import os

class Config:
    # Secret key for sessions/forms
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'mysecretkey'

    # Database setup (SQLite file in project root)
    SQLALCHEMY_DATABASE_URI = 'sqlite:///spa.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
