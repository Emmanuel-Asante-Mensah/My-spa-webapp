import os
import datetime as dt
from datetime import timedelta
import requests
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from werkzeug.utils import secure_filename
from models import db, Booking, BookingHistory, Complaint, User, Therapist, Treatment
from config import Config
from flask_migrate import Migrate
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash


app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)
migrate = Migrate(app, db)
app.secret_key = "your_secret_key"  # Needed for sessions

# Admin sessions expire after a period of inactivity. This matters because
# the admin dashboard is only ever protected by @login_required + this
# session cookie - if a staff member leaves it logged in on a shared/kiosk
# browser, we don't want that login to stay valid for whoever uses the
# browser next. Combined with session.permanent = True set at login time,
# Flask expires the session automatically after this window.
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=20)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"  # Redirects unauthorized users

# Spa opening hours - bookings can only be made within this window.
OPENING_HOUR = 8   # 8:00 AM
CLOSING_HOUR = 22  # 10:00 PM

PAYSTACK_BASE_URL = "https://api.paystack.co"

# Duration options customers can pick per treatment. Each maps to one of
# the four price columns on Treatment. Order matters - it's the display
# order on the treatment page.
DURATION_CHOICES = [
    ("30", "30 mins or less", "price_30"),
    ("60", "1 hour", "price_60"),
    ("90", "1 hr 30 mins", "price_90"),
    ("120", "2 hours", "price_120"),
]
DURATION_PRICE_FIELD = {code: field for code, _, field in DURATION_CHOICES}
DURATION_LABEL = {code: label for code, label, _ in DURATION_CHOICES}


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def allowed_image(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in app.config["ALLOWED_IMAGE_EXTENSIONS"]
    )


def log_change(booking_id, field, old_value, new_value, changed_by="system"):
    """Record an entry in the booking audit trail. No-ops if nothing changed."""
    if str(old_value) == str(new_value):
        return
    db.session.add(BookingHistory(
        booking_id=booking_id,
        field_changed=field,
        old_value=str(old_value) if old_value is not None else None,
        new_value=str(new_value) if new_value is not None else None,
        changed_by=changed_by,
    ))


# ---------- Paystack helpers ----------
# Docs: https://paystack.com/docs/payments/split-payments/ and
# https://paystack.com/docs/api/transaction/

def paystack_headers():
    return {
        "Authorization": f"Bearer {app.config['PAYSTACK_SECRET_KEY']}",
        "Content-Type": "application/json",
    }


def paystack_initialize(email, amount_ghs, callback_url, subaccount=None, transaction_charge=None, metadata=None):
    """Start a Paystack transaction. Amount is in GHS; Paystack wants pesewas (x100).
    If `subaccount` is set, the payment is split: `transaction_charge` (GHS) stays
    with your main account and the remainder goes to the subaccount."""
    payload = {
        "email": email,
        "amount": int(round(amount_ghs * 100)),
        "currency": "GHS",
        "callback_url": callback_url,
    }
    if subaccount:
        payload["subaccount"] = subaccount
    if transaction_charge is not None:
        payload["transaction_charge"] = int(round(transaction_charge * 100))
    if metadata:
        payload["metadata"] = metadata

    resp = requests.post(f"{PAYSTACK_BASE_URL}/transaction/initialize",
                          json=payload, headers=paystack_headers(), timeout=15)
    return resp.json()


def paystack_verify(reference):
    resp = requests.get(f"{PAYSTACK_BASE_URL}/transaction/verify/{reference}",
                         headers=paystack_headers(), timeout=15)
    return resp.json()


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            # Make this an expiring session (see PERMANENT_SESSION_LIFETIME
            # above) rather than one that stays valid indefinitely.
            session.permanent = True
            return redirect(url_for('admin'))
        else:
            return "Invalid credentials"
    return render_template('admin_login.html')


@app.route('/')
def home():
    return render_template('index.html')


# ---------- Booking flow ----------
# Order: Treatment+Duration -> Therapist (filtered by treatment) -> Date/Time -> Details -> Payment
# Customers pick *what* they want done (and for how long) before *who* does
# it, and the therapist list on step 2 only shows people who actually
# perform that treatment.

@app.route('/treatment', methods=['GET', 'POST'])
def treatment():
    if request.method == 'POST':
        # Radio value is "<treatment_id>:<duration_code>", e.g. "3:90"
        selection = request.form.get('massage', '')
        try:
            treatment_id_str, duration_code = selection.split(':', 1)
            treatment_id = int(treatment_id_str)
        except ValueError:
            flash("Please choose a treatment and duration.")
            return redirect(url_for('treatment'))

        chosen = Treatment.query.get(treatment_id)
        price_field = DURATION_PRICE_FIELD.get(duration_code)
        if not chosen or not price_field:
            flash("Please choose a valid treatment and duration.")
            return redirect(url_for('treatment'))

        session['treatment_id'] = chosen.id
        session['massage'] = chosen.name
        session['duration_code'] = duration_code
        session['duration_label'] = DURATION_LABEL[duration_code]
        session['price'] = getattr(chosen, price_field) or 0.0

        # Changing the treatment invalidates whichever therapist was
        # previously picked for the old treatment.
        session.pop('therapist', None)
        return redirect(url_for('therapist'))

    treatments = Treatment.query.all()
    return render_template('step2_treatment.html', step=1,
                            treatments=treatments,
                            duration_choices=DURATION_CHOICES)


@app.route('/therapist', methods=['GET', 'POST'])
def therapist():
    if not session.get('massage'):
        return redirect(url_for('treatment'))

    if request.method == 'POST':
        session['therapist'] = request.form['therapist']
        return redirect(url_for('datetime'))

    chosen_treatment = Treatment.query.get(session.get('treatment_id'))
    # Strict filtering: only therapists specifically assigned to this
    # treatment are shown. No fallback to "all therapists" anymore - if
    # nobody's assigned, the page shows an empty-state message instead.
    therapists = chosen_treatment.therapists if chosen_treatment else []

    return render_template('step1_therapist.html', step=2,
                            massage=session.get('massage'),
                            duration_label=session.get('duration_label'),
                            therapists=therapists)


@app.route('/datetime', methods=['GET', 'POST'])
def datetime():
    if request.method == 'POST':
        date_str = request.form['date']
        time_str = request.form['time']

        # Enforce spa opening hours (8:00 AM - 10:00 PM).
        try:
            hour, minute = (int(part) for part in time_str.split(':')[:2])
        except (ValueError, AttributeError):
            flash("Please choose a valid time.")
            return redirect(url_for('datetime'))

        if not (OPENING_HOUR * 60 <= hour * 60 + minute <= CLOSING_HOUR * 60):
            flash(f"We're only open for bookings between {OPENING_HOUR}:00 AM and {CLOSING_HOUR - 12}:00 PM. Please pick a time in that window.")
            return redirect(url_for('datetime'))

        session['date'] = date_str
        session['time'] = time_str
        return redirect(url_for('details'))
    return render_template('step3_datetime.html', step=3,
                            therapist=session.get('therapist'),
                            massage=session.get('massage'),
                            duration=session.get('duration_label'),
                            opening_hour=OPENING_HOUR,
                            closing_hour=CLOSING_HOUR)


@app.route('/details', methods=['GET', 'POST'])
def details():
    if request.method == 'POST':
        session['name'] = request.form['name']
        session['email'] = request.form['email']
        session['phone'] = request.form['phone']
        return redirect(url_for('payment'))
    return render_template('step4_details.html', step=4,
                            therapist=session.get('therapist'),
                            massage=session.get('massage'),
                            duration=session.get('duration_label'),
                            date=session.get('date'),
                            time=session.get('time'))


@app.route('/payment', methods=['GET', 'POST'])
def payment():
    if request.method == 'POST':
        payment_method = request.form['payment_method']  # "Online" or "In Person"

        new_booking = Booking(
            customer_name=session['name'],
            customer_email=session['email'],
            customer_phone=session['phone'],
            therapist=session['therapist'],
            massage_type=session['massage'],
            duration=session.get('duration_label', '1 hour'),
            date=session['date'],
            time=session['time'],
            payment_method=payment_method,
            payment_status="Unpaid",
            service_status="Pending",
        )
        db.session.add(new_booking)
        db.session.commit()
        log_change(new_booking.id, "booking", None, "created", changed_by="customer")
        db.session.commit()

        if payment_method == "Online":
            if not app.config.get('PAYSTACK_SECRET_KEY') or not app.config.get('PAYSTACK_SUBACCOUNT_CODE'):
                flash("Online payment isn't set up yet - please choose 'Pay In Person' for now.")
                return redirect(url_for('payment'))

            amount = session.get('price') or 0
            if amount <= app.config['COMMISSION_GHS']:
                flash("This treatment/duration doesn't have a valid price set up for online payment yet. Please choose 'Pay In Person', or contact the spa.")
                return redirect(url_for('payment'))

            result = paystack_initialize(
                email=new_booking.customer_email,
                amount_ghs=amount,
                callback_url=url_for('payment_callback', _external=True),
                subaccount=app.config['PAYSTACK_SUBACCOUNT_CODE'],
                transaction_charge=app.config['COMMISSION_GHS'],
                metadata={"booking_id": new_booking.id},
            )
            if result.get('status'):
                new_booking.payment_reference = result['data']['reference']
                db.session.commit()
                return redirect(result['data']['authorization_url'])

            flash("We couldn't start the online payment. Please try again or pay in person.")
            return redirect(url_for('payment'))

        # In-person: the booking is confirmed now; payment gets settled (and
        # the commission paid) later from the admin dashboard.
        booking_id = new_booking.id
        session.clear()
        return redirect(url_for('confirmation', booking_id=booking_id))

    return render_template('step5_payment.html', step=5,
                            therapist=session.get('therapist'),
                            massage=session.get('massage'),
                            duration=session.get('duration_label'),
                            date=session.get('date'),
                            time=session.get('time'),
                            name=session.get('name'),
                            email=session.get('email'),
                            phone=session.get('phone'))


@app.route('/payment/callback')
def payment_callback():
    """Paystack redirects the customer's browser back here after checkout."""
    reference = request.args.get('reference')
    if not reference:
        flash("Missing payment reference.")
        return redirect(url_for('home'))

    booking = Booking.query.filter_by(payment_reference=reference).first_or_404()

    result = paystack_verify(reference)
    if result.get('status') and result.get('data', {}).get('status') == 'success':
        old_status = booking.payment_status
        booking.payment_status = "Paid"
        log_change(booking.id, "payment_status", old_status, "Paid", changed_by="customer (online payment)")
        db.session.commit()
    else:
        flash("We couldn't verify your payment. If money left your account, contact the spa with your booking details.")

    session.clear()
    return redirect(url_for('confirmation', booking_id=booking.id))


@app.route('/confirmation/<int:booking_id>')
def confirmation(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    return render_template('confirmation.html', booking=booking)


# ---------- Customer complaints / feedback ----------

@app.route('/complaints', methods=['GET', 'POST'])
def complaints():
    if request.method == 'POST':
        message = request.form.get('message', '').strip()
        if not message:
            flash("Please enter your comment or complaint before submitting.")
            return redirect(url_for('complaints'))

        db.session.add(Complaint(
            name=request.form.get('name', '').strip() or None,
            email=request.form.get('email', '').strip() or None,
            phone=request.form.get('phone', '').strip() or None,
            message=message,
        ))
        db.session.commit()
        flash("Thank you - your feedback has been received.")
        return redirect(url_for('complaints'))
    return render_template('complaints.html')


# ---------- Admin: bookings ----------
# Every /admin* route below is gated by @login_required. There is no link
# to any of these pages anywhere in the customer-facing templates - staff
# reach /login by typing/bookmarking the URL directly.

@app.route('/admin')
@login_required
def admin():
    bookings = Booking.query.order_by(Booking.id.desc()).all()
    return render_template('admin.html', bookings=bookings)


@app.route('/admin/booking/<int:booking_id>/update', methods=['POST'])
@login_required
def update_booking_status(booking_id):
    booking = Booking.query.get_or_404(booking_id)

    payment_status = request.form.get('payment_status')
    service_status = request.form.get('service_status')

    if payment_status in ('Paid', 'Unpaid') and payment_status != booking.payment_status:
        if payment_status == 'Paid' and booking.payment_method == 'In Person' and not booking.commission_paid:
            flash(f"Settle the {app.config['COMMISSION_GHS']} GHS commission for this booking first (use 'Pay Commission' below), then mark it Paid.")
        else:
            log_change(booking.id, "payment_status", booking.payment_status, payment_status, changed_by=current_user.username)
            booking.payment_status = payment_status

    if service_status in ('Pending', 'Done') and service_status != booking.service_status:
        log_change(booking.id, "service_status", booking.service_status, service_status, changed_by=current_user.username)
        booking.service_status = service_status

    db.session.commit()
    return redirect(url_for('admin'))


@app.route('/admin/booking/<int:booking_id>/pay-commission')
@login_required
def pay_commission(booking_id):
    """Admin-initiated Paystack payment: the spa pays your commission
    directly (no split) for an in-person booking. Marking the booking Paid
    is blocked until this succeeds."""
    booking = Booking.query.get_or_404(booking_id)

    if booking.commission_paid:
        flash("Commission already settled for this booking.")
        return redirect(url_for('admin'))

    if not app.config.get('PAYSTACK_SECRET_KEY'):
        flash("Paystack isn't configured yet - add PAYSTACK_SECRET_KEY to enable commission payments.")
        return redirect(url_for('admin'))

    admin_email = current_user.username if '@' in current_user.username else f"{current_user.username}@spa.local"
    result = paystack_initialize(
        email=admin_email,
        amount_ghs=app.config['COMMISSION_GHS'],
        callback_url=url_for('commission_callback', booking_id=booking.id, _external=True),
        metadata={"booking_id": booking.id, "type": "commission"},
    )
    if result.get('status'):
        booking.commission_reference = result['data']['reference']
        db.session.commit()
        return redirect(result['data']['authorization_url'])

    flash("Couldn't start the commission payment. Please try again.")
    return redirect(url_for('admin'))


@app.route('/admin/booking/<int:booking_id>/commission-callback')
@login_required
def commission_callback(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    reference = request.args.get('reference') or booking.commission_reference

    result = paystack_verify(reference) if reference else {}
    if result.get('status') and result.get('data', {}).get('status') == 'success':
        log_change(booking.id, "commission_paid", booking.commission_paid, True, changed_by=current_user.username)
        booking.commission_paid = True
        db.session.commit()
        flash("Commission payment confirmed - you can now mark this booking Paid.")
    else:
        flash("Commission payment couldn't be verified. Please try again.")

    return redirect(url_for('admin'))


@app.route('/admin/history')
@login_required
def admin_history():
    booking_id = request.args.get('booking_id', type=int)
    query = BookingHistory.query.order_by(BookingHistory.timestamp.desc())
    if booking_id:
        query = query.filter_by(booking_id=booking_id)
    history = query.all()
    return render_template('admin_history.html', history=history, booking_id=booking_id)


@app.route('/admin/analytics')
@login_required
def admin_analytics():
    bookings = Booking.query.all()

    day_order = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    day_counts = {d: 0 for d in day_order}
    hour_counts = {h: 0 for h in range(24)}

    for b in bookings:
        try:
            parsed_date = dt.datetime.strptime(b.date, "%Y-%m-%d")
            day_label = parsed_date.strftime("%a")
            if day_label in day_counts:
                day_counts[day_label] += 1
        except (ValueError, TypeError):
            pass
        try:
            hour = int(b.time.split(':')[0])
            if hour in hour_counts:
                hour_counts[hour] += 1
        except (ValueError, AttributeError, IndexError):
            pass

    return render_template(
        'admin_analytics.html',
        day_labels=day_order,
        day_values=[day_counts[d] for d in day_order],
        hour_labels=[f"{h:02d}:00" for h in hour_counts.keys()],
        hour_values=list(hour_counts.values()),
        total_bookings=len(bookings),
    )


@app.route('/admin/complaints')
@login_required
def admin_complaints():
    complaint_list = Complaint.query.order_by(Complaint.created_at.desc()).all()
    return render_template('admin_complaints.html', complaints=complaint_list)


# ---------- Admin: therapists ----------

@app.route('/admin/therapists', methods=['GET', 'POST'])
@login_required
def admin_therapists():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        specialty = request.form.get('specialty', '').strip()
        image_file = request.files.get('image')
        treatment_ids = request.form.getlist('treatment_ids')

        if not name:
            flash("Therapist name is required.")
            return redirect(url_for('admin_therapists'))

        image_filename = None
        if image_file and image_file.filename:
            if not allowed_image(image_file.filename):
                flash("Image must be png, jpg, jpeg, gif, or webp.")
                return redirect(url_for('admin_therapists'))
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            safe_name = secure_filename(image_file.filename)
            # Prefix to avoid collisions between therapists with similar filenames
            image_filename = f"{name.replace(' ', '_').lower()}_{safe_name}"
            image_file.save(os.path.join(app.config['UPLOAD_FOLDER'], image_filename))

        new_therapist = Therapist(name=name, specialty=specialty, image_filename=image_filename)
        if treatment_ids:
            new_therapist.treatments = Treatment.query.filter(
                Treatment.id.in_(treatment_ids)
            ).all()

        db.session.add(new_therapist)
        db.session.commit()
        flash(f"Added therapist {name}.")
        return redirect(url_for('admin_therapists'))

    therapists = Therapist.query.all()
    treatments = Treatment.query.all()
    return render_template('admin_therapists.html', therapists=therapists, treatments=treatments)


@app.route('/admin/therapists/<int:therapist_id>/delete', methods=['POST'])
@login_required
def delete_therapist(therapist_id):
    therapist_obj = Therapist.query.get_or_404(therapist_id)
    if therapist_obj.image_filename:
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], therapist_obj.image_filename)
        if os.path.exists(image_path):
            os.remove(image_path)
    db.session.delete(therapist_obj)
    db.session.commit()
    return redirect(url_for('admin_therapists'))


# ---------- Admin: treatments ----------

@app.route('/admin/treatments', methods=['GET', 'POST'])
@login_required
def admin_treatments():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()

        if not name:
            flash("Treatment name is required.")
            return redirect(url_for('admin_treatments'))

        def parse_price(field_name):
            raw = request.form.get(field_name, '').strip()
            try:
                return float(raw) if raw else 0.0
            except ValueError:
                return None

        price_30 = parse_price('price_30')
        price_60 = parse_price('price_60')
        price_90 = parse_price('price_90')
        price_120 = parse_price('price_120')

        if None in (price_30, price_60, price_90, price_120):
            flash("Prices must be numbers.")
            return redirect(url_for('admin_treatments'))

        new_treatment = Treatment(
            name=name,
            description=description,
            price_30=price_30,
            price_60=price_60,
            price_90=price_90,
            price_120=price_120,
        )
        db.session.add(new_treatment)
        db.session.commit()
        flash(f"Added treatment {name}.")
        return redirect(url_for('admin_treatments'))

    treatments = Treatment.query.all()
    return render_template('admin_treatments.html', treatments=treatments)


@app.route('/admin/treatments/<int:treatment_id>/delete', methods=['POST'])
@login_required
def delete_treatment(treatment_id):
    treatment_obj = Treatment.query.get_or_404(treatment_id)
    db.session.delete(treatment_obj)
    db.session.commit()
    return redirect(url_for('admin_treatments'))


@app.route('/admin_logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('home'))


@app.route('/logout')
@login_required
def logout():
    logout_user()
    session.clear()
    return redirect(url_for('home'))


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
