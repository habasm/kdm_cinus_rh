"""Idempotently add a larger, fully populated demo registry to clinic.db."""
import json
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / "clinic.db"
NOW = datetime.now().isoformat(timespec="seconds")

CHILD_NAMES = [
    ("Abel", "Girma", "Male", "2024-01-14", "Marta Girma"), ("Sofia", "Kebede", "Female", "2025-03-09", "Rahel Kebede"),
    ("Henok", "Mulu", "Male", "2023-10-21", "Selam Mulu"), ("Ruth", "Tadesse", "Female", "2024-06-02", "Hana Tadesse"),
    ("Yonatan", "Alemu", "Male", "2025-07-18", "Mimi Alemu"), ("Meron", "Desta", "Female", "2024-09-25", "Liya Desta"),
    ("Samuel", "Worku", "Male", "2022-11-11", "Almaz Worku"), ("Bethel", "Fikadu", "Female", "2025-01-05", "Mekdes Fikadu"),
    ("Kaleb", "Tesfaye", "Male", "2023-05-28", "Selam Tesfaye"), ("Saron", "Abebe", "Female", "2024-12-16", "Meseret Abebe"),
    ("Dani", "Haile", "Male", "2025-06-30", "Eden Haile"), ("Mahi", "Demissie", "Female", "2023-08-07", "Tigist Demissie"),
]

def add_children(db):
    for i, (first, last, sex, dob, mother) in enumerate(CHILD_NAMES, 201):
        code = f"CIN-2026-{i:04d}"
        db.execute("INSERT OR IGNORE INTO children (child_code,first_name,last_name,sex,date_of_birth,mother_name,phone,region,woreda,kebele,household_id,registration_date) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                   (code, first, last, sex, dob, mother, f"0910 220 {i:03d}", "Amhara", "Bahir Dar", f"{(i % 14)+1:02d}", f"HH-{i:04d}", NOW))
        child = db.execute("SELECT id,date_of_birth FROM children WHERE child_code=?", (code,)).fetchone()
        for n, (day, weight, height, muac, result, dev) in enumerate((("2026-06-10", 7.2 + (i % 8), 66 + (i % 16), 12.3 + (i % 8)/10, "normal", "ndd"), ("2026-08-18", 7.8 + (i % 8), 68 + (i % 16), 12.0 + (i % 8)/10, "mam" if i % 5 == 0 else "normal", "sdd" if i % 4 == 0 else "ndd"))):
            if db.execute("SELECT 1 FROM visits WHERE child_id=? AND visit_date=?", (child[0], day)).fetchone():
                continue
            age = max(0, (int(day[:4])-int(child[1][:4]))*12 + int(day[5:7])-int(child[1][5:7]))
            cur = db.execute("INSERT INTO visits (child_id,visit_date,age_months,weight,height,muac,edema,health_worker,created_at) VALUES (?,?,?,?,?,?,?,?,?)", (child[0], day, age, weight, height, muac, int(result == "sam"), "Marta, HEW", NOW))
            vid = cur.lastrowid
            wasting = "Moderate wasting" if result == "mam" else "Normal"
            db.execute("INSERT INTO growth_assessments (visit_id,waz,haz,whz,underweight_status,stunting_status,wasting_status,generated_at) VALUES (?,?,?,?,?,?,?,?)", (vid, -1.2 if result == "normal" else -2.1, -0.8, -1.0, "Normal" if result == "normal" else "Moderate underweight", "Normal", wasting, NOW))
            db.execute("INSERT INTO nutrition_screenings (visit_id,screening_date,result,referral) VALUES (?,?,?,?)", (vid, day, result, "Nutrition counselling" if result == "normal" else "Priority nutrition follow-up"))
            db.execute("INSERT INTO development_screenings (child_id,visit_id,date,result,notes) VALUES (?,?,?,?,?)", (child[0], vid, day, dev, "Caregiver counselled and milestones reviewed"))
            if n == 1:
                db.execute("INSERT INTO vitamin_a (child_id,visit_id,dose_number,date_given,provider) VALUES (?,?,?,?,?)", (child[0], vid, 1, day, "Marta, HEW"))
                if age >= 24:
                    db.execute("INSERT INTO deworming (child_id,visit_id,dose_number,date_given,provider) VALUES (?,?,?,?,?)", (child[0], vid, 1, day, "Marta, HEW"))

def add_rh_cards(db):
    names = ["Marta Girma", "Rahel Kebede", "Selam Mulu", "Hana Tadesse", "Mimi Alemu", "Liya Desta", "Almaz Worku", "Mekdes Fikadu", "Selam Tesfaye", "Meseret Abebe", "Eden Haile", "Tigist Demissie"]
    for i, name in enumerate(names, 201):
        mrn = f"RH-2026-{i:04d}"
        risk = {} if i % 4 == 0 else ({"Age more than 35 years": True} if i % 4 == 1 else ({"Previous hypertension / pre-eclampsia / eclampsia": True} if i % 4 == 2 else {"Age less than 18 years": True}))
        start = date(2026, 4, 1) + timedelta(days=(i-201)*2)
        anc = {}
        for contact in range(1, 9):
            prefix = str(contact)
            anc.update({prefix+"Date of contact": (start + timedelta(days=(contact-1)*21)).isoformat(), prefix+"Gestational age": f"{10+contact*4} weeks", prefix+"Blood pressure": "112/72 mm Hg", prefix+"Weight": f"{58+contact//3} kg", prefix+"Fetal heart beat": "146 bpm", prefix+"Assessment": "Routine ANC; no danger signs", prefix+"Action taken": "IFA, calcium and counselling", prefix+"Next appointment": (start + timedelta(days=contact*21)).isoformat()})
        delivery_date = date(2026, 8, 20) + timedelta(days=(i-201) % 8)
        payload = {"facility_name":"Kidanemihiret", "card_date":start.isoformat(), "anc_reg_no":f"ANC-2026-{i:04d}", "mrn":mrn, "client_name":name, "age":22+(i%16), "phone":f"0911 300 {i:03d}", "woreda":"Bahir Dar", "kebele":f"{(i%14)+1:02d}", "lnmp":(start-timedelta(days=70)).isoformat(), "edd":(start+timedelta(days=210)).isoformat(), "gravida":1+(i%4), "para":i%3, "children_alive":i%3, "marital_status":"Married", "risk_answers":risk, "sections":{"anc":anc, "labor":{"Date of admission":delivery_date.isoformat(),"Time of admission":"07:30","Fetal heart rate":"144 bpm","Cervical dilation":"6 cm","Blood pressure":"118/74","Temperature":"36.7 C","Urine protein":"Nil","Drugs / IV fluids":"Ringer's lactate"}, "delivery":{"Delivery date":delivery_date.isoformat(),"Delivery time":"14:10","Mode of delivery":"SVD","Placenta status":"Complete","Newborn number":"Single","Newborn status":"Alive","Apgar score":"8/10, 9/10","Sex":"Female" if i%2 else "Male","Birth weight (g)":str(3000+i%400),"Length (cm)":"50","Term / preterm":"Term","BCG date":delivery_date.isoformat(),"OPV 0 date":delivery_date.isoformat(),"HBV birth dose":"Given","Vitamin K":"Given","Complications":"None","Delivered by":"Sr. Almaz Worku"}, "postpartum":{}}}
        for period, offset in (("24 hours",1),("25–48 hours",2),("49–72 hours",3),("73 hours–7 days",6),("8–42 days",28)):
            d=(delivery_date+timedelta(days=offset)).isoformat()
            payload["sections"]["postpartum"].update({period+"Date":d,period+"BP":"116/72",period+"Temperature":"36.6 C",period+"Uterus / PPH":"Firm; no PPH",period+"Breastfeeding":"Exclusive breastfeeding",period+"Baby breathing":"Normal",period+"Baby weight":str(2950+i%300)+" g",period+"Action taken":"Routine follow-up and counselling",period+"Remark":"Mother and baby well"})
        db.execute("INSERT OR IGNORE INTO rh_cards (mrn,client_name,facility_name,card_date,payload,created_at,updated_at) VALUES (?,?,?,?,?,?,?)", (mrn,name,"Kidanemihiret",start.isoformat(),json.dumps(payload),NOW,NOW))

def seed_database(db_path=DB):
    """Top up the demo registry; safe to call during every server startup."""
    with sqlite3.connect(db_path) as db:
        add_children(db)
        add_rh_cards(db)
        db.commit()
        return {table: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ("children", "visits", "growth_assessments", "nutrition_screenings", "development_screenings", "rh_cards")}


if __name__ == "__main__":
    print(seed_database())
