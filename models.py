from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()


# Which therapists can perform which treatments (many-to-many).
therapist_treatments = db.Table(
    'therapist_treatments',
    db.Column('therapist_id', db.Integer, db.ForeignKey('therapist.id'), primary_key=True),
    db.Column('treatment_id', db.Integer, db.ForeignKey('treatment.id'), primary_key=True),
)


class Therapist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    specialty = db.Column(db.String(100))
    image_filename = db.Column(db.String(200))  # filename inside static/uploads/therapists

    # Treatments this therapist is able to perform. Backref gives each
    # Treatment a `.therapists` list.
    treatments = db.relationship('Treatment', secondary=therapist_treatments, backref='therapists')


class Treatment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(300))

    # Duration-based pricing (GHS). Customers pick a treatment + duration
    # combo on the booking page; whichever of these four applies becomes
    # the charged amount for online payments.
    price_30 = db.Column(db.Float, default=0.0)   # 30 mins or less
    price_60 = db.Column(db.Float, default=0.0)   # 1 hour
    price_90 = db.Column(db.Float, default=0.0)   # 1 hr 30 mins
    price_120 = db.Column(db.Float, default=0.0)  # 2 hours


class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(100), nullable=False)
    customer_email = db.Column(db.String(100), nullable=False)
    customer_phone = db.Column(db.String(20), nullable=False)
    therapist = db.Column(db.String(100), nullable=False)
    massage_type = db.Column(db.String(100), nullable=False)
    duration = db.Column(db.String(20), default="1 hour")  # e.g. "30 mins or less", "1 hour"
    date = db.Column(db.String(20), nullable=False)
    time = db.Column(db.String(20), nullable=False)
    payment_method = db.Column(db.String(50), nullable=False)  # "Online" or "In Person"

    # Two independent statuses, as requested:
    payment_status = db.Column(db.String(20), default="Unpaid")   # "Paid" or "Unpaid"
    service_status = db.Column(db.String(20), default="Pending")  # "Pending" or "Done"

    # Paystack reference for the customer's own online payment (split at
    # checkout between the business subaccount and your account).
    payment_reference = db.Column(db.String(100))

    # For "In Person" bookings there's no automatic split, so the spa has to
    # separately pay your commission via Paystack before the booking can be
    # marked Paid. These two fields track that.
    commission_paid = db.Column(db.Boolean, default=False)
    commission_reference = db.Column(db.String(100))

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class BookingHistory(db.Model):
    """Audit trail: every payment/service status change on a booking."""
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey('booking.id'), nullable=False)
    field_changed = db.Column(db.String(50), nullable=False)   # e.g. "payment_status"
    old_value = db.Column(db.String(50))
    new_value = db.Column(db.String(50))
    changed_by = db.Column(db.String(100))                     # admin username, or "customer"/"system"
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    booking = db.relationship('Booking', backref=db.backref('history', order_by='BookingHistory.timestamp.desc()'))


class Complaint(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))    # optional
    email = db.Column(db.String(100))   # optional
    phone = db.Column(db.String(20))    # optional
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
