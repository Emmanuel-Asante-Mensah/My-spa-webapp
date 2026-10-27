"""
One-off migration: adds duration-based pricing columns to `treatment` and a
`duration` column to `booking`, directly on the live database file.

Safe to re-run - it checks for each column before adding it.

IMPORTANT: this targets instance/spa_webapp.db explicitly (the active DB
per check_db.py), not whatever Config.SQLALCHEMY_DATABASE_URI would resolve
to outside the Flask app context.

Usage:
    python add_duration_pricing.py
"""
import sqlite3
import os
import shutil
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'instance', 'spa_webapp.db')


def column_exists(cur, table, column):
    cur.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def main():
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}. Nothing to migrate.")
        return

    # Quick backup before touching the schema.
    backup_path = DB_PATH + f".bak-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    shutil.copy2(DB_PATH, backup_path)
    print(f"Backed up database to {backup_path}")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    treatment_columns = [
        ("price_30", "FLOAT DEFAULT 0.0"),
        ("price_60", "FLOAT DEFAULT 0.0"),
        ("price_90", "FLOAT DEFAULT 0.0"),
        ("price_120", "FLOAT DEFAULT 0.0"),
    ]
    for col, coltype in treatment_columns:
        if not column_exists(cur, "treatment", col):
            print(f"Adding treatment.{col}")
            cur.execute(f"ALTER TABLE treatment ADD COLUMN {col} {coltype}")
        else:
            print(f"treatment.{col} already exists - skipping")

    if not column_exists(cur, "booking", "duration"):
        print("Adding booking.duration")
        cur.execute("ALTER TABLE booking ADD COLUMN duration VARCHAR(20) DEFAULT '1 hour'")
    else:
        print("booking.duration already exists - skipping")

    conn.commit()
    conn.close()
    print("\nDone. All treatments now have price_30/60/90/120 = 0.0.")
    print("Go to Admin > Treatments and set the real prices for each duration.")
    print("The old single `price` column is left in place, unused, for now.")


if __name__ == "__main__":
    main()
