"""
check_db.py

Quick diagnostic: inspects both candidate database files and prints
what tables exist in each, plus how many rows are in key tables.
Run this to figure out which file has your real data.

Usage:
    python check_db.py
"""

import os
import sqlite3

candidates = [
    "instance/spa.db",
    "instance/spa_webapp.db",
    "spa.db",
    "spa-webapp.db",
    "spa_webapp.db",
]

for path in candidates:
    if not os.path.exists(path):
        print(f"\n{path}: (file does not exist)")
        continue

    size = os.path.getsize(path)
    print(f"\n{path}  (size: {size} bytes)")

    if size == 0:
        print("  -> empty file, nothing to check")
        continue

    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cur.fetchall()]
    print(f"  Tables: {tables}")

    for t in ("booking", "treatment", "therapist", "user"):
        if t in tables:
            cur.execute(f"SELECT COUNT(*) FROM {t}")
            count = cur.fetchone()[0]
            print(f"    {t}: {count} row(s)")

    conn.close()
