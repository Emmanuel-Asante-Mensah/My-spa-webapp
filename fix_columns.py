"""
fix_columns.py

Adds the missing columns to your REAL database file:
    instance/spa_webapp.db

This is the file confirmed to hold your actual bookings/treatments/
therapists. It will NOT delete or modify any existing rows - it only
adds new columns (with safe defaults) if they're missing.

Usage:
    python fix_columns.py
"""

import sqlite3

DB_PATH = "instance/spa_webapp.db"

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()


def existing_columns(table_name):
    cur.execute(f"PRAGMA table_info({table_name})")
    return {row[1] for row in cur.fetchall()}


def add_column_if_missing(table_name, column_name, ddl_type_and_default):
    cols = existing_columns(table_name)
    if column_name in cols:
        print(f"  - {table_name}.{column_name} already exists, skipping.")
        return
    sql = f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl_type_and_default}"
    print(f"  - Adding {table_name}.{column_name} ...")
    cur.execute(sql)


print(f"Fixing columns in {DB_PATH}\n")

print("Treatment table:")
add_column_if_missing("treatment", "price", "FLOAT DEFAULT 0.0")

print("\nBooking table:")
add_column_if_missing("booking", "payment_reference", "VARCHAR(100)")
add_column_if_missing("booking", "commission_paid", "BOOLEAN DEFAULT 0")
add_column_if_missing("booking", "commission_reference", "VARCHAR(100)")

# Make sure existing rows have sane values rather than NULL
cur.execute("UPDATE treatment SET price = 0.0 WHERE price IS NULL")
cur.execute("UPDATE booking SET commission_paid = 0 WHERE commission_paid IS NULL")

conn.commit()
conn.close()

print("\nDone! Your 4 existing bookings and 2 treatments were left untouched -")
print("they now just have the new columns available (set to safe defaults).")
print("You can set real prices for your treatments from the admin panel.")
