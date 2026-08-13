import os
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from werkzeug.utils import secure_filename
from models import db, Booking, User, Therapist, Treatment
from config import Config
from flask_migrate import Migrate
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash


app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)
migrate = Migrate(app, db)
app.secret_key = "your_secret_key"  # Needed for sessions
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"  # Redirects unauthorized users


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def allowed_image(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in app.config["ALLOWED_IMAGE_EXTENSIONS"]
    )


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('admin'))
        else:
            return "Invalid credentials"
    return render_template('admin_login.html')


@app.route('/')
def home():
    return render_template('index.html')


# ---------- Booking flow ----------

@app.route('/therapist', methods=['GET', 'POST'])
def therapist():
    if request.method == 'POST':
        session['therapist'] = request.form['therapist']
        return redirect(url_for('treatment'))
    therapists = Therapist.query.all()
    return render_template('step1_therapist.html', step=1, therapists=therapists)


@app.route('/treatment', methods=['GET', 'POST'])
def treatment():
    if request.method == 'POST':
        session['massage'] = request.form['massage']
        return redirect(url_for('datetime'))
    treatments = Treatment.query.all()
    return render_template('step2_treatment.html', step=2,
                            therapist=session.get('therapist'),
                            treatments=treatments)


@app.route('/datetime', methods=['GET', 'POST'])
def datetime():
    if request.method == 'POST':
        session['date'] = request.form['date']
        session['time'] = request.form['time']
        return redirect(url_for('details'))
    return render_template('step3_datetime.html', step=3,
                            therapist=session.get('therapist'),
                            massage=session.get('massage'))


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
                            date=session.get('date'),
                            time=session.get('time'))


@app.route('/payment', methods=['GET', 'POST'])
def payment():
    if request.method == 'POST':
        payment_method = request.form['payment_method']  # "Online" or "In Person"

        # Paying online settles the balance immediately.
        # Paying in person leaves it unpaid until the front desk collects payment,
        # and the service still needs to be carried out either way.
        payment_status = "Paid" if payment_method == "Online" else "Unpaid"

        new_booking = Booking(
            customer_name=session['name'],
            customer_email=session['email'],
            customer_phone=session['phone'],
            therapist=session['therapist'],
            massage_type=session['massage'],
            date=session['date'],
            time=session['time'],
            payment_method=payment_method,
            payment_status=payment_status,
            service_status="Pending"
        )
        db.session.add(new_booking)
        db.session.commit()
        return redirect(url_for('confirmation', booking_id=new_booking.id))
    return render_template('step5_payment.html', step=5,
                            therapist=session.get('therapist'),
                            massage=session.get('massage'),
                            date=session.get('date'),
                            time=session.get('time'),
                            name=session.get('name'),
                            email=session.get('email'),
                            phone=session.get('phone'))


@app.route('/confirmation/<int:booking_id>')
def confirmation(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    return render_template('confirmation.html', booking=booking)


# ---------- Admin: bookings ----------

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

    if payment_status in ('Paid', 'Unpaid'):
        booking.payment_status = payment_status
    if service_status in ('Pending', 'Done'):
        booking.service_status = service_status

    db.session.commit()
    return redirect(url_for('admin'))


# ---------- Admin: therapists ----------

@app.route('/admin/therapists', methods=['GET', 'POST'])
@login_required
def admin_therapists():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        specialty = request.form.get('specialty', '').strip()
        image_file = request.files.get('image')

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
        db.session.add(new_therapist)
        db.session.commit()
        flash(f"Added therapist {name}.")
        return redirect(url_for('admin_therapists'))

    therapists = Therapist.query.all()
    return render_template('admin_therapists.html', therapists=therapists)


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

        new_treatment = Treatment(name=name, description=description)
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
    return redirect(url_for('home'))


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
