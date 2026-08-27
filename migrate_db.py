import sqlite3
from config import Config

# Pull the actual db path straight from your config so this always matches
# whatever spa_app.py is using.
db_uri = Config.SQLALCHEMY_DATABASE_URI
if not db_uri.startswith("sqlite:///"):
    raise SystemExit(f"This script only handles sqlite databases. Found: {db_uri}")

db_path = db_uri.replace("sqlite:///", "", 1)
print(f"Migrating database: {db_path}")

conn = sqlite3.connect(db_path)
cur = conn.cursor()


def table_exists(table_name):
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    )
    return cur.fetchone() is not None


def existing_columns(table_name):
    cur.execute(f"PRAGMA table_info({table_name})")
    return {row[1] for row in cur.fetchall()}


def add_column_if_missing(table_name, column_name, ddl_type_and_default):
    if not table_exists(table_name):
        print(f"  - Table '{table_name}' doesn't exist yet, skipping column add "
              f"(it will be created fresh).")
        return
    cols = existing_columns(table_name)
    if column_name in cols:
        print(f"  - {table_name}.{column_name} already exists, skipping.")
        return
    sql = f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl_type_and_default}"
    print(f"  - Adding {table_name}.{column_name} ...")
    cur.execute(sql)


print("\nChecking Treatment table...")
add_column_if_missing("treatment", "price", "FLOAT DEFAULT 0.0")

print("\nChecking Booking table...")
add_column_if_missing("booking", "payment_reference", "VARCHAR(100)")
add_column_if_missing("booking", "commission_paid", "BOOLEAN DEFAULT 0")
add_column_if_missing("booking", "commission_reference", "VARCHAR(100)")

# Normalize any NULLs left over from the ALTER TABLE default (SQLite applies
# the default only to *new* rows in some versions/edge cases, so make sure
# existing rows are consistent too).
if table_exists("treatment"):
    cur.execute("UPDATE treatment SET price = 0.0 WHERE price IS NULL")
if table_exists("booking"):
    cur.execute("UPDATE booking SET commission_paid = 0 WHERE commission_paid IS NULL")

conn.commit()
conn.close()

print("\nColumn migration done.")
print("Now creating any brand-new tables (BookingHistory, Complaint) via SQLAlchemy...")

# Delegate new-table creation to SQLAlchemy - db.create_all() only creates
# tables that don't exist yet, so this is safe and won't touch the tables
# we just migrated above.
from spa_app import app, db  # noqa: E402

with app.app_context():
    db.create_all()

print("Done! Your database is now up to date.")