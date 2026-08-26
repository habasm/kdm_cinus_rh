"""Idempotently add realistic CINUS demo records to clinic.db."""
import sqlite3
from datetime import datetime
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / "clinic.db"
now = datetime.now().isoformat(timespec="seconds")
children = [
    ("CIN-2026-0101", "Sami", "Worku", "Male", "2024-02-14", "Meron Worku", "0910 114 201", "Amhara", "Bahir Dar", "01", "HH-0101"),
    ("CIN-2026-0102", "Eden", "Kassa", "Female", "2025-01-22", "Rahel Kassa", "0910 114 202", "Amhara", "Bahir Dar", "02", "HH-0102"),
    ("CIN-2026-0103", "Yonas", "Bekele", "Male", "2023-11-08", "Almaz Bekele", "0910 114 203", "Amhara", "Bahir Dar", "03", "HH-0103"),
    ("CIN-2026-0104", "Hana", "Desta", "Female", "2024-08-30", "Selam Desta", "0910 114 204", "Amhara", "Bahir Dar", "05", "HH-0104"),
    ("CIN-2026-0105", "Kalkidan", "Mamo", "Female", "2025-05-16", "Tigist Mamo", "0910 114 205", "Amhara", "Bahir Dar", "06", "HH-0105"),
    ("CIN-2026-0106", "Dawit", "Abate", "Male", "2022-12-03", "Mulu Abate", "0910 114 206", "Amhara", "Bahir Dar", "07", "HH-0106"),
    ("CIN-2026-0107", "Mahi", "Alemu", "Female", "2024-04-27", "Saba Alemu", "0910 114 207", "Amhara", "Bahir Dar", "10", "HH-0107"),
]
plans = {
    "Sami": [("2026-06-12", 10.6, 85.0, 13.1, "normal", "ndd"), ("2026-08-12", 11.2, 87.0, 13.5, "normal", "ndd")],
    "Eden": [("2026-05-20", 7.4, 67.0, 12.5, "normal", "ndd"), ("2026-08-20", 8.1, 70.0, 12.8, "mam", "sdd")],
    "Yonas": [("2026-07-05", 13.0, 99.0, 11.8, "mam", "ndd"), ("2026-08-05", 13.2, 100.0, 11.9, "mam", "ndd")],
    "Hana": [("2026-08-06", 9.5, 76.0, 13.4, "normal", "ndd")],
    "Kalkidan": [("2026-08-15", 6.8, 64.0, 12.9, "normal", "ndd")],
    "Dawit": [("2026-07-18", 15.6, 105.0, 11.4, "sam", "sdd")],
    "Mahi": [("2026-06-28", 10.1, 82.0, 13.0, "normal", "ndd"), ("2026-08-22", 10.7, 84.0, 13.2, "normal", "ndd")],
}

with sqlite3.connect(DB) as db:
    for row in children:
        db.execute("INSERT OR IGNORE INTO children (child_code,first_name,last_name,sex,date_of_birth,mother_name,phone,region,woreda,kebele,household_id,registration_date) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (*row, now))
    for first, visits in plans.items():
        child = db.execute("SELECT id,date_of_birth FROM children WHERE first_name=? ORDER BY id DESC LIMIT 1", (first,)).fetchone()
        for day, weight, height, muac, nutrition, development in visits:
            child_id, dob = child
            if db.execute("SELECT 1 FROM visits WHERE child_id=? AND visit_date=?", (child_id, day)).fetchone():
                continue
            age = max(0, (int(day[:4]) - int(dob[:4])) * 12 + int(day[5:7]) - int(dob[5:7]))
            cur = db.execute("INSERT INTO visits (child_id,visit_date,age_months,weight,height,muac,edema,health_worker,created_at) VALUES (?,?,?,?,?,?,?,?,?)", (child_id, day, age, weight, height, muac, int(nutrition == "sam"), "Marta, HEW", now))
            visit_id = cur.lastrowid
            db.execute("INSERT INTO growth_assessments (visit_id,waz,haz,whz,underweight_status,stunting_status,wasting_status,generated_at) VALUES (?,?,?,?,?,?,?,?)", (visit_id, -1.0, -1.0, -1.0, "Normal", "Normal", "Normal" if nutrition == "normal" else "Moderate wasting", now))
            db.execute("INSERT INTO nutrition_screenings (visit_id,screening_date,result,referral) VALUES (?,?,?,?)", (visit_id, day, nutrition, "Nutrition counselling" if nutrition == "normal" else "Priority nutrition follow-up"))
            db.execute("INSERT INTO development_screenings (child_id,visit_id,date,result,notes) VALUES (?,?,?,?,?)", (child_id, visit_id, day, development, "Development reviewed during follow-up"))
    print({table: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ("children", "visits", "rh_cards")})
