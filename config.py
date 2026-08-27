import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    # Secret key for sessions/forms
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'mysecretkey'

    # Database setup (SQLite file in project root)
    SQLALCHEMY_DATABASE_URI = 'sqlite:///spa_webapp.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Where therapist photos get saved (must live under /static so it's servable)
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads', 'therapists')
    ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5 MB upload cap

    # --- Paystack (payments) ---
    # 1. Sign up at https://paystack.com and grab your Secret/Public keys
    #    (Settings > API Keys & Webhooks). Set them as real environment
    #    variables - never commit live keys to source control.
    # 2. Create a Subaccount for the SPA's own bank account or mobile money
    #    number (Settings > Subaccounts) and put its code below. Online
    #    customer payments are split automatically: COMMISSION_GHS goes to
    #    your main Paystack account, the rest goes straight to this
    #    subaccount.
    PAYSTACK_SECRET_KEY = "sk_test_63f3504a3964f9c62bc5e8ac1535a92daf562cfc"
    PAYSTACK_PUBLIC_KEY = "pk_test_63758d0813ab273f7e3a1976e5eca7596148ab95"
    PAYSTACK_SUBACCOUNT_CODE = "ACCT_auydfxdmguqlqxv"

    # Your cut per booking, in GHS. Charged automatically on split online
    # payments; for in-person bookings the spa pays this to you manually
    # through the admin dashboard before a booking can be marked Paid.
    COMMISSION_GHS = 10