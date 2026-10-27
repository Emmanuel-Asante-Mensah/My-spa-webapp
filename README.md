# Spa Booking Web App

A Flask web application for booking spa treatments online, with a staff admin portal, duration-based pricing, Paystack payments and a built-in commission system.

## Features

### Customer side
- **5-step booking flow:** Treatment + duration → Therapist → Date & time → Your details → Payment
- **Duration-based pricing:** each treatment has four prices (30 min or less, 1 hr, 1 hr 30, 2 hr)
- **Therapist filtering:** only therapists assigned to the chosen treatment are shown
- **Opening-hours validation:** bookings are only accepted between 8:00 AM and 10:00 PM
- **Pay online or in person:** online payments go through Paystack (card or mobile money)
- **Booking confirmation page** and a **feedback / complaints form** (name, email and phone optional)

### Admin portal (login required)
- **Bookings dashboard:** update payment status (Paid/Unpaid) and service status (Pending/Done)
- **Therapist management:** add/remove therapists, upload photos, assign treatments
- **Treatment management:** add/remove treatments with the four duration prices
- **Audit trail:** every booking and status change is logged with who made it and when
- **Complaints inbox**
- **Analytics:** bookings by day of week and by hour (Chart.js)
- **Session timeout:** admin sessions expire after 20 minutes of inactivity

### Payments and commission
- **Online bookings:** payment is split automatically through a Paystack subaccount. The commission (default GHS 10) goes to the main account and the rest goes to the spa.
- **In-person bookings:** the commission must be paid via Paystack from the admin dashboard before the booking can be marked Paid.

## Tech stack

- Python, Flask, Flask-SQLAlchemy, Flask-Migrate, Flask-Login
- SQLite
- Jinja2 templates, plain CSS
- Paystack API (via `requests`)
- Chart.js for analytics

## Getting started

### 1. Clone and install

```bash
git clone https://github.com/Emmanuel-Asante-Mensah/My-spa-webapp.git
cd My-spa-webapp
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install flask flask-sqlalchemy flask-migrate flask-login requests
```

### 2. Configure environment variables

Set these before running (never commit real keys):

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Flask session/CSRF secret |
| `PAYSTACK_SECRET_KEY` | Paystack secret key |
| `PAYSTACK_PUBLIC_KEY` | Paystack public key |
| `PAYSTACK_SUBACCOUNT_CODE` | Paystack subaccount for the spa's bank/mobile money account |

The commission amount is set by `COMMISSION_GHS` in `config.py`.

### 3. Create the database

```bash
python spa_app.py
```

Tables are created on first run. The SQLite file lives at `instance/spa_webapp.db`.

### 4. Create an admin user

Passwords are stored hashed. From a Python shell:

```python
from spa_app import app, db
from models import User
from werkzeug.security import generate_password_hash

with app.app_context():
    db.session.add(User(username="admin", password=generate_password_hash("choose-a-strong-password")))
    db.session.commit()
```

### 5. Run

```bash
python spa_app.py
```

Open http://127.0.0.1:5000. The admin portal is at `/login`. It is deliberately not linked from any public page.

## Project structure

```
spa_app.py            Routes, booking flow, admin, Paystack helpers
models.py             Therapist, Treatment, Booking, BookingHistory, Complaint, User
config.py             App configuration
templates/            Jinja2 templates (step1–step5, admin_*, confirmation, complaints)
static/               style.css, script.js, uploads/therapists/
instance/             SQLite database (not committed)
```

## Database migrations

Schema changes to an existing database use one-off scripts, because `db.create_all()` does not alter existing tables:

- `migrate_db.py` / `fix_columns.py`: add payment and commission columns
- `add_duration_pricing.py`: add `price_30/60/90/120` and `booking.duration` (backs up the DB first)
- `check_db.py`: diagnostic that shows which `.db` file holds your real data

Flask-SQLAlchemy resolves `sqlite:///spa_webapp.db` into the `instance/` folder, so run scripts against `instance/spa_webapp.db` explicitly. Back up the database before running any migration.

## Roadmap

- Block already-booked date/time slots and add an "available only" filter
- Theme and branding update
- Custom admin login URL

## License

Add a license of your choice (e.g. MIT).
