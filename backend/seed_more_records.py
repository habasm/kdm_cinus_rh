"""Create a fresh, versioned clinical demo dataset.

This seeder intentionally replaces the older demo data once, then records a
seed version so future application starts do not erase newly entered work.
"""
import json
import os
import shutil
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / "clinic.db"
SEED_VERSION = "fresh_30_cinus_30_rh_v1"

USERS = [
    ("admin", "System administrator", "@admin365", "admin", ["admin.users"]),
    ("child_reg", "Selamawit Bekele", "child123", "physician", ["cinus.overview", "cinus.children"]),
    ("followup", "Meseret Tola", "follow123", "physician", ["cinus.overview", "cinus.visit"]),
    ("cinus_report", "Dawit Alemayehu", "report123", "physician", ["cinus.overview", "cinus.report"]),
    ("rh_registrar", "Hana Wolde", "rh123", "physician", ["rh.clients"]),
    ("anc_provider", "Marta Girma", "anc123", "physician", ["rh.clients", "rh.anc"]),
    ("delivery_provider", "Almaz Worku", "delivery123", "physician", ["rh.labor"]),
    ("postnatal_provider", "Tigist Fekadu", "post123", "physician", ["rh.postpartum"]),
    ("rh_reporter", "Yonas Kebede", "rhreport123", "physician", ["rh.report"]),
    ("clinic_lead", "Rahel Tesfaye", "lead123", "physician", ["cinus.overview", "cinus.children", "cinus.visit", "rh.clients", "rh.anc", "rh.labor", "rh.postpartum", "rh.report"]),
]

CHILDREN = [
    ("Liya", "Abebe", "Female", "Meseret Abebe"), ("Nahom", "Kebede", "Male", "Saron Kebede"),
    ("Miki", "Tesfaye", "Male", "Hana Tesfaye"), ("Ruth", "Tadesse", "Female", "Marta Tadesse"),
    ("Yonatan", "Alemu", "Male", "Mekdes Alemu"), ("Meron", "Desta", "Female", "Liya Desta"),
    ("Samuel", "Worku", "Male", "Almaz Worku"), ("Bethel", "Fikadu", "Female", "Rahel Fikadu"),
    ("Kaleb", "Haile", "Male", "Eden Haile"), ("Saron", "Mulugeta", "Female", "Tigist Mulugeta"),
    ("Abel", "Girma", "Male", "Marta Girma"), ("Sofia", "Kassa", "Female", "Birtukan Kassa"),
    ("Henok", "Mekonnen", "Male", "Selam Mekonnen"), ("Mahi", "Demissie", "Female", "Tigist Demissie"),
    ("Dagmawi", "Bekele", "Male", "Selamawit Bekele"), ("Amen", "Assefa", "Female", "Hirut Assefa"),
    ("Robel", "Getachew", "Male", "Tsehay Getachew"), ("Naomi", "Yilma", "Female", "Mimi Yilma"),
    ("Biniyam", "Teka", "Male", "Genet Teka"), ("Maron", "Solomon", "Female", "Emebet Solomon"),
    ("Elias", "Wolde", "Male", "Hana Wolde"), ("Meklit", "Feleke", "Female", "Lensa Feleke"),
    ("Yared", "Negash", "Male", "Mahlet Negash"), ("Hiyab", "Samuel", "Female", "Frehiwot Samuel"),
    ("Nati", "Ayele", "Male", "Tigist Ayele"), ("Blain", "Dereje", "Female", "Roman Dereje"),
    ("Eyob", "Tamiru", "Male", "Eden Tamiru"), ("Feven", "Sisay", "Female", "Almaz Sisay"),
    ("Bereket", "Muluneh", "Male", "Kalkidan Muluneh"), ("Kidist", "Gashaw", "Female", "Mekdes Gashaw"),
]

MOTHERS = [
    "Mekdes Alemu", "Tigist Getachew", "Bethlehem Tesfaye", "Rahel Asmare", "Selamawit Kebede",
    "Hiwot Mulugeta", "Marta Girma", "Saron Bekele", "Hana Wolde", "Eden Haile",
    "Liya Desta", "Almaz Worku", "Meseret Abebe", "Birtukan Kassa", "Selam Mekonnen",
    "Tsehay Getachew", "Mimi Yilma", "Genet Teka", "Emebet Solomon", "Lensa Feleke",
    "Mahlet Negash", "Frehiwot Samuel", "Tigist Ayele", "Roman Dereje", "Eden Tamiru",
    "Almaz Sisay", "Kalkidan Muluneh", "Mekdes Gashaw", "Hirut Assefa", "Marta Tadesse",
]


def execute_many(db: sqlite3.Connection, statements: list[str]) -> None:
    for statement in statements:
        db.execute(statement)


def reset_clinical_data(db: sqlite3.Connection) -> None:
    execute_many(db, [
        "DELETE FROM vitamin_a",
        "DELETE FROM deworming",
        "DELETE FROM development_screenings",
        "DELETE FROM nutrition_screenings",
        "DELETE FROM growth_assessments",
        "DELETE FROM visits",
        "DELETE FROM children",
        "DELETE FROM child_services",
        "DELETE FROM maternal_records",
        "DELETE FROM patients",
        "DELETE FROM nutrition_reports",
        "DELETE FROM rh_cards",
        "DELETE FROM audit_logs",
    ])
    db.execute("DELETE FROM users")
    db.execute("DELETE FROM sqlite_sequence WHERE name IN ('children','visits','growth_assessments','nutrition_screenings','development_screenings','vitamin_a','deworming','rh_cards','patients','maternal_records','child_services','nutrition_reports','users','audit_logs')")


def seed_users(db: sqlite3.Connection, now: str) -> dict[str, str]:
    for username, full_name, password, role, permissions in USERS:
        db.execute(
            "INSERT INTO users (username,full_name,password,role,permissions,active,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (username, full_name, password, role, json.dumps(permissions), 1, now, now),
        )
    return {username: full_name for username, full_name, *_ in USERS}


def log(db: sqlite3.Connection, username: str, full_name: str, action: str, target: str, target_id: int, detail: str, at: str) -> None:
    db.execute(
        "INSERT INTO audit_logs (username,full_name,role,action,target_type,target_id,detail,created_at) VALUES (?,?,?,?,?,?,?,?)",
        (username, full_name, "physician" if username != "admin" else "admin", action, target, target_id, detail, at),
    )


def z_status(value: float, normal: str, moderate: str, severe: str) -> str:
    return severe if value < -3 else moderate if value < -2 else normal


def seed_cinus(db: sqlite3.Connection, users: dict[str, str], now: str) -> None:
    base = date(2026, 8, 24)
    for i, (first, last, sex, mother) in enumerate(CHILDREN, 1):
        age_months = 5 + (i * 7) % 55
        dob = base - timedelta(days=age_months * 30 + (i % 13))
        registrar = users["child_reg"] if i % 3 else users["clinic_lead"]
        code = f"CIN-2026-{i:04d}"
        db.execute(
            "INSERT INTO children (child_code,first_name,last_name,sex,date_of_birth,mother_name,phone,region,woreda,kebele,household_id,registration_date,recorded_by) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (code, first, last, sex, dob.isoformat(), mother, f"09{10 + i % 8} {220 + i:03d} {110 + i:03d}", "Amhara", "Bahir Dar", f"{(i % 16) + 1:02d}", f"HH-{3000+i:04d}", (base - timedelta(days=18 - i % 9)).isoformat(), registrar),
        )
        child_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        log(db, "child_reg" if i % 3 else "clinic_lead", registrar, "create_child", "child", child_id, f"{first} {last} registered", now)
        visit_count = 0 if i in (6, 17, 28) else 1 + (1 if i % 4 == 0 else 0)
        for n in range(visit_count):
            visit_date = base - timedelta(days=(visit_count - n - 1) * 28 + (i % 6))
            age = max(0, (visit_date.year - dob.year) * 12 + visit_date.month - dob.month)
            result = "sam" if i % 13 == 0 and n == visit_count - 1 else "mam" if i % 5 == 0 and n == visit_count - 1 else "normal"
            muac = 10.9 if result == "sam" else 12.0 if result == "mam" else 13.2 + (i % 5) / 10
            waz = -3.3 if result == "sam" else -2.4 if result == "mam" else -1.0 + (i % 4) / 10
            whz = -3.2 if result == "sam" else -2.3 if result == "mam" else -0.8
            height = min(118, 59 + age * 0.9)
            weight = round(5.6 + age * 0.23 - (1.1 if result == "mam" else 2.0 if result == "sam" else 0), 1)
            worker_user = "followup" if i % 4 else "clinic_lead"
            worker = users[worker_user]
            cur = db.execute(
                "INSERT INTO visits (child_id,visit_date,age_months,weight,height,muac,edema,health_worker,created_at,recorded_by) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (child_id, visit_date.isoformat(), age, weight, round(height, 1), round(muac, 1), int(result == "sam" and i % 2 == 0), worker, now, worker),
            )
            visit_id = cur.lastrowid
            db.execute(
                "INSERT INTO growth_assessments (visit_id,waz,haz,whz,underweight_status,stunting_status,wasting_status,generated_at) VALUES (?,?,?,?,?,?,?,?)",
                (visit_id, waz, -1.1 + (i % 3) / 10, whz, z_status(waz, "Normal", "Moderate underweight", "Severe underweight"), "Normal", z_status(whz, "Normal", "Moderate wasting", "Severe wasting"), now),
            )
            db.execute("INSERT INTO nutrition_screenings (visit_id,screening_date,result,referral) VALUES (?,?,?,?)", (visit_id, visit_date.isoformat(), result, "Routine counselling" if result == "normal" else "Priority nutrition follow-up"))
            dev = "cdd" if i % 14 == 0 else "sdd" if i % 6 == 0 else "ndd"
            db.execute("INSERT INTO development_screenings (child_id,visit_id,date,result,notes) VALUES (?,?,?,?,?)", (child_id, visit_id, visit_date.isoformat(), dev, "Milestones reviewed with caregiver"))
            if age >= 6 and (i + n) % 2 == 0:
                db.execute("INSERT INTO vitamin_a (child_id,visit_id,dose_number,date_given,provider) VALUES (?,?,?,?,?)", (child_id, visit_id, 1 + (i % 2), visit_date.isoformat(), worker))
            if age >= 24 and i % 3 == 0:
                db.execute("INSERT INTO deworming (child_id,visit_id,dose_number,date_given,provider) VALUES (?,?,?,?,?)", (child_id, visit_id, 1, visit_date.isoformat(), worker))
            log(db, worker_user, worker, "create_visit", "visit", visit_id, f"CINUS follow-up for {code}", now)


def anc_values(start: date, contacts: int, high_risk: bool) -> dict[str, str]:
    anc: dict[str, str] = {}
    for c in range(1, contacts + 1):
        d = start + timedelta(days=(c - 1) * 28)
        anc.update({
            f"{c}Date of contact": d.isoformat(),
            f"{c}Gestational age": f"{10 + c * 4} weeks",
            f"{c}Present pregnancy history / complaint": "No complaint" if not high_risk else "Headache reviewed; danger signs counselled",
            f"{c}General appearance": "Well appearing",
            f"{c}Blood pressure": "142/92" if high_risk and c in (1, 4, 6) else "112/72",
            f"{c}Weight": f"{54 + c + (2 if high_risk else 0)} kg",
            f"{c}Maternal MUAC (cm)": "22.4" if high_risk and c % 2 == 0 else "24.1",
            f"{c}Iron and folic acid dose": "Daily IFA advised",
            f"{c}Malaria prevention / ITN": "Counselled / ITN advised",
            f"{c}Nutrition / healthy eating": "Counselled",
            f"{c}Assessment / danger signs identified": "High-risk follow-up" if high_risk else "No danger signs identified",
            f"{c}Action taken": "Physician review and close follow-up" if high_risk else "Routine ANC care",
            f"{c}Next appointment": (d + timedelta(days=28)).isoformat(),
            f"{c}Provider name and signature": "Marta Girma",
        })
        if c >= 2:
            anc[f"{c}Fetal heart beat"] = "144 bpm"
        if c in (1, 3, 6):
            anc[f"{c}Haemoglobin"] = "12.1 g/dL"
            anc[f"{c}Urine test"] = "Negative"
        if c in (1, 4, 5):
            anc[f"{c}RPR / VDRL"] = "Non-reactive"
            anc[f"{c}HIV PITC - pregnant client"] = "Negative"
        if c == 3:
            anc[f"{c}75 g oral glucose test"] = "Normal"
        if c >= 5:
            anc[f"{c}IFA 90+ received"] = "Yes"
    return anc


def labor_values(admit: date) -> dict[str, object]:
    observations = []
    for hour, cervix in ((0, 4), (2, 5), (4, 7)):
        observations.append({"time": f"{7 + hour:02d}:30", "hour": str(hour), "fhr": str(140 + hour), "amniotic_fluid": "Clear", "moulding": "0", "cervix": str(cervix), "descent": str(min(5, cervix - 2)), "contractions": "3", "contraction_duration": "40", "pulse": "82", "systolic": "118", "diastolic": "74", "temperature": "36.7", "urine_protein": "Negative", "urine_acetone": "Negative"})
    return {"admission_date": admit.isoformat(), "admission_time": "07:30", "ruptured_membranes": "Intact", "ruptured_hours": "0", "observations": observations, "assessment": "Labor progressing well", "plan": "Continue partograph monitoring", "supportive_care": "Companion, fluids and mobility supported", "initials": "AW"}


def delivery_values(delivery_date: date, i: int) -> dict[str, str]:
    return {"delivery_date": delivery_date.isoformat(), "delivery_time": "14:10", "place_of_delivery": "Facility", "birth_weight": str(2850 + (i % 9) * 90), "length": "50", "pph_occurred": "No", "birth_notification_type": "Institutional", "death_notification_type": "None", "bcg_date": delivery_date.isoformat(), "opv0_date": delivery_date.isoformat(), "feeding_ebf": "Yes", "feeding_erf": "No", "arv_mother": "Not applicable", "known_hiv_positive": "No", "new_hiv_positive": "No", "arv_newborn": "Not applicable", "remark": "Stable mother and newborn", "delivered_by": "Almaz Worku", "signature": "Almaz Worku", "Mode of delivery": ["C/Section"] if i % 11 == 0 else ["SVD"], "AMTSL uterotonic": ["Oxytocin"], "Placenta": ["Complete"], "Newborn": ["Single", "Alive"], "Sex": ["Female" if i % 2 else "Male"], "Newborn care": ["Vitamin K", "Skin-to-skin contact", "HBV birth dose"]}


def birth_notification(card: dict[str, object], delivery: dict[str, str], i: int) -> dict[str, object]:
    twins = i in (8, 22)
    children = []
    for n in range(2 if twins else 1):
        children.append({"child_name": f"Baby {n + 1} of {card['client_name']}", "birth_weight": str(int(delivery["birth_weight"]) - n * 180), "sex": "Female" if (i + n) % 2 else "Male", "birth_type": "Twin / multiple" if twins else "Single", "outcome": "Stillbirth" if i == 26 and n == 0 else "Live birth", "register_cinus": n == 0, "cinus_child_id": "", "cinus_child_code": ""})
    return {"serial": f"BN-2026-{i:04d}", "to": "Bahir Dar city civil registration", "kebele": card["kebele"], "place": "Hospital", "ownership": "Government", "facility": card["facility_name"], "region": "Amhara", "zone": "Bahir Dar", "woreda": card["woreda"], "house_no": f"H-{400+i}", "mother_phone": card["phone"], "mother_address": f"{card['woreda']} kebele {card['kebele']}", "mother_name": card["client_name"], "mother_age": card["age"], "birth_date": delivery["delivery_date"], "birth_time": delivery["delivery_time"], "delivery_type": "C/Section" if "C/Section" in delivery["Mode of delivery"] else "SVD / Normal", "birth_count": str(len(children)), "birth_notification_type": "Institutional", "death_notification_type": "None", "attendant": "Almaz Worku", "qualification": "Skilled professional", "attendant_date": delivery["delivery_date"], "attendant_signature": "Almaz Worku", "issued_by": "Hana Wolde", "issued_date": delivery["delivery_date"], "issued_signature": "Hana Wolde", "children": children}


def postpartum_values(delivery_date: date, periods: int) -> dict[str, str]:
    labels = [("24 hours", 1), ("25-48 hours", 2), ("49-72 hours", 3), ("73 hours-7 days", 6), ("8-42 days", 28)]
    data: dict[str, str] = {}
    for label, offset in labels[:periods]:
        data.update({label + "Date": (delivery_date + timedelta(days=offset)).isoformat(), label + "BP": "116/72", label + "PR / RR": "82 / 18", label + "Temperature": "36.6", label + "Maternal MUAC (cm)": "24.0", label + "Uterus contracted / PPH assessment": "Contracted; no PPH", label + "Baby breathing": "Normal", label + "Baby breastfeeding": "Effective breastfeeding", label + "Baby weight (g)": "3020", label + "HIV tested": "Yes", label + "HIV test result": "Negative", label + "Action taken": "Routine postpartum care", label + "Remark": "Stable"})
    return data


def seed_rh(db: sqlite3.Connection, users: dict[str, str], now: str) -> None:
    for i, name in enumerate(MOTHERS, 1):
        start = date(2026, 1, 10) + timedelta(days=i * 5)
        stage = i % 6
        high_risk = i % 5 in (0, 1)
        contacts = 1 if stage == 0 else 3 if stage == 1 else 6 if stage == 2 else 8
        delivery_date = date(2026, 8, 2) + timedelta(days=i % 24)
        card = {"facility_name": "Kidanemihiret", "card_date": start.isoformat(), "anc_reg_no": f"ANC-2026-{i:04d}", "mrn": f"RH-2026-{i:04d}", "client_name": name, "age": 17 + (i * 3) % 25, "phone": f"09{11 + i % 7} {300 + i:03d} {700 + i:03d}", "woreda": "Bahir Dar", "kebele": f"{(i % 16) + 1:02d}", "lnmp": (start - timedelta(days=70)).isoformat(), "edd": (start + timedelta(days=210)).isoformat(), "gravida": 1 + i % 5, "para": i % 4, "children_alive": i % 4, "marital_status": "Married", "risk_answers": {}, "sections": {"anc": anc_values(start, contacts, high_risk), "labor": {}, "delivery": {}, "postpartum": {}, "_meta": {"last_recorded_by": users["rh_registrar"], "section_recorded_by": {"clients": {"name": users["rh_registrar"], "at": now}}, "anc_recorded_by": {}, "anc_submitted": {}}}, "care_status": "closed" if i % 7 in (0, 3) else "open", "closed_at": "", "closure_note": ""}
        if card["age"] < 18:
            card["risk_answers"]["Age less than 18 years"] = True
        if card["age"] > 35:
            card["risk_answers"]["Age more than 35 years"] = True
        if high_risk:
            card["risk_answers"]["Previous hypertension / pre-eclampsia / eclampsia"] = True
        meta = card["sections"]["_meta"]
        for c in range(1, contacts + 1):
            meta["anc_recorded_by"][str(c)] = {"name": users["anc_provider"] if c % 2 else users["clinic_lead"], "at": (start + timedelta(days=(c - 1) * 28)).isoformat()}
            if c < contacts or stage in (2, 3, 4, 5):
                meta["anc_submitted"][str(c)] = True
        if stage >= 3:
            card["sections"]["labor"] = labor_values(delivery_date)
            meta["labor_submitted"] = True
            meta["section_recorded_by"]["labor"] = {"name": users["delivery_provider"], "at": delivery_date.isoformat()}
        if stage >= 4:
            card["sections"]["delivery"] = delivery_values(delivery_date, i)
            card["sections"]["birth_notification"] = birth_notification(card, card["sections"]["delivery"], i)
            meta["delivery_submitted"] = True
            meta["birth_notification_submitted"] = True
            meta["section_recorded_by"]["delivery"] = {"name": users["delivery_provider"], "at": delivery_date.isoformat()}
            meta["section_recorded_by"]["birth_notification"] = {"name": users["rh_registrar"], "at": delivery_date.isoformat()}
        if stage == 5 or card["care_status"] == "closed":
            card["sections"]["postpartum"] = postpartum_values(delivery_date, 5 if i % 2 else 3)
            meta["postpartum_submitted"] = {p: True for p in ("24 hours", "25-48 hours", "49-72 hours", "73 hours-7 days", "8-42 days") if p + "Date" in card["sections"]["postpartum"]}
            meta["section_recorded_by"]["postpartum"] = {"name": users["postnatal_provider"], "at": (delivery_date + timedelta(days=2)).isoformat()}
        if card["care_status"] == "closed":
            card["closed_at"] = (delivery_date + timedelta(days=42)).isoformat()
            card["closure_note"] = "Maternal care cycle closed after documented follow-up"
        cur = db.execute(
            "INSERT INTO rh_cards (mrn,client_name,facility_name,card_date,payload,created_at,updated_at,recorded_by) VALUES (?,?,?,?,?,?,?,?)",
            (card["mrn"], card["client_name"], card["facility_name"], card["card_date"], json.dumps(card), now, now, users["rh_registrar"]),
        )
        log(db, "rh_registrar", users["rh_registrar"], "create_rh_card", "rh_card", cur.lastrowid, f"{name} registered", now)
        if contacts:
            log(db, "anc_provider", users["anc_provider"], "record_anc", "rh_card", cur.lastrowid, f"{contacts} ANC contact(s) recorded", now)
        if stage >= 4:
            log(db, "delivery_provider", users["delivery_provider"], "record_delivery", "rh_card", cur.lastrowid, "Delivery and birth notification recorded", now)


def seed_database(db_path=DB):
    with sqlite3.connect(db_path) as db:
        db.row_factory = sqlite3.Row
        db.execute("CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        current = db.execute("SELECT value FROM app_settings WHERE key='seed_version'").fetchone()
        if current and current["value"] == SEED_VERSION:
            return {"seed_version": SEED_VERSION, "status": "already seeded"}
        if os.environ.get("ALLOW_DEMO_DATA_RESET") != "1":
            return {"seed_version": SEED_VERSION, "status": "reset skipped; set ALLOW_DEMO_DATA_RESET=1 to replace local demo data"}
        backup = Path(db_path).with_suffix(f".backup-{datetime.now().strftime('%Y%m%d%H%M%S')}.db")
        shutil.copy2(db_path, backup)
        now = datetime.now().isoformat(timespec="seconds")
        reset_clinical_data(db)
        users = seed_users(db, now)
        seed_cinus(db, users, now)
        seed_rh(db, users, now)
        db.execute("INSERT OR REPLACE INTO app_settings (key,value) VALUES ('seed_version',?)", (SEED_VERSION,))
        db.commit()
        counts = {table: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ("users", "children", "visits", "rh_cards", "audit_logs")}
        counts["backup"] = str(backup)
        return counts


if __name__ == "__main__":
    print(seed_database())
