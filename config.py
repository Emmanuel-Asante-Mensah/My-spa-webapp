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