from flask import Flask, render_template, request, redirect, url_for, session
from models import db, Booking
from config import Config

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/therapist', methods=['GET','POST'])
def therapist():
    if request.method == 'POST':
        session['therapist'] = request.form['therapist']
        return redirect(url_for('treatment'))
    return render_template('step1_therapist.html', step=1)

@app.route('/treatment', methods=['GET','POST'])
def treatment():
    if request.method == 'POST':
        # This will now always exist because of required radio inputs
        session['massage'] = request.form['massage']
        return redirect(url_for('datetime'))
    return render_template('step2_treatment.html', step=2,
                       therapist=session.get('therapist'))

@app.route('/datetime', methods=['GET','POST'])
def datetime():
    if request.method == 'POST':
        session['date'] = request.form['date']
        session['time'] = request.form['time']
        return redirect(url_for('details'))
    return render_template('step3_datetime.html', step=3,
                       therapist=session.get('therapist'),
                       massage=session.get('massage'))

@app.route('/details', methods=['GET','POST'])
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

@app.route('/payment', methods=['GET','POST'])
def payment():
    if request.method == 'POST':
        new_booking = Booking(
            customer_name=session['name'],
            customer_email=session['email'],
            customer_phone=session['phone'],
            therapist=session['therapist'],
            massage_type=session['massage'],
            date=session['date'],
            time=session['time'],
            payment_method=request.form['payment'],
            payment_status="Paid"
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

@app.route('/admin')
def admin():
    bookings = Booking.query.all()
    return render_template('admin.html', bookings=bookings)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
