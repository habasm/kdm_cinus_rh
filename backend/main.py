from __future__ import annotations

import json
import sqlite3
from calendar import monthrange
from io import BytesIO
from contextlib import closing
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pygrowup import Observation
from pygrowup.exceptions import PyGrowUpException
from pydantic import BaseModel, Field
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from pypdf import PdfReader, PdfWriter

try:
    from .seed_more_records import seed_database as seed_more_demo_records
except ImportError:
    from seed_more_records import seed_database as seed_more_demo_records

ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / "clinic.db"
DIST = ROOT / "frontend" / "dist"

app = FastAPI(title="CINUS Clinic Reporting")


@app.exception_handler(Exception)
async def api_unexpected_error(request: Request, error: Exception) -> JSONResponse:
    """Return safe JSON to the user instead of an internal server-error page."""
    return JSONResponse(status_code=500, content={"detail": "The request could not be completed. Check the entered values and try again."})
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class PatientInput(BaseModel):
    full_name: str
    sex: str
    age: int = Field(ge=0, le=130)
    phone: str = ""
    woreda: str = ""
    kebele: str = ""
    mrn: str | None = None


class MaternalInput(BaseModel):
    patient_id: int
    gravida: int = Field(ge=1)
    para: int = Field(ge=0)
    lmp: str = ""
    edd: str = ""
    gestational_age: int = Field(ge=0, le=45)
    contact_date: str = ""
    blood_pressure: str = ""
    weight: str = ""
    fetal_heart_rate: str = ""
    risk_flags: list[str] = []
    services: list[str] = []
    assessment: str = ""
    action_taken: str = ""
    next_appointment: str = ""

class RHCardInput(BaseModel):
    facility_name: str = "Kidanemihiret"
    card_date: str = ""
    anc_reg_no: str = ""
    mrn: str
    client_name: str
    age: int = Field(ge=10, le=65)
    phone: str = ""
    woreda: str = "Bahir Dar"
    kebele: str = ""
    lnmp: str = ""
    edd: str = ""
    gravida: int = Field(default=1, ge=1)
    para: int = Field(default=0, ge=0)
    children_alive: int = Field(default=0, ge=0)
    marital_status: str = ""
    risk_answers: dict[str, bool] = {}
    sections: dict[str, Any] = {}
    care_status: str = "open"
    closed_at: str = ""
    closure_note: str = ""


class NutritionInput(BaseModel):
    facility_name: str = "Kidanemihiret"
    woreda: str = ""
    report_month: str
    gmp_normal_0_5: int = 0
    gmp_moderate_0_5: int = 0
    gmp_severe_0_5: int = 0
    gmp_normal_6_23: int = 0
    gmp_moderate_6_23: int = 0
    gmp_severe_6_23: int = 0
    screen_normal: int = 0
    mam: int = 0
    sam: int = 0
    vitamin_a_one: int = 0
    vitamin_a_two: int = 0
    deworming_one: int = 0
    deworming_two: int = 0
    confirmed_delay: int = 0
    suspected_delay: int = 0
    no_delay: int = 0


class ChildServiceInput(BaseModel):
    patient_id: int
    service_date: str
    age_months: int = Field(ge=0, le=59)
    gmp_status: str = ""  # normal, moderate, severe
    nutrition_status: str = ""  # normal, mam, sam
    vitamin_a_doses: int = Field(default=0, ge=0, le=2)
    deworming_doses: int = Field(default=0, ge=0, le=2)
    developmental_status: str = ""  # cdd, sdd, ndd


class ChildInput(BaseModel):
    first_name: str
    last_name: str
    sex: str
    date_of_birth: str
    mother_name: str = ""
    phone: str = ""
    region: str = "Amhara"
    woreda: str = "Bahir Dar"
    kebele: str = ""
    household_id: str = ""


class VisitInput(BaseModel):
    child_id: int
    visit_date: str
    weight: float = Field(ge=0, le=50)
    height: float = Field(ge=0, le=150)
    muac: float = Field(ge=0, le=40)
    edema: bool = False
    health_worker: str = ""
    # Calculated server-side from the child's sex, date of birth and measurements.
    waz: float | None = None
    haz: float | None = None
    whz: float | None = None
    nutrition_result: str = "normal"
    referral: str = ""
    vitamin_a_dose: int = Field(default=0, ge=0, le=2)
    deworming_dose: int = Field(default=0, ge=0, le=2)
    developmental_result: str = "ndd"
    development_notes: str = ""


def db() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def rows(query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with closing(db()) as connection:
        return [dict(row) for row in connection.execute(query, params).fetchall()]


def demo_anc_contacts(start_date: str, high_risk: bool = False) -> dict[str, str]:
    """Complete eight-contact test data matching the RH card contents-of-care rows."""
    start = date.fromisoformat(start_date)
    weeks = [11, 20, 26, 30, 34, 36, 38, 40]
    offsets = [0, 63, 105, 133, 161, 175, 189, 203]
    weights = [58.0, 60.1, 62.0, 63.4, 65.0, 66.0, 67.0, 67.8]
    result: dict[str, str] = {}
    for index, (week, offset, weight) in enumerate(zip(weeks, offsets, weights), 1):
        prefix = str(index)
        contact_date = start + timedelta(days=offset)
        next_date = start + timedelta(days=offsets[index]) if index < 8 else contact_date + timedelta(days=7)
        systolic = 138 if high_risk and index in (1, 4, 6) else 110 + index
        diastolic = 88 if high_risk and index in (1, 4, 6) else 68 + (index % 4) * 2
        values = {
            "Date of contact": contact_date.isoformat(), "Gestational age": f"{week} weeks",
            "Present pregnancy history / complaint": "No danger signs; fetal movement present" if week >= 20 else "Mild morning nausea; no danger signs",
            "Family / social history": "Lives with family; no tobacco or alcohol" if index == 1 else "",
            "General appearance": "Well, stable", "Blood pressure": f"{systolic}/{diastolic} mm Hg", "Weight": f"{weight:.1f} kg",
            "Pallor": "Absent", "Breast": "Normal", "Chest": "Clear",
            "Fundal height (weeks)": "Not palpable" if index == 1 else str(week),
            "Fetal heart beat": "Not detected" if index == 1 else f"{142 + index % 4} bpm",
            "Presentation": "Not assessed" if week < 34 else "Cephalic", "Pelvic assessment": "Not indicated",
            "Ultrasound": "Viable singleton pregnancy" if index in (1, 3) else "Not scheduled",
            "Haemoglobin": "12.1 g/dL" if index == 1 else "11.8 g/dL" if index == 5 else "Not due",
            "Blood group and Rh": "O positive" if index == 1 else "Previously recorded",
            "RPR / VDRL": "Non-reactive" if index in (1, 5) else "Not due",
            "HIV PITC - pregnant client": "Negative; counselled" if index in (1, 5) else "Status reviewed",
            "HIV PITC - partner": "Negative" if index == 2 else "Counselling offered",
            "HBsAg": "Negative" if index == 1 else "Previously recorded", "Urine test": "Normal; no protein/glucose",
            "Active TB screening": "No symptoms", "Indirect Coombs test": "Not applicable - Rh positive",
            "75 g oral glucose test": "Normal" if index == 3 and not high_risk else "Monitoring continued" if index == 3 else "Not due",
            "Preventive anti-helminthic treatment": "Given" if index == 2 else "Previously given",
            "Malaria prevention / ITN": "ITN use reinforced", "Td vaccination": "Td dose given" if index in (2, 4) else "Status reviewed",
            "Anti-D immunoglobulin": "Not applicable", "Iron and folic acid dose": "30 tablets supplied",
            "ARV treatment type": "Not applicable", "Syphilis treatment": "Not required", "HBV prophylaxis": "Not required",
            "Daily calcium supplementation": "Counselled and supplied",
            "Nutrition / healthy eating": "Counselled", "PMTCT and testing": "Counselled", "Family planning": "Postpartum options discussed",
            "Breastfeeding": "Exclusive breastfeeding counselled", "Hygiene": "Counselled", "Avoid harmful traditional practices": "Counselled",
            "Reduce caffeine intake": "Counselled", "Gender-based violence / IPV": "Screened; no disclosure",
            "Birth preparedness and complication readiness plan": "Transport, companion and emergency plan reviewed",
            "Assessment / danger signs identified": "High-risk follow-up; stable today" if high_risk else "Pregnancy progressing normally",
            "Action taken": "Close BP follow-up and physician review" if high_risk else "Routine ANC care continued",
            "Next appointment": next_date.isoformat(), "Provider name and signature": "Sr. Almaz Worku"
        }
        result.update({prefix + key: value for key, value in values.items()})
    return result


def demo_partograph() -> dict[str, Any]:
    """Representative multi-time labor record for interface and report testing."""
    times = [
        ("06:40", 0, 142, "I", "0", 4, 4, 2, 25, "", "", "Ringer lactate 500 mL", 82, 122, 76, 36.7, "Negative", "Negative", 180),
        ("07:40", 1, 144, "I", "0", 5, 3, 3, 30, "", "", "Ringer lactate continued", 84, 124, 78, 36.8, "Negative", "Negative", 150),
        ("08:40", 2, 140, "C", "+", 6, 3, 3, 35, "", "", "Oral fluids", 86, 126, 78, 36.8, "Trace", "Negative", 140),
        ("09:40", 3, 138, "C", "+", 7, 2, 4, 40, "5 U/L", 10, "Oxytocin started", 88, 128, 80, 36.9, "Trace", "Negative", 120),
        ("10:40", 4, 144, "C", "+", 8, 2, 4, 45, "5 U/L", 20, "Oxytocin continued", 92, 130, 82, 37.0, "Negative", "Negative", 110),
        ("11:40", 5, 146, "C", "++", 9, 1, 5, 50, "5 U/L", 30, "IV fluids maintained", 96, 132, 82, 37.0, "Negative", "Negative", 100),
        ("12:40", 6, 142, "C", "++", 10, 0, 5, 55, "Stopped", 0, "Prepared for delivery", 98, 134, 84, 37.1, "Negative", "Negative", 90),
    ]
    observations = []
    for t in times:
        observations.append(dict(zip(
            ("time","hour","fhr","amniotic_fluid","moulding","cervix","descent","contractions","contraction_duration","oxytocin_ul","drops_min","drugs_fluids","pulse","systolic","diastolic","temperature","urine_protein","urine_acetone","urine_volume"), t
        )))
    return {"admission_date":"2026-08-22","admission_time":"06:40","ruptured_membranes":"Spontaneous at 08:30","ruptured_hours":"4","observations":observations}


def demo_delivery_postpartum() -> tuple[dict[str, Any], dict[str, str]]:
    delivery = {
        "delivery_date":"2026-08-22","delivery_time":"13:18","apgar":"8 at 1 minute; 9 at 5 minutes",
        "birth_weight":"3150","length":"50","bcg_date":"2026-08-23","opv0_date":"2026-08-23",
        "Mode of delivery":["SVD"],"AMTSL uterotonic":["Oxytocin"],"Placenta":["CCT","Complete"],
        "Tear repair":["1st degree"],"Newborn":["Single","Alive"],"Stillbirth":[],"Sex":["Female"],
        "Maturity":["Term"],"Newborn care":["HBV birth dose","Vitamin K","TTC","Skin-to-skin contact"],
        "Obstetric complication action":["Managed"],"Complications":[],"HIV testing accepted":["Yes"],
        "HIV test result":["Negative"],"feeding_ebf":"Started within one hour","feeding_erf":"Not applicable",
        "arv_mother":"Not applicable","arv_newborn":"Not applicable","remark":"Mother and newborn stable",
        "delivered_by":"Sr. Almaz Worku","signature":"A. Worku"
    }
    periods = [
        ("24 hours","2026-08-23","118/74","82 / 18","36.8","Contracted; no PPH","Absent","No anemia","Not applicable","Not indicated","Normal","30 tablets supplied","Given","Normal","Exclusive breastfeeding established","3100","BCG, OPV0, HBV birth dose","Yes","Negative","Not applicable","Not applicable","EBF","No","Counselled - implant planned","Routine postpartum care","Stable; discharged with advice"),
        ("25-48 hours","2026-08-24","116/72","80 / 18","36.7","Well contracted","Absent","No anemia","Not applicable","Not indicated","Normal","Continued","Reinforced","Normal","Feeding well","3080","Birth doses completed","Reviewed","Negative","Not applicable","Not applicable","EBF","No","Method reviewed","Continue routine care","No danger signs"),
        ("49-72 hours","2026-08-25","114/70","78 / 18","36.6","Contracted","Absent","No anemia","Normal lochia","Not indicated","Normal","Continued","Reinforced by phone","Normal","Feeding 8-12 times/day","3120","Up to date","Reviewed","Negative","Not applicable","Not applicable","EBF","No","Counselled","No additional action","Telephone follow-up"),
        ("73 hours-7 days","2026-08-29","112/70","78 / 17","36.6","Involuting normally","Absent","No anemia","Normal lochia","Not indicated","Normal","Continued","Given","Normal","Effective attachment","3250","Up to date","No new test","Negative","Not applicable","Not applicable","EBF","No","Implant appointment made","Routine follow-up","Mother and baby well"),
        ("8-42 days","2026-09-30","110/70","76 / 17","36.5","Normal involution","Absent","No anemia","No abnormal discharge","Normal","Normal","Completed course","Completed","Normal","Exclusive breastfeeding","4300","Vaccination linkage confirmed","Yes","Negative","Not applicable","Not applicable","EBF","No","Implant provided","Discharged from routine PNC","Six-week assessment normal"),
    ]
    row_names = ("Date","BP","PR / RR","Temperature","Uterus contracted / PPH assessment","Dribbling / leaking urine","Anemia","Vaginal discharge after 4 weeks","Pelvic examination if indicated","Breast examination","IFA supplementation","Danger signs, FP, hygiene, nutrition, EPI, ITN and breastfeeding counselling","Baby breathing","Baby breastfeeding","Baby weight (g)","Immunization","HIV tested","HIV test result","ARV treatment for mother (type)","ARV prophylaxis for newborn (type)","Feeding option EBF / RF","Newborn referred to chronic HIV infant care","Family planning counselled / method provided","Action taken","Remark")
    postpartum: dict[str, str] = {}
    for values in periods:
        period, entries = values[0], values[1:]
        postpartum.update({period + row: value for row, value in zip(row_names, entries)})
    return delivery, postpartum


def additional_rh_cards() -> list[dict[str, Any]]:
    """Extra RH-care examples for ANC, labor/delivery, and postpartum testing."""
    names = [
        ("RH-2026-0007", "ANC-2026-0159", "Saron Yilma", 24, "0913 400 721", "03", "2026-04-05", "2027-01-10", 1, 0),
        ("RH-2026-0008", "ANC-2026-0164", "Almaz Demissie", 29, "0914 332 118", "06", "2026-02-18", "2026-11-25", 3, 1),
        ("RH-2026-0009", "ANC-2026-0104", "Frehiwot Tesfaye", 34, "0920 117 456", "12", "2025-12-03", "2026-09-09", 4, 2),
        ("RH-2026-0010", "ANC-2026-0096", "Eden Worku", 26, "0921 663 904", "15", "2025-11-11", "2026-08-18", 2, 1),
        ("RH-2026-0011", "ANC-2026-0087", "Liya Abera", 31, "0935 777 208", "08", "2025-10-28", "2026-08-04", 3, 2),
        ("RH-2026-0012", "ANC-2026-0171", "Mahilet Fikadu", 19, "0940 219 833", "10", "2026-05-01", "2027-02-05", 1, 0),
        ("RH-2026-0013", "ANC-2026-0149", "Yordanos Haile", 38, "0942 506 612", "05", "2026-01-30", "2026-11-06", 5, 4),
        ("RH-2026-0014", "ANC-2026-0117", "Hirut Bekele", 28, "0906 018 742", "01", "2025-12-25", "2026-10-01", 2, 1),
    ]
    cards = []
    for index, (mrn, anc, client_name, age, phone, kebele, lnmp, edd, gravida, para) in enumerate(names):
        card = {
            "facility_name": "Kidanemihiret", "card_date": "2026-08-26", "anc_reg_no": anc,
            "mrn": mrn, "client_name": client_name, "age": age, "phone": phone,
            "woreda": "Bahir Dar", "kebele": kebele, "lnmp": lnmp, "edd": edd,
            "gravida": gravida, "para": para, "children_alive": para, "marital_status": "Married",
            "risk_answers": {}, "sections": {"anc": {}, "labor": {}, "delivery": {}, "postpartum": {}},
        }
        if index in (0, 1, 5, 6, 7):
            card["sections"]["anc"] = demo_anc_contacts("2026-04-01", high_risk=index == 6)
        if index in (2, 3, 4, 7):
            card["sections"]["labor"] = demo_partograph()
            delivery, postpartum = demo_delivery_postpartum()
            delivery["delivery_date"] = "2026-08-18" if index == 3 else "2026-08-04" if index == 4 else "2026-08-26"
            delivery["delivery_time"] = "11:45" if index == 3 else "09:10" if index == 4 else "14:25"
            delivery["birth_weight"] = str(2850 + index * 80)
            delivery["Sex"] = ["Male"] if index in (3, 7) else ["Female"]
            card["sections"]["delivery"] = delivery
            card["sections"]["postpartum"] = postpartum
        if index == 6:
            card["risk_answers"] = {"Age more than 35 years": True, "Previous stillbirth or neonatal death": True}
        cards.append(card)
    return cards


def ensure_additional_rh_cards(connection: sqlite3.Connection) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    for card in additional_rh_cards():
        if connection.execute("SELECT id FROM rh_cards WHERE mrn=?", (card["mrn"],)).fetchone():
            continue
        connection.execute(
            "INSERT INTO rh_cards (mrn,client_name,facility_name,card_date,payload,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
            (card["mrn"], card["client_name"], card["facility_name"], card["card_date"], json.dumps(card), now, now),
        )


def ensure_demo_cinus_records(connection: sqlite3.Connection) -> None:
    """Top up an existing database with a useful, repeatable CINUS demo set."""
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
    for child in children:
        if connection.execute("SELECT 1 FROM children WHERE child_code=?", (child[0],)).fetchone():
            continue
        connection.execute("INSERT INTO children (child_code,first_name,last_name,sex,date_of_birth,mother_name,phone,region,woreda,kebele,household_id,registration_date) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (*child, now))

    visit_plan = {
        "Sami": [("2026-06-12", 10.6, 85.0, 13.1, "normal", "ndd"), ("2026-08-12", 11.2, 87.0, 13.5, "normal", "ndd")],
        "Eden": [("2026-05-20", 7.4, 67.0, 12.5, "normal", "ndd"), ("2026-08-20", 8.1, 70.0, 12.8, "mam", "sdd")],
        "Yonas": [("2026-07-05", 13.0, 99.0, 11.8, "mam", "ndd"), ("2026-08-05", 13.2, 100.0, 11.9, "mam", "ndd")],
        "Hana": [("2026-08-06", 9.5, 76.0, 13.4, "normal", "ndd")],
        "Kalkidan": [("2026-08-15", 6.8, 64.0, 12.9, "normal", "ndd")],
        "Dawit": [("2026-07-18", 15.6, 105.0, 11.4, "sam", "sdd")],
        "Mahi": [("2026-06-28", 10.1, 82.0, 13.0, "normal", "ndd"), ("2026-08-22", 10.7, 84.0, 13.2, "normal", "ndd")],
    }
    for first_name, plans in visit_plan.items():
        child = connection.execute("SELECT * FROM children WHERE first_name=? ORDER BY id DESC LIMIT 1", (first_name,)).fetchone()
        if not child:
            continue
        for visit_date, weight, height, muac, nutrition, development in plans:
            if connection.execute("SELECT 1 FROM visits WHERE child_id=? AND visit_date=?", (child["id"], visit_date)).fetchone():
                continue
            age = age_in_months(child["date_of_birth"], visit_date)
            try:
                scores = calculate_growth_scores(child["sex"], child["date_of_birth"], visit_date, weight, height)
            except Exception:
                scores = {"waz": -1.0, "haz": -1.0, "whz": -1.0}
            cursor = connection.execute("INSERT INTO visits (child_id,visit_date,age_months,weight,height,muac,edema,health_worker,created_at) VALUES (?,?,?,?,?,?,?,?,?)", (child["id"], visit_date, age, weight, height, muac, int(nutrition == "sam"), "Marta, HEW", now))
            visit_id = cursor.lastrowid
            connection.execute("INSERT INTO growth_assessments (visit_id,waz,haz,whz,underweight_status,stunting_status,wasting_status,generated_at) VALUES (?,?,?,?,?,?,?,?)", (visit_id, scores.get("waz", -1.0), scores.get("haz", -1.0), scores.get("whz", -1.0), "Normal", "Normal", "Normal" if nutrition == "normal" else "Moderate wasting", now))
            connection.execute("INSERT INTO nutrition_screenings (visit_id,screening_date,result,referral) VALUES (?,?,?,?)", (visit_id, visit_date, nutrition, "Nutrition counselling" if nutrition == "normal" else "Priority nutrition follow-up"))
            connection.execute("INSERT INTO development_screenings (child_id,visit_id,date,result,notes) VALUES (?,?,?,?,?)", (child["id"], visit_id, visit_date, development, "Development reviewed during follow-up"))
            if age >= 6:
                connection.execute("INSERT INTO vitamin_a (child_id,visit_id,dose_number,date_given,provider) VALUES (?,?,?,?,?)", (child["id"], visit_id, 1, visit_date, "Marta, HEW"))
            if age >= 24:
                connection.execute("INSERT INTO deworming (child_id,visit_id,dose_number,date_given,provider) VALUES (?,?,?,?,?)", (child["id"], visit_id, 1, visit_date, "Marta, HEW"))


def init_db() -> None:
    with closing(db()) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS patients (
              id INTEGER PRIMARY KEY AUTOINCREMENT, mrn TEXT UNIQUE NOT NULL,
              full_name TEXT NOT NULL, sex TEXT NOT NULL, age INTEGER NOT NULL,
              phone TEXT, woreda TEXT, kebele TEXT, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS maternal_records (
              id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER NOT NULL,
              gravida INTEGER, para INTEGER, lmp TEXT, edd TEXT, gestational_age INTEGER,
              contact_date TEXT, blood_pressure TEXT, weight TEXT, fetal_heart_rate TEXT,
              risk_flags TEXT, services TEXT, assessment TEXT, action_taken TEXT,
              next_appointment TEXT, created_at TEXT NOT NULL,
              FOREIGN KEY(patient_id) REFERENCES patients(id)
            );
            CREATE TABLE IF NOT EXISTS rh_cards (
              id INTEGER PRIMARY KEY AUTOINCREMENT, mrn TEXT UNIQUE NOT NULL,
              client_name TEXT NOT NULL, facility_name TEXT NOT NULL, card_date TEXT,
              payload TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS nutrition_reports (
              id INTEGER PRIMARY KEY AUTOINCREMENT, payload TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS child_services (
              id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER NOT NULL,
              service_date TEXT NOT NULL, age_months INTEGER NOT NULL,
              gmp_status TEXT, nutrition_status TEXT, vitamin_a_doses INTEGER NOT NULL DEFAULT 0,
              deworming_doses INTEGER NOT NULL DEFAULT 0, developmental_status TEXT,
              created_at TEXT NOT NULL, FOREIGN KEY(patient_id) REFERENCES patients(id)
            );
            CREATE TABLE IF NOT EXISTS children (
              id INTEGER PRIMARY KEY AUTOINCREMENT, child_code TEXT UNIQUE NOT NULL,
              first_name TEXT NOT NULL, last_name TEXT NOT NULL, sex TEXT NOT NULL,
              date_of_birth TEXT NOT NULL, mother_name TEXT, phone TEXT, region TEXT,
              woreda TEXT, kebele TEXT, household_id TEXT, registration_date TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS visits (
              id INTEGER PRIMARY KEY AUTOINCREMENT, child_id INTEGER NOT NULL, visit_date TEXT NOT NULL,
              age_months INTEGER NOT NULL, weight REAL, height REAL, muac REAL, edema INTEGER NOT NULL,
              health_worker TEXT, created_at TEXT NOT NULL, FOREIGN KEY(child_id) REFERENCES children(id)
            );
            CREATE TABLE IF NOT EXISTS growth_assessments (
              id INTEGER PRIMARY KEY AUTOINCREMENT, visit_id INTEGER UNIQUE NOT NULL, waz REAL, haz REAL, whz REAL,
              underweight_status TEXT, stunting_status TEXT, wasting_status TEXT, generated_at TEXT NOT NULL,
              FOREIGN KEY(visit_id) REFERENCES visits(id)
            );
            CREATE TABLE IF NOT EXISTS nutrition_screenings (
              id INTEGER PRIMARY KEY AUTOINCREMENT, visit_id INTEGER UNIQUE NOT NULL, screening_date TEXT NOT NULL,
              result TEXT NOT NULL, referral TEXT, FOREIGN KEY(visit_id) REFERENCES visits(id)
            );
            CREATE TABLE IF NOT EXISTS vitamin_a (
              id INTEGER PRIMARY KEY AUTOINCREMENT, child_id INTEGER NOT NULL, visit_id INTEGER, dose_number INTEGER NOT NULL,
              date_given TEXT NOT NULL, provider TEXT, FOREIGN KEY(child_id) REFERENCES children(id), FOREIGN KEY(visit_id) REFERENCES visits(id)
            );
            CREATE TABLE IF NOT EXISTS deworming (
              id INTEGER PRIMARY KEY AUTOINCREMENT, child_id INTEGER NOT NULL, visit_id INTEGER, dose_number INTEGER NOT NULL,
              date_given TEXT NOT NULL, provider TEXT, FOREIGN KEY(child_id) REFERENCES children(id), FOREIGN KEY(visit_id) REFERENCES visits(id)
            );
            CREATE TABLE IF NOT EXISTS development_screenings (
              id INTEGER PRIMARY KEY AUTOINCREMENT, child_id INTEGER NOT NULL, visit_id INTEGER UNIQUE, date TEXT NOT NULL,
              result TEXT NOT NULL, notes TEXT, FOREIGN KEY(child_id) REFERENCES children(id), FOREIGN KEY(visit_id) REFERENCES visits(id)
            );
            """
        )
        if connection.execute("SELECT COUNT(*) FROM patients").fetchone()[0] == 0:
            now = datetime.now().isoformat(timespec="seconds")
            patients = [
                ("MRN-2026-0001", "Hana Tadesse", "Female", 26, "0911 234 567", "Bole", "03", now),
                ("MRN-2026-0002", "Mekdes Alemu", "Female", 31, "0922 456 701", "Yeka", "08", now),
                ("MRN-2026-0003", "Abel Girma", "Male", 2, "0933 100 231", "Kolfe Keranio", "11", now),
                ("MRN-2026-0004", "Selamawit Bekele", "Female", 24, "0944 805 112", "Akaki Kaliti", "04", now),
            ]
            connection.executemany(
                "INSERT INTO patients (mrn, full_name, sex, age, phone, woreda, kebele, created_at) VALUES (?,?,?,?,?,?,?,?)",
                patients,
            )
            connection.execute(
                "INSERT INTO maternal_records (patient_id,gravida,para,lmp,edd,gestational_age,contact_date,blood_pressure,weight,fetal_heart_rate,risk_flags,services,assessment,action_taken,next_appointment,created_at) VALUES (1,2,1,'2026-01-10','2026-10-17',32,'2026-08-20','110/70','62 kg','144 bpm','[]','[\"Iron & folic acid\",\"HIV PITC\",\"Nutrition counselling\"]','Stable pregnancy','Routine ANC follow up','2026-09-03',?)",
                (now,),
            )
            seed = NutritionInput(report_month="2026-08", woreda="Bole", gmp_normal_0_5=34, gmp_normal_6_23=86, gmp_moderate_6_23=5, gmp_severe_6_23=1, screen_normal=168, mam=9, sam=2, vitamin_a_one=43, vitamin_a_two=116, deworming_one=72, deworming_two=55, confirmed_delay=1, suspected_delay=4, no_delay=129)
            connection.execute("INSERT INTO nutrition_reports (payload,created_at) VALUES (?,?)", (seed.model_dump_json(), now))
            child_services = [
              (3, "2026-08-03", 18, "normal", "normal", 1, 0, "ndd", now),
              (3, "2026-08-10", 18, "normal", "normal", 0, 0, "ndd", now),
              (3, "2026-08-18", 18, "moderate", "mam", 0, 0, "sdd", now),
            ]
            connection.executemany("INSERT INTO child_services (patient_id,service_date,age_months,gmp_status,nutrition_status,vitamin_a_doses,deworming_doses,developmental_status,created_at) VALUES (?,?,?,?,?,?,?,?,?)", child_services)
        if connection.execute("SELECT COUNT(*) FROM rh_cards").fetchone()[0] == 0:
            now = datetime.now().isoformat(timespec="seconds")
            sample_rh_cards = [
                {"facility_name":"Kidanemihiret","card_date":"2026-08-04","anc_reg_no":"ANC-2026-0141","mrn":"RH-2026-0001","client_name":"Mekdes Alemu","age":27,"phone":"0911 248 630","woreda":"Bahir Dar","kebele":"11","lnmp":"2026-03-02","edd":"2026-12-07","gravida":2,"para":1,"children_alive":1,"marital_status":"Married","risk_answers":{},"sections":{"anc":{"1Date":"2026-05-18","1Gestational age":"11 weeks","1Blood pressure":"110/70","1Weight":"58 kg","1Fetal heart beat":"Not detected","1Assessment":"Stable pregnancy","1Action taken":"Routine ANC counselling","1Next appointment":"2026-07-13","2Date":"2026-07-13","2Gestational age":"19 weeks","2Blood pressure":"112/72","2Weight":"60 kg","2Fetal heart beat":"146 bpm"},"labor":{},"delivery":{},"postpartum":{}}},
                {"facility_name":"Kidanemihiret","card_date":"2026-07-22","anc_reg_no":"ANC-2026-0127","mrn":"RH-2026-0002","client_name":"Tigist Getachew","age":36,"phone":"0922 405 817","woreda":"Bahir Dar","kebele":"04","lnmp":"2026-01-14","edd":"2026-10-21","gravida":4,"para":3,"children_alive":3,"marital_status":"Married","risk_answers":{"Age more than 35 years":True,"Chronic hypertension":True},"sections":{"anc":{"1Date":"2026-03-30","1Gestational age":"10 weeks","1Blood pressure":"142/92","1Weight":"64 kg","1Assessment":"High-risk pregnancy","1Action taken":"Physician review and close follow-up","2Date":"2026-06-08","2Gestational age":"20 weeks","2Blood pressure":"138/88","2Weight":"66 kg","2Fetal heart beat":"148 bpm"},"labor":{},"delivery":{},"postpartum":{}}},
                {"facility_name":"Kidanemihiret","card_date":"2026-08-10","anc_reg_no":"ANC-2026-0148","mrn":"RH-2026-0003","client_name":"Bethlehem Tesfaye","age":22,"phone":"0933 765 214","woreda":"Bahir Dar","kebele":"07","lnmp":"2026-05-11","edd":"2027-02-15","gravida":1,"para":0,"children_alive":0,"marital_status":"Married","risk_answers":{},"sections":{"anc":{"1Date":"2026-07-27","1Gestational age":"11 weeks","1Blood pressure":"108/68","1Weight":"52 kg","1Assessment":"Normal first pregnancy","1Action taken":"IFA and nutrition counselling","1Next appointment":"2026-09-28"},"labor":{},"delivery":{},"postpartum":{}}},
                {"facility_name":"Kidanemihiret","card_date":"2026-06-15","anc_reg_no":"ANC-2026-0099","mrn":"RH-2026-0004","client_name":"Rahel Asmare","age":30,"phone":"0944 316 905","woreda":"Bahir Dar","kebele":"14","lnmp":"2025-11-20","edd":"2026-08-27","gravida":3,"para":2,"children_alive":2,"marital_status":"Married","risk_answers":{"Previous hypertension / pre-eclampsia / eclampsia":True},"sections":{"anc":{"6Date":"2026-07-30","6Gestational age":"36 weeks","6Blood pressure":"124/78","6Weight":"69 kg","6Fetal heart beat":"140 bpm","6Assessment":"Stable; previous obstetric risk","6Next appointment":"2026-08-13"},"labor":{"Date of admission":"2026-08-22","Time of admission":"06:40","Ruptured membranes":"No","Fetal heart rate":"142 bpm","Cervical dilation":"5 cm","Blood pressure":"126/80"},"delivery":{"Delivery date":"2026-08-22","Delivery time":"13:18","Mode of delivery":"SVD","Placenta status":"Complete","Newborn number":"Single","Newborn status":"Alive","Apgar score":"8/10, 9/10","Sex":"Female","Birth weight (g)":"3150","Length (cm)":"50","Term / preterm":"Term","Vitamin K":"Given","Delivered by":"Sr. Almaz Worku"},"postpartum":{"24 hoursDate":"2026-08-23","24 hoursBP":"118/74","24 hoursBaby breathing":"Normal","24 hoursBreastfeeding":"EBF established","24 hoursBaby weight":"3100 g"}}},
                {"facility_name":"Kidanemihiret","card_date":"2026-08-01","anc_reg_no":"ANC-2026-0136","mrn":"RH-2026-0005","client_name":"Selamawit Kebede","age":17,"phone":"0901 882 470","woreda":"Bahir Dar","kebele":"02","lnmp":"2026-02-06","edd":"2026-11-13","gravida":1,"para":0,"children_alive":0,"marital_status":"Married","risk_answers":{"Age less than 18 years":True},"sections":{"anc":{"1Date":"2026-04-23","1Gestational age":"11 weeks","1Blood pressure":"106/66","1Weight":"48 kg","1Assessment":"Adolescent pregnancy","1Action taken":"High-risk ANC and counselling","1Next appointment":"2026-06-26","3Date":"2026-08-07","3Gestational age":"26 weeks","3Blood pressure":"108/68","3Weight":"52 kg","3Fetal heart beat":"150 bpm"},"labor":{},"delivery":{},"postpartum":{}}},
                {"facility_name":"Kidanemihiret","card_date":"2026-07-05","anc_reg_no":"ANC-2026-0112","mrn":"RH-2026-0006","client_name":"Hiwot Mulugeta","age":32,"phone":"0912 536 441","woreda":"Bahir Dar","kebele":"09","lnmp":"2025-12-18","edd":"2026-09-24","gravida":5,"para":2,"children_alive":2,"marital_status":"Married","risk_answers":{"3 or more consecutive spontaneous abortions":True,"Diabetes mellitus":True},"sections":{"anc":{"5Date":"2026-08-13","5Gestational age":"34 weeks","5Blood pressure":"116/74","5Weight":"71 kg","5Fetal heart beat":"144 bpm","5Assessment":"Gestational diabetes follow-up","5Action taken":"Glucose monitoring and referral","5Next appointment":"2026-08-27"},"labor":{},"delivery":{},"postpartum":{}}}
            ]
            sample_rh_cards[0]["sections"]["anc"] = demo_anc_contacts("2026-05-18")
            sample_rh_cards[1]["sections"]["anc"] = demo_anc_contacts("2026-03-30", high_risk=True)
            sample_rh_cards[3]["sections"]["labor"] = demo_partograph()
            sample_rh_cards[3]["sections"]["delivery"], sample_rh_cards[3]["sections"]["postpartum"] = demo_delivery_postpartum()
            connection.executemany(
                "INSERT INTO rh_cards (mrn,client_name,facility_name,card_date,payload,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
                [(card["mrn"],card["client_name"],card["facility_name"],card["card_date"],json.dumps(card),now,now) for card in sample_rh_cards],
            )
        ensure_additional_rh_cards(connection)
        ensure_demo_cinus_records(connection)
        if connection.execute("SELECT COUNT(*) FROM children").fetchone()[0] == 0:
            now = datetime.now().isoformat(timespec="seconds")
            children = [("CIN-2026-0001","Mimi","Abebe","Female","2025-09-10","Meseret Abebe","0912 220 181","Addis Ababa","Bole","04","HH-0041",now),("CIN-2026-0002","Nahom","Kebede","Male","2023-06-18","Saron Kebede","0912 220 182","Addis Ababa","Bole","04","HH-0042",now),("CIN-2026-0003","Liya","Tadesse","Female","2024-12-02","Hana Tadesse","0911 234 567","Addis Ababa","Bole","03","HH-0043",now)]
            connection.executemany("INSERT INTO children (child_code,first_name,last_name,sex,date_of_birth,mother_name,phone,region,woreda,kebele,household_id,registration_date) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", children)
        if connection.execute("SELECT COUNT(*) FROM visits").fetchone()[0] == 0:
            now = datetime.now().isoformat(timespec="seconds")
            child_ids = {row["first_name"]: row["id"] for row in connection.execute("SELECT id,first_name FROM children").fetchall()}
            seeded_visits = [(child_ids["Mimi"],"2026-08-11",11,8.5,73.2,13.7,0,"Meseret, HEW",now),(child_ids["Nahom"],"2026-08-19",38,12.2,94.5,12.1,0,"Meseret, HEW",now),(child_ids["Liya"],"2026-08-23",20,9.9,80.1,13.3,0,"Meseret, HEW",now)]
            connection.executemany("INSERT INTO visits (child_id,visit_date,age_months,weight,height,muac,edema,health_worker,created_at) VALUES (?,?,?,?,?,?,?,?,?)", seeded_visits)
            visit_rows = connection.execute("SELECT id,child_id,visit_date FROM visits ORDER BY id").fetchall()
            for index, visit in enumerate(visit_rows):
                waz = -1.1 if index != 1 else -2.4; result = "normal" if index != 1 else "mam"; dev = "ndd" if index != 1 else "sdd"
                connection.execute("INSERT INTO growth_assessments (visit_id,waz,haz,whz,underweight_status,stunting_status,wasting_status,generated_at) VALUES (?,?,?,?,?,?,?,?)", (visit["id"],waz,-1.0,-1.1,z_status(waz,"Normal","Moderate underweight","Severe underweight"),"Normal","Normal",now))
                connection.execute("INSERT INTO nutrition_screenings (visit_id,screening_date,result,referral) VALUES (?,?,?,?)", (visit["id"],visit["visit_date"],result,"Nutrition counselling" if result == "normal" else "MAM follow-up"))
                connection.execute("INSERT INTO development_screenings (child_id,visit_id,date,result,notes) VALUES (?,?,?,?,?)", (visit["child_id"],visit["id"],visit["visit_date"],dev,""))
                if index < 2: connection.execute("INSERT INTO vitamin_a (child_id,visit_id,dose_number,date_given,provider) VALUES (?,?,?,?,?)", (visit["child_id"],visit["id"],index+1,visit["visit_date"],"Meseret, HEW"))
                if index == 1: connection.execute("INSERT INTO deworming (child_id,visit_id,dose_number,date_given,provider) VALUES (?,?,?,?,?)", (visit["child_id"],visit["id"],1,visit["visit_date"],"Meseret, HEW"))
        if connection.execute("SELECT COUNT(*) FROM child_services").fetchone()[0] == 0:
            now = datetime.now().isoformat(timespec="seconds")
            existing = {row[0] for row in connection.execute("SELECT full_name FROM patients").fetchall()}
            if "Mimi Abebe" not in existing:
                connection.executemany("INSERT INTO patients (mrn,full_name,sex,age,phone,woreda,kebele,created_at) VALUES (?,?,?,?,?,?,?,?)", [("MRN-2026-0005","Mimi Abebe","Female",1,"0912 220 181","Bole","04",now),("MRN-2026-0006","Nahom Kebede","Male",3,"0912 220 182","Bole","04",now)])
            ids = {row["full_name"]: row["id"] for row in connection.execute("SELECT id,full_name FROM patients").fetchall()}
            connection.executemany("INSERT INTO child_services (patient_id,service_date,age_months,gmp_status,nutrition_status,vitamin_a_doses,deworming_doses,developmental_status,created_at) VALUES (?,?,?,?,?,?,?,?,?)", [(ids["Abel Girma"],"2026-08-03",18,"normal","normal",1,0,"ndd",now),(ids["Mimi Abebe"],"2026-08-11",11,"normal","normal",2,0,"ndd",now),(ids["Nahom Kebede"],"2026-08-19",38,"","mam",0,1,"sdd",now)])
        connection.commit()
    # Run after the schema connection is closed so the seeder can safely open
    # its own transaction during every startup.
    seed_more_demo_records(DATABASE)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/api/dashboard")
def dashboard() -> dict[str, Any]:
    patient_count = rows("SELECT COUNT(*) AS count FROM patients")[0]["count"]
    anc_count = rows("SELECT COUNT(*) AS count FROM maternal_records")[0]["count"]
    nutrition_count = rows("SELECT COUNT(*) AS count FROM nutrition_reports")[0]["count"]
    recent = rows("SELECT id,mrn,full_name,sex,age,woreda,created_at FROM patients ORDER BY id DESC LIMIT 5")
    return {"patients": patient_count, "anc_contacts": anc_count, "nutrition_reports": nutrition_count, "recent_patients": recent}


@app.get("/api/patients")
def list_patients() -> list[dict[str, Any]]:
    return rows("SELECT * FROM patients ORDER BY id DESC")


@app.post("/api/patients", status_code=201)
def create_patient(patient: PatientInput) -> dict[str, Any]:
    now = datetime.now().isoformat(timespec="seconds")
    with closing(db()) as connection:
        mrn = patient.mrn or f"MRN-{date.today().year}-{connection.execute('SELECT COUNT(*) FROM patients').fetchone()[0] + 1:04d}"
        try:
            cursor = connection.execute(
                "INSERT INTO patients (mrn,full_name,sex,age,phone,woreda,kebele,created_at) VALUES (?,?,?,?,?,?,?,?)",
                (mrn, patient.full_name, patient.sex, patient.age, patient.phone, patient.woreda, patient.kebele, now),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(409, "MRN already exists")
        connection.commit()
        return dict(connection.execute("SELECT * FROM patients WHERE id=?", (cursor.lastrowid,)).fetchone())


@app.get("/api/maternal-records")
def list_maternal_records() -> list[dict[str, Any]]:
    records = rows("SELECT m.*, p.full_name, p.mrn FROM maternal_records m JOIN patients p ON p.id=m.patient_id ORDER BY m.id DESC")
    for record in records:
        record["risk_flags"] = json.loads(record["risk_flags"] or "[]")
        record["services"] = json.loads(record["services"] or "[]")
    return records


@app.post("/api/maternal-records", status_code=201)
def create_maternal_record(record: MaternalInput) -> dict[str, Any]:
    if not rows("SELECT id FROM patients WHERE id=?", (record.patient_id,)):
        raise HTTPException(404, "Patient not found")
    now = datetime.now().isoformat(timespec="seconds")
    fields = record.model_dump()
    with closing(db()) as connection:
        cursor = connection.execute(
            """INSERT INTO maternal_records (patient_id,gravida,para,lmp,edd,gestational_age,contact_date,blood_pressure,weight,fetal_heart_rate,risk_flags,services,assessment,action_taken,next_appointment,created_at)
            VALUES (:patient_id,:gravida,:para,:lmp,:edd,:gestational_age,:contact_date,:blood_pressure,:weight,:fetal_heart_rate,:risk_flags,:services,:assessment,:action_taken,:next_appointment,:created_at)""",
            {**fields, "risk_flags": json.dumps(fields["risk_flags"]), "services": json.dumps(fields["services"]), "created_at": now},
        )
        connection.commit()
    return {"id": cursor.lastrowid, "message": "ANC contact saved"}

def decode_rh_card(row: dict[str, Any]) -> dict[str, Any]:
    payload = json.loads(row.pop("payload"))
    return {**row, **payload}

@app.get("/api/rh-cards")
def list_rh_cards() -> list[dict[str, Any]]:
    return [decode_rh_card(item) for item in rows("SELECT * FROM rh_cards ORDER BY updated_at DESC")]

@app.get("/api/rh-cards/{card_id}")
def get_rh_card(card_id: int) -> dict[str, Any]:
    found = rows("SELECT * FROM rh_cards WHERE id=?", (card_id,))
    if not found:
        raise HTTPException(404, "Maternal RH card not found")
    return decode_rh_card(found[0])

@app.post("/api/rh-cards", status_code=201)
def create_rh_card(card: RHCardInput) -> dict[str, Any]:
    now = datetime.now().isoformat(timespec="seconds")
    with closing(db()) as connection:
        try:
            cursor = connection.execute("INSERT INTO rh_cards (mrn,client_name,facility_name,card_date,payload,created_at,updated_at) VALUES (?,?,?,?,?,?,?)", (card.mrn,card.client_name,card.facility_name,card.card_date,card.model_dump_json(),now,now))
        except sqlite3.IntegrityError:
            raise HTTPException(409, "An RH card with this MRN already exists")
        connection.commit()
        return {"id": cursor.lastrowid, "message": "Maternal RH card created"}

@app.put("/api/rh-cards/{card_id}")
def update_rh_card(card_id: int, card: RHCardInput) -> dict[str, Any]:
    now = datetime.now().isoformat(timespec="seconds")
    with closing(db()) as connection:
        cursor = connection.execute("UPDATE rh_cards SET mrn=?,client_name=?,facility_name=?,card_date=?,payload=?,updated_at=? WHERE id=?", (card.mrn,card.client_name,card.facility_name,card.card_date,card.model_dump_json(),now,card_id))
        if not cursor.rowcount: raise HTTPException(404, "Maternal RH card not found")
        connection.commit()
    return {"id": card_id, "message": "Maternal RH card updated"}


def create_rh_page1_reference_pdf(card: dict[str, Any]) -> BytesIO:
    """Fill the official MoH page-1 artwork supplied as the RH card reference."""
    template = ROOT / "backend" / "assets" / "rh_card_page1_reference.pdf"
    if not template.exists():
        return create_rh_page1_pdf(card)
    overlay = BytesIO()
    c = canvas.Canvas(overlay, pagesize=A4)
    c.setFillColor(colors.HexColor("#17212b"))
    c.setFont("Helvetica", 8.5)

    def value(raw: Any) -> str:
        return str(raw or "")

    def date_value(raw: Any) -> str:
        raw = value(raw)
        if len(raw) == 10 and raw[4] == "-":
            return f"{raw[8:10]}/{raw[5:7]}/{raw[:4]}"
        return raw

    # The reference page uses underlined blanks; these overlays sit directly on them.
    fields = [
        ("facility_name", 98, 744, 180), ("card_date", 343, 744, 95),
        ("anc_reg_no", 88, 717, 85), ("mrn", 312, 717, 120),
        ("client_name", 98, 691, 148), ("age", 278, 691, 30), ("phone", 389, 691, 62),
        ("woreda", 480, 691, 55), ("kebele", 545, 691, 38),
        ("lnmp", 38, 666, 85), ("edd", 150, 666, 85), ("gravida", 224, 666, 33),
        ("para", 285, 666, 33), ("children_alive", 395, 666, 46), ("marital_status", 548, 666, 28),
    ]
    for key, x, y, width in fields:
        raw = card.get(key)
        text = date_value(raw) if key in {"card_date", "lnmp", "edd"} else value(raw)
        c.setFillColor(colors.white)
        c.rect(x - 2, y - 2, width, 12, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#17212b"))
        c.drawString(x, y, text[:max(1, int(width / 4.2))])

    risk_answers = card.get("risk_answers") or {}
    keys = [
        "Previous stillbirth or neonatal death", "3 or more consecutive spontaneous abortions", "Last baby below 2500 g",
        "Last baby above 4000 g", "Previous hypertension / pre-eclampsia / eclampsia", "Previous reproductive tract surgery",
        "Grand multipara", "Suspected multiple pregnancy", "Age less than 18 years", "Age more than 35 years",
        "Isoimmunization (Rh negative)", "Vaginal bleeding", "Pelvic mass", "Blood pressure above 140/90 mm Hg",
        "Diabetes mellitus", "Renal disease", "Cardiac disease", "Chronic hypertension", "Substance use", "Other severe disease or condition",
    ]
    # Template table: 20 question rows grouped under three grey section bands.
    section_rows = {0, 8, 16}
    table_top = 626
    row_h = 24.6
    question_index = 0
    for row in range(23):
        if row in section_rows:
            continue
        key = keys[question_index]
        question_index += 1
        cy = table_top - (row + 1.0) * row_h + 8
        cx = 517 if risk_answers.get(key) else 566
        c.setStrokeColor(colors.black)
        c.setLineWidth(1)
        c.line(cx - 5, cy - 5, cx + 5, cy + 5)
        c.line(cx - 5, cy + 5, cx + 5, cy - 5)
    c.showPage()
    c.save()
    overlay.seek(0)
    base = PdfReader(str(template))
    layer = PdfReader(overlay)
    base.pages[0].merge_page(layer.pages[0])
    output = BytesIO()
    writer = PdfWriter()
    writer.add_page(base.pages[0])
    writer.write(output)
    output.seek(0)
    return output


def create_rh_page1_pdf(card: dict[str, Any]) -> BytesIO:
    out = BytesIO()
    c = canvas.Canvas(out, pagesize=A4)
    W, H = A4

    def text(x: float, y: float, value: Any, size: float = 8, bold: bool = False, align: str = "left") -> None:
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        {"left": c.drawString, "center": c.drawCentredString, "right": c.drawRightString}[align](x, y, str(value or ""))

    def line(x1: float, y1: float, x2: float, y2: float, width: float = .55) -> None:
        c.setLineWidth(width)
        c.line(x1, y1, x2, y2)

    def box(x: float, y: float, w: float, h: float, fill: str | None = None, width: float = .55) -> None:
        if fill:
            c.setFillColor(colors.HexColor(fill))
            c.rect(x, y, w, h, stroke=0, fill=1)
            c.setFillColor(colors.black)
        c.setLineWidth(width)
        c.rect(x, y, w, h, stroke=1, fill=0)

    def filled_line(label: str, value: Any, x: float, y: float, w: float, size: float = 8.4) -> None:
        text(x, y + 3, label, 8.5)
        line(x + c.stringWidth(label, "Helvetica", 8.5) + 3, y, x + w, y)
        text(x + c.stringWidth(label, "Helvetica", 8.5) + 6, y + 3, value, size, True)

    def mark(cx: float, cy: float) -> None:
        size = 4.5
        c.setStrokeColor(colors.black)
        c.setLineWidth(1.15)
        c.line(cx - size, cy - size, cx + size, cy + size)
        c.line(cx - size, cy + size, cx + size, cy - size)

    def date_parts(value: str) -> tuple[str, str, str]:
        try:
            y, m, d = value.split("-")
            return d, m, y
        except ValueError:
            return "", "", value or ""

    c.setTitle(f"RH Card Page 1 - {card.get('client_name','client')}")
    logo = ROOT / "backend" / "assets" / "moh_logo.png"
    if logo.exists():
        c.drawImage(ImageReader(str(logo)), 18 * mm, H - 25 * mm, width=50 * mm, height=16 * mm, mask="auto")
    text(W / 2, H - 39 * mm, "Integrated Antenatal, Labor, Delivery, Newborn and Postnatal Care Card", 15, True, "center")

    y = H - 62 * mm
    filled_line("Name of Facility:", card.get("facility_name"), 14 * mm, y, 270)
    filled_line("Date:", card.get("card_date"), 105 * mm, y, 125)
    y -= 12 * mm
    filled_line("ANC Reg.No:", card.get("anc_reg_no"), 14 * mm, y, 135)
    filled_line("Medical Record Number (MRN):", card.get("mrn"), 58 * mm, y, 178)
    y -= 14 * mm
    filled_line("Name of Client:", card.get("client_name"), 14 * mm, y, 180)
    filled_line("Age (Years):", card.get("age"), 75 * mm, y, 55)
    filled_line("Phone No:", card.get("phone"), 103 * mm, y, 76, 7.2)
    filled_line("Woreda:", card.get("woreda"), 139 * mm, y, 56, 7.2)
    filled_line("Kebele:", card.get("kebele"), 170 * mm, y, 38, 7.6)
    y -= 13 * mm
    lnmp = date_parts(card.get("lnmp") or "")
    edd = date_parts(card.get("edd") or "")
    filled_line("LNMP:", " / ".join(lnmp), 14 * mm, y, 100)
    filled_line("EDD:", " / ".join(edd), 41 * mm, y, 92)
    filled_line("Gravida:", card.get("gravida"), 75 * mm, y, 52)
    filled_line("Para:", card.get("para"), 98 * mm, y, 43)
    filled_line("Number of children alive:", card.get("children_alive"), 120 * mm, y, 105)
    filled_line("Marital Status:", card.get("marital_status"), 169 * mm, y, 46, 7.2)
    y -= 11 * mm
    text(14 * mm, y, "INSTRUCTIONS to Fill Classifying form: Answer all of the following questions by placing a cross mark in the corresponding box.", 8.3, True)

    risk_answers = card.get("risk_answers") or {}
    rows_def = [
        ("OBSTETRIC HISTORY", None), ("1. Previous stillbirth or neonatal death?", "Previous stillbirth or neonatal death"),
        ("2. History of 3 or more consecutive spontaneous abortions?", "3 or more consecutive spontaneous abortions"),
        ("3. Birth weight of last baby < 2500gm", "Last baby below 2500 g"), ("4. Birth weight of last baby > 4000gm", "Last baby above 4000 g"),
        ("5. Last pregnancy: hospital admission for hypertension or pre-eclampsia/eclampsia?", "Previous hypertension / pre-eclampsia / eclampsia"),
        ("6. Previous surgery on reproductive tract? (CS, Myomectomy, fistula repair, repaired uterine rupture, cervical cerclage)", "Previous reproductive tract surgery"),
        ("7. Grand multipara (more than 5 previous births)?", "Grand multipara"),
        ("CURRENT PREGNANCY", None), ("8. Diagnosed or suspected multiple pregnancy?", "Suspected multiple pregnancy"),
        ("9. Age less than 18 years?", "Age less than 18 years"), ("10. Age more than 35 years?", "Age more than 35 years"),
        ("11. Isoimmunization (Rh -ve) in current or in previous pregnancy?", "Isoimmunization (Rh negative)"),
        ("12. Vaginal bleeding?", "Vaginal bleeding"), ("13. Pelvic mass?", "Pelvic mass"),
        ("14. Systolic >140mm Hg and/or Diastolic Blood pressure >90 mm Hg", "Blood pressure above 140/90 mm Hg"),
        ("GENERAL MEDICAL", None), ("15. Diabetes mellitus?", "Diabetes mellitus"), ("16. Renal disease?", "Renal disease"),
        ("17. Cardiac disease?", "Cardiac disease"), ("18. Chronic Hypertension", "Chronic hypertension"),
        ("19. Known substance abuse (including heavy alcohol drinking, Smoking)?", "Substance use"),
        ("20. Any other severe medical disease or condition TB, HIV, Ca, DVT...?", "Other severe disease or condition"),
    ]
    table_x, table_y, table_w = 14 * mm, 24 * mm, W - 28 * mm
    row_h, yes_w, no_w = 6.78 * mm, 15 * mm, 15 * mm
    care_w = table_w - yes_w - no_w
    top = y - 7 * mm
    box(table_x, top - row_h * len(rows_def), table_w, row_h * len(rows_def), width=1.2)
    header_y = top
    text(table_x + care_w + yes_w / 2, header_y - row_h * .68, "Yes", 8.5, False, "center")
    text(table_x + care_w + yes_w + no_w / 2, header_y - row_h * .68, "NO", 8.5, False, "center")
    line(table_x + care_w, top, table_x + care_w, top - row_h * len(rows_def), .8)
    line(table_x + care_w + yes_w, top, table_x + care_w + yes_w, top - row_h * len(rows_def), .8)
    for i, (title, key) in enumerate(rows_def):
        ry = top - row_h * (i + 1)
        if key is None:
            box(table_x, ry, table_w, row_h, "#c8c8c8")
            text(table_x + 3, ry + row_h * .32, title, 9.2, True)
        else:
            line(table_x, ry, table_x + table_w, ry)
            text(table_x + 3, ry + row_h * .32, title, 6.25)
            for cx in (table_x + care_w + yes_w / 2, table_x + care_w + yes_w + no_w / 2):
                box(cx - 5.2, ry + 4.3, 10.4, 8.8)
            mark_x = table_x + care_w + (yes_w / 2 if risk_answers.get(key) else yes_w + no_w / 2)
            mark(mark_x, ry + 8.7)
    text(14 * mm, 9.5 * mm, "A \"Yes\" to any ONE of the above questions means that the woman is not eligible for the basic component of the new antenatal care model", 5.8)
    text(14 * mm, 7 * mm, "and requires more close follow up or referral to specialized care.", 5.8)
    c.showPage()
    c.save()
    out.seek(0)
    return out


def create_rh_page2_reference_pdf(card: dict[str, Any]) -> BytesIO:
    """Fill the official ANC contact grid while preserving the supplied artwork."""
    template = ROOT / "backend" / "assets" / "rh_card_page2_reference.pdf"
    if not template.exists():
        return create_rh_page2_pdf(card)
    overlay = BytesIO()
    c = canvas.Canvas(overlay, pagesize=A4)
    anc = card.get("sections", {}).get("anc", {}) or {}
    rows = [
        "Date of contact", "Gestational age", "Present pregnancy history / complaint", "Family / social history",
        "General appearance", "Blood pressure", "Weight", "Pallor", "Breast", "Chest", "Fundal height (weeks)",
        "Fetal heart beat", "Presentation", "Pelvic assessment", "Ultrasound", "Haemoglobin", "Blood group and Rh",
        "RPR / VDRL", "HIV PITC - pregnant client", "HIV PITC - partner", "HBsAg", "Urine test", "Active TB screening",
        "Indirect Coombs test", "75 g oral glucose test", "Preventive anti-helminthic treatment", "Malaria prevention / ITN",
        "Td vaccination", "Anti-D immunoglobulin", "Iron and folic acid dose", "ARV treatment type", "Syphilis treatment",
        "HBV prophylaxis", "Daily calcium supplementation", "Nutrition / healthy eating", "PMTCT and testing", "Family planning",
        "Breastfeeding", "Hygiene", "Avoid harmful traditional practices", "Reduce caffeine intake", "Gender-based violence / IPV",
        "Birth preparedness and complication readiness plan", "Assessment / danger signs identified", "Action taken", "Next appointment", "Provider name and signature",
    ]
    def compact(raw: Any) -> str:
        text = str(raw or "").replace("\n", " ").strip()
        replacements = {"No danger signs; fetal movement present":"No danger signs", "Lives with family; no tobacco or alcohol":"Family support", "Counselled and supplied":"Supplied", "Previously recorded":"Recorded", "Not applicable - Rh positive":"N/A - Rh+", "Transport, companion and emergency plan reviewed":"Plan reviewed"}
        return replacements.get(text, text)
    x_centers = [228 + 49 * i for i in range(8)]
    y = 733.0
    for row_index, key in enumerate(rows):
        height = 70 if key in {"Assessment / danger signs identified", "Action taken"} else 23 if key in {"Next appointment", "Provider name and signature"} else 12.35
        cy = y - height / 2
        for contact, x in enumerate(x_centers, 1):
            text = compact(anc.get(f"{contact}{key}", ""))
            if not text:
                continue
            c.setFillColor(colors.HexColor("#17212b"))
            c.setFont("Helvetica", 4.2 if height < 20 else 4.7)
            max_chars = 17 if height < 20 else 34
            c.drawCentredString(x, cy - 1.4, text[:max_chars])
        y -= height
    c.showPage()
    c.save()
    overlay.seek(0)
    base = PdfReader(str(template))
    layer = PdfReader(overlay)
    base.pages[0].merge_page(layer.pages[0])
    output = BytesIO()
    writer = PdfWriter()
    writer.add_page(base.pages[0])
    writer.write(output)
    output.seek(0)
    return output


def create_rh_page2_pdf(card: dict[str, Any]) -> BytesIO:
    out = BytesIO()
    W, H = A4

    def compact_value(value: Any) -> str:
        value = str(value or "").strip()
        replacements = {
            "No danger signs; fetal movement present": "No danger signs",
            "Mild morning nausea; no danger signs": "Mild nausea",
            "Lives with family; no tobacco or alcohol": "Family support",
            "Viable singleton pregnancy": "Viable singleton",
            "Normal; no protein/glucose": "Normal",
            "Screened; no disclosure": "Screened",
            "Transport, companion and emergency plan reviewed": "Plan reviewed",
            "Pregnancy progressing normally": "Normal",
            "Routine ANC care continued": "Routine care",
            "Close BP follow-up and physician review": "BP follow-up",
            "High-risk follow-up; stable today": "High-risk stable",
            "Exclusive breastfeeding counselled": "Counselled",
            "Postpartum options discussed": "Options discussed",
            "Counselled and supplied": "Supplied",
            "Previously recorded": "Recorded",
            "Previously given": "Given",
            "Not applicable - Rh positive": "N/A - Rh +",
        }
        return replacements.get(value, value)

    def tiny(value: Any, bold: bool = False, size: float = 4.15) -> Paragraph:
        style = getSampleStyleSheet()["BodyText"].clone("rhTiny")
        style.fontName = "Helvetica-Bold" if bold else "Helvetica"
        style.fontSize = size
        style.leading = size + .7
        style.alignment = 1
        style.wordWrap = "CJK"
        return Paragraph(compact_value(value).replace("&", "&amp;"), style)

    def label(value: Any, bold: bool = False, size: float = 6.0) -> Paragraph:
        style = getSampleStyleSheet()["BodyText"].clone("rhLabel")
        style.fontName = "Helvetica-Bold" if bold else "Helvetica"
        style.fontSize = size
        style.leading = size + .8
        style.wordWrap = "CJK"
        return Paragraph(str(value).replace("&", "&amp;"), style)

    anc = card.get("sections", {}).get("anc", {}) or {}
    contacts = ["1st Contact<br/>(better before<br/>12Wks)", "2nd<br/>Contact at<br/>20 WKs", "3rd<br/>Contact at<br/>26WKs", "4th<br/>Contact at<br/>30WKs", "5th<br/>Contact at<br/>34Wks", "6th<br/>Contact at<br/>36Wks", "7th<br/>Contact at<br/>38Wks", "8th<br/>Contact at<br/>40Wks"]
    rows_def = [
        ("Date of contact", "Date of contact", 11), ("Gestational age", "Gestational age", 11),
        ("Present Pregnancy History (complaint)", "Present pregnancy history / complaint", 12), ("Family/Social History", "Family / social history", 11),
        ("General Appearance", "General appearance", 11), ("Blood pressure", "Blood pressure", 11), ("Weight", "Weight", 11),
        ("Pallor", "Pallor", 11), ("Breast", "Breast", 11), ("Chest", "Chest", 11),
        ("Fundal height (wks)", "Fundal height (weeks)", 11), ("FHB", "Fetal heart beat", 11), ("Presentation", "Presentation", 11),
        ("Pelvic assessment (as required/indicated)", "Pelvic assessment", 12), ("Ultrasound (up to 24 weeks of gestation)", "Ultrasound", 12),
        ("Haemoglobin", "Haemoglobin", 11), ("Blood group, RH", "Blood group and Rh", 11), ("RPR/VDRL", "RPR / VDRL", 11),
        ("HIV (PITC) for pregnant", "HIV PITC - pregnant client", 12), ("HIV (PITC) for partner", "HIV PITC - partner", 12),
        ("HBsAg", "HBsAg", 11), ("Urine test", "Urine test", 11), ("Screening for active TB", "Active TB screening", 11),
        ("Indirect coomb's test <i>for RH negatives</i>", "Indirect Coombs test", 12), ("75 gm oral glucose test <i>(for those at risk)</i>", "75 g oral glucose test", 12),
        ("Preventive anti-helminthic treatment", "Preventive anti-helminthic treatment", 11), ("Malaria prevention with ITN, and early diagnosis and treatment", "Malaria prevention / ITN", 18),
        ("Td vaccination", "Td vaccination", 11), ("Anti-D immunoglobulin at 28 weeks <i>(for those unsensitised RH negatives)</i>", "Anti-D immunoglobulin", 16),
        ("Iron and folic acid (supplement dose)", "Iron and folic acid dose", 11), ("ARV Rx (type)", "ARV treatment type", 11),
        ("Syphilis Treatment", "Syphilis treatment", 11), ("HBV prophylaxis", "HBV prophylaxis", 11), ("Daily calcium supplementation", "Daily calcium supplementation", 11),
        ("Nutrition/healthy eating", "Nutrition / healthy eating", 11), ("PMTCT and testing", "PMTCT and testing", 11),
        ("Family planning", "Family planning", 11), ("Breast feeding", "Breastfeeding", 11), ("Hygiene", "Hygiene", 11),
        ("Avoidance of harmful traditional practices", "Avoid harmful traditional practices", 11), ("Reduce caffeine intake", "Reduce caffeine intake", 11),
        ("Gender based violence specially IPV", "Gender-based violence / IPV", 12),
        ("Birth Preparedness and Complication Readiness plan", "Birth preparedness and complication readiness plan", 16),
        ("Assessment <i>(diagnosis, danger sign/symptom identified)</i>", "Assessment / danger signs identified", 54),
        ("Action taken", "Action taken", 54), ("Next Appointment", "Next appointment", 14), ("Name and Signature", "Provider name and signature", 18),
    ]
    data = [[label("Contents of Care", True, 7.4)] + [label(x, True, 6.2) for x in contacts]]
    for title, key, _height in rows_def:
        row = [label(title, key in {"Date of contact", "Assessment / danger signs identified", "Action taken", "Next appointment", "Provider name and signature"}, 5.9)]
        for contact in range(1, 9):
            value = anc.get(f"{contact}{key}", "")
            row.append(tiny(value, key in {"Date of contact", "Gestational age", "Blood pressure", "Weight", "Fetal heart beat"}, 4.0))
        data.append(row)

    col_widths = [59 * mm] + [15.4 * mm] * 8
    row_heights = [40] + [height for _, _, height in rows_def]
    table = Table(data, colWidths=col_widths, rowHeights=row_heights, repeatRows=1)
    style = [
        ("GRID", (0, 0), (-1, -1), .45, colors.black),
        ("BOX", (0, 0), (-1, -1), 1.0, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d0d0d0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]
    section_rows = {"History": 3, "Physical Examination": 5, "Investigations": 15, "Medications & Vaccines": 26, "Advice and counselling on": 35}
    for row in section_rows.values():
        style.append(("LINEABOVE", (0, row), (-1, row), 1.0, colors.black))
    for row in [4, 13, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 29, 35, 44]:
        style.append(("BACKGROUND", (2, row), (-1, row), colors.HexColor("#a9a9a9")))
    table.setStyle(TableStyle(style))

    c = canvas.Canvas(out, pagesize=A4)
    c.setTitle(f"RH Card Page 2 - {card.get('client_name','client')}")
    logo = ROOT / "backend" / "assets" / "moh_logo.png"
    if logo.exists():
        c.drawImage(ImageReader(str(logo)), W - 46 * mm, H - 18 * mm, width=39 * mm, height=13 * mm, mask="auto")
    c.setFont("Helvetica-Bold", 11)
    c.drawCentredString(W / 2 + 20 * mm, H - 27 * mm, "II. Present pregnancy follow up schedule of ANC contacts")
    c.drawCentredString(W / 2 + 20 * mm, H - 38 * mm, "(weeks of gestation)")
    table.wrapOn(c, W - 16 * mm, H - 48 * mm)
    table.drawOn(c, 8 * mm, 8 * mm)
    c.showPage()
    c.save()
    out.seek(0)
    return out


def create_rh_page3_pdf(card: dict[str, Any]) -> BytesIO:
    out = BytesIO()
    c = canvas.Canvas(out, pagesize=A4)
    W, H = A4
    labor = card.get("sections", {}).get("labor", {}) or {}
    observations = labor.get("observations") if isinstance(labor.get("observations"), list) else []

    def text(x: float, y: float, value: Any, size: float = 8, bold: bool = False, align: str = "left") -> None:
        c.setFont("Times-Bold" if bold else "Times-Roman", size)
        {"left": c.drawString, "center": c.drawCentredString, "right": c.drawRightString}[align](x, y, str(value or ""))

    def line(x1: float, y1: float, x2: float, y2: float, width: float = .45) -> None:
        c.setLineWidth(width)
        c.line(x1, y1, x2, y2)

    def grid(x: float, y: float, w: float, h: float, cols: int, rows_count: int, heavy_y: list[int] | None = None) -> None:
        c.setLineWidth(.45)
        for i in range(cols + 1):
            xx = x + (w / cols) * i
            line(xx, y, xx, y + h)
        for i in range(rows_count + 1):
            yy = y + (h / rows_count) * i
            line(x, yy, x + w, yy, 1.2 if heavy_y and i in heavy_y else .45)

    def field(label: str, value: Any, x: float, y: float, w: float) -> None:
        text(x, y, label, 10.5, True)
        start = x + c.stringWidth(label, "Times-Bold", 10.5) + 2
        line(start, y - 2, x + w, y - 2)
        text(start + 4, y, value, 8.6, True)

    def col_for(entry: dict[str, Any]) -> int | None:
        raw = entry.get("hour") or entry.get("time") or ""
        try:
            value = float(raw)
            return max(0, min(23, int(round(value * 2))))
        except (TypeError, ValueError):
            return None

    def plot_value(entry: dict[str, Any], key: str, minimum: float, maximum: float, x: float, y: float, w: float, h: float, mark: str = "x") -> None:
        col = col_for(entry)
        if col is None:
            return
        try:
            value = float(entry.get(key))
        except (TypeError, ValueError):
            return
        cx = x + (col + .5) * (w / 24)
        cy = y + ((value - minimum) / (maximum - minimum)) * h
        cy = max(y, min(y + h, cy))
        c.setFont("Helvetica-Bold", 8)
        c.drawCentredString(cx, cy - 3, mark)

    def write_cell(entry: dict[str, Any], key: str, x: float, y: float, w: float, h: float, size: float = 6.5) -> None:
        col = col_for(entry)
        value = str(entry.get(key) or "").strip()
        if col is None or not value:
            return
        c.setFont("Helvetica", size)
        c.drawCentredString(x + (col + .5) * (w / 24), y + h / 2 - size / 3, value[:8])

    c.setTitle(f"RH Card Page 3 - {card.get('client_name','client')}")
    logo = ROOT / "backend" / "assets" / "moh_logo.png"
    if logo.exists():
        c.drawImage(ImageReader(str(logo)), W - 57 * mm, H - 18 * mm, width=49 * mm, height=15 * mm, mask="auto")

    left, grid_x, grid_w = 28 * mm, 49 * mm, 130 * mm
    top = H - 30 * mm
    text(left / 2, top, "III. Intrapartum Care and Follow up: Monitoring Progress of Labor using Partograph", 14, True)
    field("Name", card.get("client_name"), left / 2, top - 18 * mm, 50 * mm)
    field("Gravida", card.get("gravida"), 73 * mm, top - 18 * mm, 34 * mm)
    field("Para", card.get("para"), 123 * mm, top - 18 * mm, 30 * mm)
    field("MRN", card.get("mrn"), 161 * mm, top - 18 * mm, 26 * mm)
    field("Date of Admission", labor.get("admission_date"), left / 2, top - 30 * mm, 47 * mm)
    field("Time of admission", labor.get("admission_time"), 60 * mm, top - 30 * mm, 45 * mm)
    field("Ruptured Membranes", labor.get("ruptured_membranes"), 109 * mm, top - 30 * mm, 44 * mm)
    field("Hours", labor.get("ruptured_hours"), 159 * mm, top - 30 * mm, 26 * mm)

    fhr_y, fhr_h = H - 107 * mm, 42 * mm
    grid(grid_x, fhr_y, grid_w, fhr_h, 24, 12, [2, 10])
    for idx, value in enumerate(range(80, 201, 10)):
        text(grid_x - 6, fhr_y + (idx / 12) * fhr_h - 2, value, 10, False, "right")
    text(grid_x - 15 * mm, fhr_y + 27 * mm, "Fetal", 8.4, False, "center")
    text(grid_x - 15 * mm, fhr_y + 22 * mm, "Heart", 8.4, False, "center")
    text(grid_x - 15 * mm, fhr_y + 17 * mm, "rate", 8.4, False, "center")
    for obs in observations:
        plot_value(obs, "fhr", 80, 200, grid_x, fhr_y, grid_w, fhr_h, "x")

    strip_h = 9 * mm
    fluid_y = fhr_y - 10 * mm
    grid(grid_x, fluid_y, grid_w, strip_h, 24, 2)
    text(grid_x - 1, fluid_y + strip_h * .63, "Amniotic fluid", 7.6, False, "right")
    text(grid_x - 1, fluid_y + strip_h * .18, "Moulding", 7.6, False, "right")
    for obs in observations:
        write_cell(obs, "amniotic_fluid", grid_x, fluid_y + strip_h / 2, grid_w, strip_h / 2)
        write_cell(obs, "moulding", grid_x, fluid_y, grid_w, strip_h / 2)

    cervix_y, cervix_h = fluid_y - 49 * mm, 38 * mm
    grid(grid_x, cervix_y, grid_w, cervix_h, 24, 10)
    for i in range(11):
        text(grid_x - 7, cervix_y + (i / 10) * cervix_h - 2, i, 10, False, "right")
    text(34 * mm, cervix_y + 23 * mm, "Cervix (cm)", 8.2, False, "center")
    text(34 * mm, cervix_y + 18 * mm, "(Plot x)", 7.2, False, "center")
    line(grid_x, cervix_y + cervix_h * .4, grid_x + grid_w * .5, cervix_y + cervix_h, 1.4)
    line(grid_x + grid_w * .333, cervix_y + cervix_h * .4, grid_x + grid_w * .833, cervix_y + cervix_h, 1.4)
    text(grid_x + grid_w * .24, cervix_y + cervix_h * .66, "Alert", 15, True, "center")
    text(grid_x + grid_w * .56, cervix_y + cervix_h * .64, "Action", 15, True, "center")
    for obs in observations:
        plot_value(obs, "cervix", 0, 10, grid_x, cervix_y, grid_w, cervix_h, "x")
        plot_value(obs, "descent", 0, 10, grid_x, cervix_y, grid_w, cervix_h, "o")
    hours_y = cervix_y - 8 * mm
    grid(grid_x, hours_y, grid_w, 9 * mm, 24, 2)
    text(grid_x - 1, hours_y + 5.8 * mm, "Hours", 7, False, "right")
    text(grid_x - 1, hours_y + 1.8 * mm, "Time", 7, False, "right")
    for i in range(12):
        text(grid_x + (i + .5) * (grid_w / 12), hours_y + 5.8 * mm, i + 1, 5.8, False, "center")
    for obs in observations:
        write_cell(obs, "time", grid_x, hours_y, grid_w, 4.5 * mm, 5.2)

    contraction_y, contraction_h = hours_y - 23 * mm, 18 * mm
    grid(grid_x, contraction_y, grid_w, contraction_h, 24, 5)
    text(grid_x - 13 * mm, contraction_y + 10 * mm, "Contraction", 6.6, False, "center")
    text(grid_x - 13 * mm, contraction_y + 6 * mm, "per 10mins", 6.6, False, "center")
    for i in range(1, 6):
        text(grid_x - 2, contraction_y + (i - .5) * (contraction_h / 5) - 2, i, 10, False, "right")
    for obs in observations:
        plot_value(obs, "contractions", 0, 5, grid_x, contraction_y, grid_w, contraction_h, "x")

    oxy_y = contraction_y - 12 * mm
    grid(grid_x, oxy_y, grid_w, 9 * mm, 24, 2)
    text(grid_x - 1, oxy_y + 5.7 * mm, "Oxytocin U/L", 6.8, False, "right")
    text(grid_x - 1, oxy_y + 1.6 * mm, "Drops/min", 6.8, False, "right")
    for obs in observations:
        write_cell(obs, "oxytocin_ul", grid_x, oxy_y + 4.5 * mm, grid_w, 4.5 * mm, 5.2)
        write_cell(obs, "drops_min", grid_x, oxy_y, grid_w, 4.5 * mm, 5.2)

    drugs_y = oxy_y - 21 * mm
    grid(grid_x, drugs_y, grid_w, 15 * mm, 12, 1)
    text(grid_x - 2, drugs_y + 9 * mm, "Drugs given &", 5.6, False, "right")
    text(grid_x - 2, drugs_y + 5.5 * mm, "IV fluids", 5.6, False, "right")
    for obs in observations:
        write_cell(obs, "drugs_fluids", grid_x, drugs_y, grid_w, 15 * mm, 4.8)

    bp_y, bp_h = 43 * mm, 43 * mm
    grid(grid_x, bp_y, grid_w, bp_h, 24, 12)
    for idx, value in enumerate(range(60, 181, 10)):
        text(grid_x - 6, bp_y + (idx / 12) * bp_h - 2, value, 10, False, "right")
    text(31 * mm, bp_y + 24 * mm, "Pulse", 6.6, False, "right")
    text(31 * mm, bp_y + 14 * mm, "and", 6.6, False, "right")
    text(31 * mm, bp_y + 7 * mm, "BP", 6.6, False, "right")
    for obs in observations:
        plot_value(obs, "pulse", 60, 180, grid_x, bp_y, grid_w, bp_h, ".")
        plot_value(obs, "systolic", 60, 180, grid_x, bp_y, grid_w, bp_h, "x")
        plot_value(obs, "diastolic", 60, 180, grid_x, bp_y, grid_w, bp_h, "o")

    temp_y = bp_y - 11 * mm
    grid(grid_x, temp_y, grid_w, 7 * mm, 24, 1)
    text(grid_x - 2, temp_y + 3 * mm, "Temp C", 6.8, False, "right")
    for obs in observations:
        write_cell(obs, "temperature", grid_x, temp_y, grid_w, 8 * mm, 5.2)

    urine_y = temp_y - 17 * mm
    grid(grid_x, urine_y, grid_w, 13 * mm, 24, 3)
    text(grid_x - 2, urine_y + 10 * mm, "Protein", 6.4, False, "right")
    text(grid_x - 2, urine_y + 6 * mm, "Acetone", 6.4, False, "right")
    text(grid_x - 2, urine_y + 2 * mm, "Volume", 6.4, False, "right")
    for obs in observations:
        write_cell(obs, "urine_protein", grid_x, urine_y + 9.3 * mm, grid_w, 4.7 * mm, 5.2)
        write_cell(obs, "urine_acetone", grid_x, urine_y + 4.6 * mm, grid_w, 4.7 * mm, 5.2)
        write_cell(obs, "urine_volume", grid_x, urine_y, grid_w, 4.7 * mm, 5.2)

    c.showPage()
    c.save()
    out.seek(0)
    return out


def create_rh_page4_pdf(card: dict[str, Any]) -> BytesIO:
    out = BytesIO()
    c = canvas.Canvas(out, pagesize=A4)
    W, H = A4
    delivery = card.get("sections", {}).get("delivery", {}) or {}
    postpartum = card.get("sections", {}).get("postpartum", {}) or {}

    def text(x: float, y: float, value: Any, size: float = 9, bold: bool = False, align: str = "left") -> None:
        c.setFont("Times-Bold" if bold else "Times-Roman", size)
        {"left": c.drawString, "center": c.drawCentredString, "right": c.drawRightString}[align](x, y, str(value or ""))

    def line(x1: float, y1: float, x2: float, y2: float, width: float = .45) -> None:
        c.setLineWidth(width)
        c.line(x1, y1, x2, y2)

    def selected(group: str, item: str) -> bool:
        values = delivery.get(group)
        return item in values if isinstance(values, list) else str(values or "").strip().lower() == item.lower()

    def check(x: float, y: float, on: bool = False) -> None:
        c.setLineWidth(.55)
        c.rect(x, y, 8, 8)
        if on:
            c.setLineWidth(1.0)
            c.line(x + 1.5, y + 1.5, x + 6.5, y + 6.5)
            c.line(x + 1.5, y + 6.5, x + 6.5, y + 1.5)

    def option(label: str, group: str, item: str, x: float, y: float, size: float = 9) -> float:
        text(x, y, label, size)
        w = c.stringWidth(label, "Times-Roman", size)
        check(x + w + 5, y - 2, selected(group, item))
        return x + w + 18

    def filled(label: str, value: Any, x: float, y: float, w: float, size: float = 9, bold_label: bool = False) -> None:
        text(x, y, label, size, bold_label)
        start = x + c.stringWidth(label, "Times-Bold" if bold_label else "Times-Roman", size) + 2
        line(start, y - 2, x + w, y - 2)
        text(start + 3, y, value, max(6.2, size - 1), True)

    def cell_value(period: str, label: str) -> str:
        aliases = {
            "Date": ["Date"],
            "BP": ["BP"],
            "PR/RR": ["PR / RR"],
            "Temp": ["Temperature"],
            "Uterus contracted/look for PPH": ["Uterus contracted / PPH assessment"],
            "Dribbling/leaking urine": ["Dribbling / leaking urine"],
            "Anemia": ["Anemia"],
            "Vaginal discharge (after 4 Wks of delivery)": ["Vaginal discharge after 4 weeks"],
            "Pelvic Exam (only if vaginal discharge)": ["Pelvic examination if indicated"],
            "Breast Exam": ["Breast examination"],
            "IFA supplementation": ["IFA supplementation"],
            "Counseling danger signs/symptoms, FP, Hygiene,\nNutrition, EPI, use of ITN, BF, etc given": ["Danger signs, FP, hygiene, nutrition, EPI, ITN and breastfeeding counselling"],
            "Baby Breathing": ["Baby breathing"],
            "Baby Breastfeeding:": ["Baby breastfeeding"],
            "Baby Wt (gm)": ["Baby weight (g)"],
            "Immunization": ["Immunization"],
            "HIV tested (Y/N)": ["HIV tested"],
            "HIV test result : P/N": ["HIV test result"],
            "ARV Rx for mother (By Type)": ["ARV treatment for mother (type)"],
            "ARV Px for Newborn(By Type)": ["ARV prophylaxis for newborn (type)"],
            "Feeding option : EBF/RF": ["Feeding option EBF / RF"],
            "Newborn referred to chronic HIV infant care": ["Newborn referred to chronic HIV infant care"],
            "FP Counseled & provided (By Method)": ["Family planning counselled / method provided"],
            "Action Taken": ["Action taken"],
            "Remark": ["Remark"],
        }
        for key in aliases.get(label, [label]):
            value = postpartum.get(period + key)
            if value:
                return str(value)
        return ""

    c.setTitle(f"RH Card Page 4 - {card.get('client_name','client')}")
    logo = ROOT / "backend" / "assets" / "moh_logo.png"
    if logo.exists():
        c.drawImage(ImageReader(str(logo)), W - 57 * mm, H - 18 * mm, width=49 * mm, height=15 * mm, mask="auto")

    x0, y = 14 * mm, H - 29 * mm
    text(x0, y, "Delivery Summary", 18, True)
    y -= 14 * mm
    filled("Date (DD/MM/YY)", delivery.get("delivery_date"), x0, y, 54 * mm, 11)
    filled("Time:", delivery.get("delivery_time"), 68 * mm, y, 45 * mm, 11)

    y -= 10 * mm
    text(x0, y, "Mode of Delivery:", 10.5, True)
    x = 41 * mm
    for label, group, item in [("SVD", "Mode of delivery", "SVD"), ("C/Section", "Mode of delivery", "C/Section"), ("Vacuum/Forceps", "Mode of delivery", "Vacuum/Forceps"), ("Episiotomy", "Mode of delivery", "Episiotomy"), ("AMTSL: Oxytocin", "AMTSL uterotonic", "Oxytocin"), ("Ergometrine", "AMTSL uterotonic", "Ergometrine"), ("Misoprostol", "AMTSL uterotonic", "Misoprostol")]:
        x = option(label, group, item, x, y, 8.6)

    y -= 9 * mm
    text(x0, y, "Placenta:", 10.5, True)
    x = 30 * mm
    for label, group, item in [("CCT", "Placenta", "CCT"), ("Complete", "Placenta", "Complete"), ("Incomplete", "Placenta", "Incomplete"), ("MRP*", "Placenta", "MRP")]:
        x = option(label, group, item, x, y, 9.3)
    text(105 * mm, y, "Tear rep:", 9.5)
    x = 122 * mm
    for label in ["1st degree", "2nd degree", "3rd degree"]:
        x = option(label, "Tear repair", label, x, y, 9.0)

    y -= 9 * mm
    text(x0, y, "NEWBORN:", 10.5, True)
    x = 38 * mm
    for label, group, item in [("Single", "Newborn", "Single"), ("Multiple", "Newborn", "Multiple"), ("Alive", "Newborn", "Alive")]:
        x = option(label, group, item, x, y, 9.3)
    filled("Apgar score:", delivery.get("apgar"), 97 * mm, y, 31 * mm, 9.3)
    text(130 * mm, y, "Still Birth:", 9.3)
    x = 155 * mm
    x = option("Mac", "Stillbirth", "Macerated", x, y, 9.0)
    option("Fresh", "Stillbirth", "Fresh", x, y, 9.0)

    y -= 9 * mm
    text(x0, y, "Sex:", 9.8)
    x = 22 * mm
    x = option("Male", "Sex", "Male", x, y, 9.3)
    x = option("Female", "Sex", "Female", x, y, 9.3)
    filled("Birth wt. (gm.)", delivery.get("birth_weight"), 49 * mm, y, 32 * mm, 9.0)
    filled("Length (cm.)", delivery.get("length"), 83 * mm, y, 30 * mm, 9.3)
    x = 118 * mm
    x = option("Term", "Maturity", "Term", x, y, 9.3)
    option("Preterm", "Maturity", "Preterm", x, y, 9.3)

    y -= 9 * mm
    filled("BCG (Date):", delivery.get("bcg_date"), x0, y, 35 * mm, 9.3)
    filled("OPV 0(Date)", delivery.get("opv0_date"), 50 * mm, y, 28 * mm, 9.3)
    x = 83 * mm
    for label, item in [("HBV birth dose", "HBV birth dose"), ("Vit K", "Vitamin K"), ("TTC", "TTC"), ("Skin to skin contact", "Skin-to-skin contact")]:
        x = option(label, "Newborn care", item, x, y, 9.0)

    y -= 9 * mm
    text(x0, y, "Obstetric Cxn:", 9.7)
    x = 50 * mm
    x = option("Managed", "Obstetric complication action", "Managed", x, y, 9.3)
    option("Referred", "Obstetric complication action", "Referred", x, y, 9.3)

    y -= 9 * mm
    x = x0
    for label, item in [("Eclampsia:", "Eclampsia"), ("PPH", "PPH"), ("APH", "APH"), ("PROM/Sepsis", "PROM/Sepsis"), ("Ruptured Ux", "Ruptured uterus"), ("Repaired", "Repaired"), ("Hysterectomy", "Hysterectomy")]:
        x = option(label, "Complications", item, x, y, 8.7)
    y -= 7 * mm
    x = x0
    x = option("Obst/prolg labor", "Complications", "Obstructed/prolonged labor", x, y, 8.7)
    filled("Feeding Option: EBF", delivery.get("feeding_ebf"), 67 * mm, y, 26 * mm, 8.7)
    filled("ERF", delivery.get("feeding_erf"), 101 * mm, y, 23 * mm, 8.7)

    y -= 13 * mm
    text(x0, y, "HIV Testing accepted:", 10, True)
    x = 51 * mm
    x = option("Yes", "HIV testing accepted", "Yes", x, y, 9.3)
    x = option("No:", "HIV testing accepted", "No", x, y, 9.3)
    text(75 * mm, y, "HIV Test result:", 9.3)
    x = 108 * mm
    x = option("P", "HIV test result", "Positive", x, y, 9.3)
    option("N", "HIV test result", "Negative", x, y, 9.3)

    y -= 9 * mm
    filled("ARV Rx : for mothers (by Type)", delivery.get("arv_mother"), x0, y, 78 * mm, 9.4, True)
    filled("ARV Px for New Born (by type)", delivery.get("arv_newborn"), 97 * mm, y, 66 * mm, 9.4)
    y -= 9 * mm
    filled("Remark:", delivery.get("remark"), x0, y, 154 * mm, 9.4)
    y -= 9 * mm
    filled("Delivered by:", delivery.get("delivered_by"), x0, y, 86 * mm, 9.4)
    filled("Sign:", delivery.get("signature"), 122 * mm, y, 31 * mm, 9.4)
    y -= 7 * mm
    text(x0, y, "*MRP=manual removal of placenta", 9.2)

    y -= 10 * mm
    text(x0, y, "IV. Postpartum Care", 18, True)
    table_top = y - 10 * mm
    table_x, table_w = x0, W - 28 * mm
    periods = ["24 hours", "25-48 hours", "49-72 hours", "73 hours-7 days", "8-42 days"]
    headers = ["Date", "24 hrs stay", "25-48 Hrs", "49-72 Hrs", "73Hrs-7days", "8-42 days", "Remarks"]
    row_labels = [
        "BP", "PR/RR", "Temp", "Uterus contracted/look for PPH", "Dribbling/leaking urine", "Anemia",
        "Vaginal discharge (after 4 Wks of delivery)", "Pelvic Exam (only if vaginal discharge)", "Breast Exam",
        "IFA supplementation", "Counseling danger signs/symptoms, FP, Hygiene,\nNutrition, EPI, use of ITN, BF, etc given",
        "Baby Breathing", "Baby Breastfeeding:", "Baby Wt (gm)", "Immunization", "HIV tested (Y/N)", "HIV test result : P/N",
        "ARV Rx for mother (By Type)", "ARV Px for Newborn(By Type)", "Feeding option : EBF/RF",
        "Newborn referred to chronic HIV infant care", "FP Counseled & provided (By Method)", "Action Taken", "Remark",
    ]
    col_widths = [72 * mm, 20 * mm, 18.5 * mm, 19 * mm, 23 * mm, 18.5 * mm, 11 * mm]
    row_h = 4.15 * mm
    c.setLineWidth(1.5)
    c.rect(table_x, table_top - row_h * (len(row_labels) + 1), table_w, row_h * (len(row_labels) + 1))
    c.setFillColor(colors.HexColor("#d0d0d0"))
    c.rect(table_x, table_top - row_h, table_w, row_h, stroke=0, fill=1)
    c.setFillColor(colors.black)
    xx = table_x
    for w in col_widths:
        line(xx, table_top, xx, table_top - row_h * (len(row_labels) + 1), .55)
        xx += w
    line(table_x + table_w, table_top, table_x + table_w, table_top - row_h * (len(row_labels) + 1), .55)
    for i in range(len(row_labels) + 2):
        line(table_x, table_top - row_h * i, table_x + table_w, table_top - row_h * i, .55)
    xx = table_x
    for header, w in zip(headers, col_widths):
        text(xx + 2, table_top - row_h + 3.4, header, 6.7, True)
        xx += w
    for r, label in enumerate(row_labels, start=1):
        yy = table_top - row_h * (r + 1) + 4
        lines = label.split("\n")
        text(table_x + 2, yy + (2.1 if len(lines) == 2 else 0), lines[0], 5.9)
        if len(lines) > 1:
            text(table_x + 2, yy - 3.3, lines[1], 5.9)
        xx = table_x + col_widths[0]
        for period, w in zip(periods, col_widths[1:-1]):
            value = cell_value(period, label)
            text(xx + 1, yy, value[:13], 4.9)
            xx += w
        if label == "Remark":
            text(xx + 1, yy, cell_value(periods[-1], label)[:8], 4.8)

    c.showPage()
    c.save()
    out.seek(0)
    return out


@app.get("/api/rh-cards/{card_id}/pdf")
def rh_card_pdf(card_id: int, page: str = "1"):
    found = rows("SELECT * FROM rh_cards WHERE id=?", (card_id,))
    if not found:
        raise HTTPException(404, "Maternal RH card not found")
    if page not in ("1", "page1", "2", "page2", "3", "page3", "4", "page4"):
        raise HTTPException(422, "Only RH card page 1, page 2, page 3 and page 4 PDFs are available in this version")
    card = decode_rh_card(found[0])
    selected_page = "4" if page in ("4", "page4") else "3" if page in ("3", "page3") else "2" if page in ("2", "page2") else "1"
    filename = f"RH-card-page-{selected_page}-{card.get('mrn','record')}.pdf"
    pdf = create_rh_page4_pdf(card) if selected_page == "4" else create_rh_page3_pdf(card) if selected_page == "3" else create_rh_page2_reference_pdf(card) if selected_page == "2" else create_rh_page1_reference_pdf(card)
    return Response(content=pdf.getvalue(), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.get("/api/nutrition-reports")
def list_nutrition_reports() -> list[dict[str, Any]]:
    result = rows("SELECT * FROM nutrition_reports ORDER BY id DESC")
    return [{"id": item["id"], **json.loads(item["payload"]), "created_at": item["created_at"]} for item in result]


@app.post("/api/nutrition-reports", status_code=201)
def create_nutrition_report(report: NutritionInput) -> dict[str, Any]:
    with closing(db()) as connection:
        cursor = connection.execute("INSERT INTO nutrition_reports (payload,created_at) VALUES (?,?)", (report.model_dump_json(), datetime.now().isoformat(timespec="seconds")))
        connection.commit()
    return {"id": cursor.lastrowid, "message": "Nutrition tally report saved"}


def tally_marks(value: int) -> str:
    groups, remaining = divmod(value, 5)
    return " ".join(["||||/" for _ in range(groups)] + (["|" * remaining] if remaining else [])) or "-"


def zero_tally() -> dict[str, Any]:
    return {"gmp": {age: {s: 0 for s in ("normal", "moderate", "severe")} for age in ("0-5", "6-23")}, "screen": {age: {s: 0 for s in ("normal", "mam", "sam")} for age in ("0-5", "6-23", "24-59")}, "vitamin": {"6-11": {"one": 0, "two": 0}, "12-59": {"one": 0, "two": 0}}, "deworming": {"one": 0, "two": 0}, "development": {age: {s: 0 for s in ("cdd", "sdd", "ndd")} for age in ("0-23", "24-59")}}


def build_cinus_tally(month: str, region: str = "Amhara", woreda: str = "Bahir Dar", facility: str = "Kidanemihiret", begin_date: str | None = None, end_date: str | None = None) -> dict[str, Any]:
    tally = zero_tally()
    year, mon = map(int, month.split("-")); begin_date = begin_date or f"{month}-01"; end_date = end_date or f"{month}-{monthrange(year, mon)[1]:02d}"
    canonical = rows("""SELECT v.*,g.underweight_status,n.result AS nutrition_result,d.result AS developmental_result,
    va.dose_number AS vitamin_dose, dw.dose_number AS deworming_dose FROM visits v
    LEFT JOIN growth_assessments g ON g.visit_id=v.id LEFT JOIN nutrition_screenings n ON n.visit_id=v.id
    LEFT JOIN development_screenings d ON d.visit_id=v.id LEFT JOIN vitamin_a va ON va.visit_id=v.id
    LEFT JOIN deworming dw ON dw.visit_id=v.id WHERE v.visit_date BETWEEN ? AND ?""", (begin_date, end_date))
    if canonical:
        for item in canonical:
            age = item["age_months"]; gmp_age = "0-5" if age <= 5 else "6-23" if age <= 23 else None; screen_age = "0-5" if age <= 5 else "6-23" if age <= 23 else "24-59"
            gmp_key = {"Normal":"normal","Moderate underweight":"moderate","Severe underweight":"severe"}.get(item["underweight_status"])
            if gmp_age and gmp_key: tally["gmp"][gmp_age][gmp_key] += 1
            if item["nutrition_result"] in tally["screen"][screen_age]: tally["screen"][screen_age][item["nutrition_result"]] += 1
            vitamin_age = "6-11" if 6 <= age <= 11 else "12-59" if 12 <= age <= 59 else None
            if vitamin_age and item["vitamin_dose"]: tally["vitamin"][vitamin_age]["one" if item["vitamin_dose"] == 1 else "two"] += 1
            if 24 <= age <= 59 and item["deworming_dose"]: tally["deworming"]["one" if item["deworming_dose"] == 1 else "two"] += 1
            dev_age = "0-23" if age <= 23 else "24-59"
            if item["developmental_result"] in tally["development"][dev_age]: tally["development"][dev_age][item["developmental_result"]] += 1
        return {"month": month, "year": month[:4], "region": region, "woreda": woreda, "facility": facility, "begin_date": begin_date, "end_date": end_date, "records": len(canonical), "tally": tally}
    services = rows("SELECT * FROM child_services WHERE service_date BETWEEN ? AND ?", (begin_date, end_date))
    for item in services:
        age = item["age_months"]
        gmp_age = "0-5" if age <= 5 else "6-23" if age <= 23 else None
        screen_age = "0-5" if age <= 5 else "6-23" if age <= 23 else "24-59"
        if gmp_age and item["gmp_status"] in tally["gmp"][gmp_age]: tally["gmp"][gmp_age][item["gmp_status"]] += 1
        if item["nutrition_status"] in tally["screen"][screen_age]: tally["screen"][screen_age][item["nutrition_status"]] += 1
        vitamin_age = "6-11" if 6 <= age <= 11 else "12-59" if 12 <= age <= 59 else None
        if vitamin_age and item["vitamin_a_doses"]: tally["vitamin"][vitamin_age]["one" if item["vitamin_a_doses"] == 1 else "two"] += 1
        if 24 <= age <= 59 and item["deworming_doses"]: tally["deworming"]["one" if item["deworming_doses"] == 1 else "two"] += 1
        development_age = "0-23" if age <= 23 else "24-59"
        if item["developmental_status"] in tally["development"][development_age]: tally["development"][development_age][item["developmental_status"]] += 1
    return {"month": month, "year": month[:4], "region": region, "woreda": woreda, "facility": facility, "begin_date": begin_date, "end_date": end_date, "records": len(services), "tally": tally}


@app.get("/api/child-services")
def list_child_services(month: str | None = None) -> list[dict[str, Any]]:
    query = "SELECT c.*,p.full_name,p.mrn FROM child_services c JOIN patients p ON p.id=c.patient_id"
    params: tuple[Any, ...] = ()
    if month:
        query += " WHERE substr(c.service_date,1,7)=?"; params = (month,)
    return rows(query + " ORDER BY c.service_date DESC, c.id DESC", params)


@app.post("/api/child-services", status_code=201)
def create_child_service(record: ChildServiceInput) -> dict[str, Any]:
    if not rows("SELECT id FROM patients WHERE id=?", (record.patient_id,)): raise HTTPException(404, "Child not found")
    with closing(db()) as connection:
        cursor = connection.execute("INSERT INTO child_services (patient_id,service_date,age_months,gmp_status,nutrition_status,vitamin_a_doses,deworming_doses,developmental_status,created_at) VALUES (?,?,?,?,?,?,?,?,?)", (*record.model_dump().values(), datetime.now().isoformat(timespec="seconds")))
        connection.commit()
    return {"id": cursor.lastrowid, "message": "Child service record saved"}


def age_in_months(dob: str, visit_date: str) -> int:
    born, visited = date.fromisoformat(dob), date.fromisoformat(visit_date)
    return (visited.year - born.year) * 12 + visited.month - born.month - (1 if visited.day < born.day else 0)


def z_status(value: float | None, normal: str, moderate: str, severe: str) -> str:
    if value is None: return "Not assessed"
    if value >= -2: return normal
    if value >= -3: return moderate
    return severe


def calculate_growth_scores(sex: str, dob: str, visit_date: str, weight: float, height: float) -> dict[str, float]:
    """Return WHO 0-5 growth z-scores. Length is used below age 24 months."""
    age_days = (date.fromisoformat(visit_date) - date.fromisoformat(dob)).days
    if not 0 <= age_days <= 1826:
        raise HTTPException(422, "WHO growth scores are available for children aged 0-59 months")
    try:
        # Pass dates rather than age_in_days: the underlying library treats 0 days
        # as a false value, whereas a same-day newborn visit is valid.
        observation = Observation(sex=sex.lower(), dob=date.fromisoformat(dob), date_of_observation=date.fromisoformat(visit_date))
        recumbent = age_days < 731
        if recumbent and not 45 <= height <= 110:
            raise HTTPException(422, "For children under 24 months, length must be between 45 and 110 cm for WHO WHZ calculation.")
        if not recumbent and not 65 <= height <= 120:
            raise HTTPException(422, "For children aged 24 months or older, height must be between 65 and 120 cm for WHO WHZ calculation.")
        haz = observation.length_or_height_for_age(height, recumbent=recumbent)
        whz = observation.weight_for_length(weight, height) if recumbent else observation.weight_for_height(weight, height)
        return {"waz": float(round(observation.weight_for_age(weight), 2)), "haz": float(round(haz, 2)), "whz": float(round(whz, 2))}
    except (PyGrowUpException, ValueError, TypeError) as error:
        raise HTTPException(422, f"Check measurements: {error}. Enter length/height in centimetres, for example 50, 71.5 or 92.") from error


@app.get("/api/children")
def list_children() -> list[dict[str, Any]]:
    return rows("SELECT * FROM children ORDER BY id DESC")


@app.post("/api/children", status_code=201)
def create_child(child: ChildInput) -> dict[str, Any]:
    now = datetime.now().isoformat(timespec="seconds")
    with closing(db()) as connection:
        next_number = connection.execute("SELECT COUNT(*) FROM children").fetchone()[0] + 1
        code = f"CIN-{date.today().year}-{next_number:04d}"
        cursor = connection.execute("INSERT INTO children (child_code,first_name,last_name,sex,date_of_birth,mother_name,phone,region,woreda,kebele,household_id,registration_date) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (code, *child.model_dump().values(), now))
        connection.commit()
        return dict(connection.execute("SELECT * FROM children WHERE id=?", (cursor.lastrowid,)).fetchone())


@app.put("/api/children/{child_id}")
def update_child(child_id: int, child: ChildInput) -> dict[str, Any]:
    with closing(db()) as connection:
        existing = connection.execute("SELECT id FROM children WHERE id=?", (child_id,)).fetchone()
        if not existing:
            raise HTTPException(404, "Child not found")
        connection.execute("""UPDATE children SET first_name=?,last_name=?,sex=?,date_of_birth=?,mother_name=?,phone=?,region=?,woreda=?,kebele=?,household_id=? WHERE id=?""", (*child.model_dump().values(), child_id))
        connection.commit()
        return dict(connection.execute("SELECT * FROM children WHERE id=?", (child_id,)).fetchone())


@app.get("/api/growth-assessment")
def growth_assessment(child_id: int, visit_date: str, weight: float, height: float) -> dict[str, float]:
    with closing(db()) as connection:
        child = connection.execute("SELECT sex,date_of_birth FROM children WHERE id=?", (child_id,)).fetchone()
    if not child:
        raise HTTPException(404, "Child not found")
    return calculate_growth_scores(child["sex"], child["date_of_birth"], visit_date, weight, height)


@app.get("/api/visits")
def list_visits(month: str | None = None) -> list[dict[str, Any]]:
    query = """SELECT v.*,c.child_code,c.first_name,c.last_name,c.sex,c.woreda,g.waz,g.haz,g.whz,g.underweight_status,g.stunting_status,g.wasting_status,n.result AS nutrition_result,n.referral,d.result AS developmental_result FROM visits v JOIN children c ON c.id=v.child_id LEFT JOIN growth_assessments g ON g.visit_id=v.id LEFT JOIN nutrition_screenings n ON n.visit_id=v.id LEFT JOIN development_screenings d ON d.visit_id=v.id"""
    params: tuple[Any, ...] = ()
    if month: query += " WHERE substr(v.visit_date,1,7)=?"; params = (month,)
    return rows(query + " ORDER BY v.visit_date DESC, v.id DESC", params)


@app.get("/api/children/{child_id}/history")
def child_history(child_id: int) -> list[dict[str, Any]]:
    return rows("""SELECT v.*,g.waz,g.haz,g.whz,n.result AS nutrition_result,
        va.dose_number AS vitamin_a_dose,dw.dose_number AS deworming_dose,
        n.referral,d.result AS developmental_result,d.notes AS development_notes
        FROM visits v LEFT JOIN growth_assessments g ON g.visit_id=v.id
        LEFT JOIN nutrition_screenings n ON n.visit_id=v.id
        LEFT JOIN vitamin_a va ON va.visit_id=v.id LEFT JOIN deworming dw ON dw.visit_id=v.id
        LEFT JOIN development_screenings d ON d.visit_id=v.id
        WHERE v.child_id=? ORDER BY v.visit_date DESC,v.id DESC""", (child_id,))


@app.post("/api/visits", status_code=201)
def create_visit(item: VisitInput) -> dict[str, Any]:
    with closing(db()) as connection:
        child = connection.execute("SELECT * FROM children WHERE id=?", (item.child_id,)).fetchone()
        if not child: raise HTTPException(404, "Child not found")
        age = age_in_months(child["date_of_birth"], item.visit_date)
        if not 0 <= age <= 59: raise HTTPException(422, "CINUS is for children aged 0-59 months")
        scores = calculate_growth_scores(child["sex"], child["date_of_birth"], item.visit_date, item.weight, item.height)
        now = datetime.now().isoformat(timespec="seconds")
        visit = connection.execute("INSERT INTO visits (child_id,visit_date,age_months,weight,height,muac,edema,health_worker,created_at) VALUES (?,?,?,?,?,?,?,?,?)", (item.child_id,item.visit_date,age,item.weight,item.height,item.muac,int(item.edema),item.health_worker,now))
        visit_id = visit.lastrowid
        connection.execute("INSERT INTO growth_assessments (visit_id,waz,haz,whz,underweight_status,stunting_status,wasting_status,generated_at) VALUES (?,?,?,?,?,?,?,?)", (visit_id,scores["waz"],scores["haz"],scores["whz"],z_status(scores["waz"],"Normal","Moderate underweight","Severe underweight"),z_status(scores["haz"],"Normal","Moderate stunting","Severe stunting"),z_status(scores["whz"],"Normal","Moderate wasting","Severe wasting"),now))
        # Bilateral pitting oedema is an independent SAM criterion and overrides a manual screen selection.
        nutrition_result = "sam" if item.edema else item.nutrition_result
        connection.execute("INSERT INTO nutrition_screenings (visit_id,screening_date,result,referral) VALUES (?,?,?,?)", (visit_id,item.visit_date,nutrition_result,item.referral))
        if item.vitamin_a_dose:
            if not 6 <= age <= 59: raise HTTPException(422, "Vitamin A may be recorded in this CINUS form only for children aged 6-59 months")
            previous = connection.execute("SELECT date_given FROM vitamin_a WHERE child_id=? ORDER BY date_given DESC LIMIT 1", (item.child_id,)).fetchone()
            if previous and (date.fromisoformat(item.visit_date) - date.fromisoformat(previous["date_given"])).days < 120:
                raise HTTPException(422, "Vitamin A was already recorded within the last 4 months. Check the child's service history.")
            connection.execute("INSERT INTO vitamin_a (child_id,visit_id,dose_number,date_given,provider) VALUES (?,?,?,?,?)", (item.child_id,visit_id,item.vitamin_a_dose,item.visit_date,item.health_worker))
        if item.deworming_dose:
            if not 24 <= age <= 59: raise HTTPException(422, "Deworming may be recorded in this CINUS form only for children aged 24-59 months")
            previous = connection.execute("SELECT date_given FROM deworming WHERE child_id=? ORDER BY date_given DESC LIMIT 1", (item.child_id,)).fetchone()
            if previous and (date.fromisoformat(item.visit_date) - date.fromisoformat(previous["date_given"])).days < 365:
                raise HTTPException(422, "Deworming was already recorded within the last 12 months. Check the child's service history.")
            connection.execute("INSERT INTO deworming (child_id,visit_id,dose_number,date_given,provider) VALUES (?,?,?,?,?)", (item.child_id,visit_id,item.deworming_dose,item.visit_date,item.health_worker))
        connection.execute("INSERT INTO development_screenings (child_id,visit_id,date,result,notes) VALUES (?,?,?,?,?)", (item.child_id,visit_id,item.visit_date,item.developmental_result,item.development_notes))
        connection.commit()
    return {"id": visit_id, "age_months": age, "scores": scores, "message": "Child visit and all linked CINUS records saved"}


@app.put("/api/visits/{visit_id}")
def update_visit(visit_id: int, item: VisitInput) -> dict[str, Any]:
    with closing(db()) as connection:
        existing = connection.execute("SELECT id FROM visits WHERE id=? AND child_id=?", (visit_id, item.child_id)).fetchone()
        child = connection.execute("SELECT * FROM children WHERE id=?", (item.child_id,)).fetchone()
        if not existing or not child: raise HTTPException(404, "Visit or child not found")
        age = age_in_months(child["date_of_birth"], item.visit_date)
        if not 0 <= age <= 59: raise HTTPException(422, "CINUS is for children aged 0-59 months")
        if item.vitamin_a_dose and not 6 <= age <= 59: raise HTTPException(422, "Vitamin A is available for children aged 6-59 months")
        if item.deworming_dose and not 24 <= age <= 59: raise HTTPException(422, "Deworming is available for children aged 24-59 months")
        scores = calculate_growth_scores(child["sex"], child["date_of_birth"], item.visit_date, item.weight, item.height)
        now = datetime.now().isoformat(timespec="seconds")
        connection.execute("UPDATE visits SET visit_date=?,age_months=?,weight=?,height=?,muac=?,edema=?,health_worker=? WHERE id=?", (item.visit_date,age,item.weight,item.height,item.muac,int(item.edema),item.health_worker,visit_id))
        for table in ("growth_assessments","nutrition_screenings","vitamin_a","deworming","development_screenings"):
            connection.execute(f"DELETE FROM {table} WHERE visit_id=?", (visit_id,))
        connection.execute("INSERT INTO growth_assessments (visit_id,waz,haz,whz,underweight_status,stunting_status,wasting_status,generated_at) VALUES (?,?,?,?,?,?,?,?)", (visit_id,scores["waz"],scores["haz"],scores["whz"],z_status(scores["waz"],"Normal","Moderate underweight","Severe underweight"),z_status(scores["haz"],"Normal","Moderate stunting","Severe stunting"),z_status(scores["whz"],"Normal","Moderate wasting","Severe wasting"),now))
        nutrition = "sam" if item.edema else item.nutrition_result
        connection.execute("INSERT INTO nutrition_screenings (visit_id,screening_date,result,referral) VALUES (?,?,?,?)", (visit_id,item.visit_date,nutrition,item.referral))
        if item.vitamin_a_dose: connection.execute("INSERT INTO vitamin_a (child_id,visit_id,dose_number,date_given,provider) VALUES (?,?,?,?,?)", (item.child_id,visit_id,item.vitamin_a_dose,item.visit_date,item.health_worker))
        if item.deworming_dose: connection.execute("INSERT INTO deworming (child_id,visit_id,dose_number,date_given,provider) VALUES (?,?,?,?,?)", (item.child_id,visit_id,item.deworming_dose,item.visit_date,item.health_worker))
        connection.execute("INSERT INTO development_screenings (child_id,visit_id,date,result,notes) VALUES (?,?,?,?,?)", (item.child_id,visit_id,item.visit_date,item.developmental_result,item.development_notes))
        connection.commit()
    return {"id": visit_id, "age_months": age, "scores": scores, "message": "Existing visit updated"}


@app.get("/api/cinus-tally")
def cinus_tally(month: str, region: str = "Amhara", woreda: str = "Bahir Dar", facility: str = "Kidanemihiret", begin_date: str | None = None, end_date: str | None = None) -> dict[str, Any]:
    return build_cinus_tally(month, region, woreda, facility, begin_date, end_date)


def cell(value: Any, bold: bool = False) -> Paragraph:
    style = getSampleStyleSheet()["BodyText"]
    style.fontName = "Helvetica-Bold" if bold else "Helvetica"
    style.fontSize, style.leading, style.alignment = 6.3, 7.2, 1
    return Paragraph(str(value), style)


def add_table(parts: list[Any], title: str, header: list[str], body: list[list[Any]], widths: list[float]) -> None:
    data = [[cell(title, True)] + [""] * (len(widths) - 1), [cell(x, True) for x in header]] + [[cell(x) for x in row] for row in body]
    table = Table(data, colWidths=widths, repeatRows=2)
    table.setStyle(TableStyle([("SPAN", (0, 0), (-1, 0)), ("BACKGROUND", (0, 0), (-1, 1), colors.HexColor("#e9e9e9")), ("GRID", (0, 0), (-1, -1), .45, colors.HexColor("#303030")), ("BOX", (0, 0), (-1, -1), 1.2, colors.black), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    parts.extend([table, Spacer(1, 2)])


def create_cinus_pdf(report: dict[str, Any]) -> BytesIO:
    """Draw the supplied FMOH tally sheet as one fixed A4 landscape form."""
    out = BytesIO(); c = canvas.Canvas(out, pagesize=landscape(A4)); W, H = landscape(A4); t = report["tally"]
    def text(x, y, value, size=7, bold=False, align="left"):
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        {"left": c.drawString, "center": c.drawCentredString, "right": c.drawRightString}[align](x, y, str(value))
    def line(x1, y1, x2, y2, w=.45): c.setLineWidth(w); c.line(x1,y1,x2,y2)
    def box(x1,y1,x2,y2,w=.55): c.setLineWidth(w); c.rect(x1,y1,x2-x1,y2-y1,stroke=1,fill=0)
    def centre(x1,x2,y,val,size=6.4,bold=False): text((x1+x2)/2,y,val,size,bold,"center")
    def shaded(x1,y1,x2,y2): c.setFillColor(colors.HexColor("#e8e8e8")); c.rect(x1,y1,x2-x1,y2-y1,stroke=0,fill=1); c.setFillColor(colors.black)
    # Page 1 - standalone FMOH cover, filled automatically from report metadata.
    cover_logo = ROOT / "backend" / "assets" / "moh_cover_logo.png"
    if cover_logo.exists(): c.drawImage(ImageReader(str(cover_logo)), W/2-95, 390, width=190, height=176, mask="auto")
    text(W/2, 286, "Health Centre /Clinic/Hospital", 38, True, "center")
    text(W/2, 242, "Comprehensive and Integrated Nutrition Service", 31, True, "center")
    text(W/2, 201, "for <5 years Tally Sheet", 31, True, "center")
    fields = [(115, 175, "Region", report["region"]), (250, 405, "Zone/Subcity/Woreda", report["woreda"]), (425, 575, "Health Facility Name", report["facility"]), (600, 673, "Begin Date", report["begin_date"]), (695, 768, "End Date", report["end_date"])]
    for left, right, label, value in fields:
        line(left, 108, right, 108, 1.0); text((left+right)/2, 115, value, 8, False, "center"); text((left+right)/2, 80, label, 13, True, "center")
    c.showPage()
    # Page 2 - the completed landscape tally grid.
    c.setPageSize(landscape(A4)); W, H = landscape(A4)
    # Header matches the official sheet: the original Ministry mark, title, and report fields.
    logo = ROOT / "backend" / "assets" / "moh_logo.png"
    if logo.exists(): c.drawImage(ImageReader(str(logo)), 20, 540, width=132, height=43, mask="auto")
    text(W/2+48,566,"Comprehensive and Integrated Nutrition Service for <5 years Children tally sheet",15,True,"center")
    text(195,544,"Woreda:",9,True); line(234,541,350,541); text(236,544,report["woreda"],8)
    text(402,544,"Facility:",9,True); line(442,541,520,541); text(444,544,report["facility"],8)
    text(195,530,"Year:",9,True); line(220,527,300,527); text(223,530,report["year"],8)
    text(402,530,"Month:",9,True); line(443,527,527,527); text(445,530,report["month"][5:],8)
    # Grid coordinates measured from the supplied FMOH PDF (A4 landscape, in points).
    x0,x1,x2,x3,x4,x5,x6 = 21,173,372,415,731,765,820
    # GMP
    top,bottom=525,403; box(x0,bottom,x6,top,1.8); shaded(x0,bottom,x1,top); shaded(x1,487,x6,525); shaded(x1,403,x2,417); shaded(x3,403,x4,417); centre(x0,x1,503,"GMP",8,True); centre(x1,x6,515,"Weighted during GMP",8,True)
    line(x1,bottom,x1,top,1.2)  # | right edge of merged GMP label cell
    for y in [512,499,487]: line(x1,y,x6,y)
    line(x0,487,x1,487)  # upper border of the first Z-score row continues through the label cell
    for y in [465,439,417]: line(x1,y,x6,y)
    for y in [465,439,417]: line(x0,y,x1,y)  # left GMP labels use separate source-form rows
    for x in [x1,x2,x3,x4,x5]: line(x,487,x,499); line(x,403,x,487)
    line(x5,403,x5,525,1.2)  # full right-side border of the GMP total-count cell
    centre(x1,x3,504,"0-5 months",7,True); centre(x3,x5,504,"6-23 Months",7,True); centre(x1,x2,491,"Tally",7,True); centre(x2,x3,491,"Count",7,True); centre(x3,x4,491,"Tally",7,True); centre(x4,x5,491,"Count",7,True); centre(x5,x6,491,"Total Count",7,True)
    gmp_rows=[("Z score >=  -2(Normal)","normal"),("Z score between  -3  and -2 (moderate under weight)","moderate"),("Z score < -3(Sever under weight)","severe")]
    ys=[476,452,428]
    for (label,key),y in zip(gmp_rows,ys):
        if key == "moderate":
            text(29,y+3,"Z score between  -3  and -2 (moderate",5.6,True); text(29,y-5,"under weight)",5.6,True)
        else: text(29,y,label,5.8,True)
        a,b=t['gmp']['0-5'][key],t['gmp']['6-23'][key]; centre(x1,x2,y,tally_marks(a));centre(x2,x3,y,a);centre(x3,x4,y,tally_marks(b));centre(x4,x5,y,b);centre(x5,x6,y,a+b)
    text(36,407,"Total count",6.8,True); centre(x2,x3,407,sum(t['gmp']['0-5'].values()));centre(x4,x5,407,sum(t['gmp']['6-23'].values()));centre(x5,x6,407,sum(t['gmp']['0-5'].values())+sum(t['gmp']['6-23'].values()))
    # Nutritional screening
    top,bottom=403,208; box(x0,bottom,x6,top,1.8); shaded(x0,bottom,x1,top); shaded(x1,365,x6,403); text(22,379,"Nutritional Screening",7,True); centre(x1,x6,393,"Nutritional Screening for under 5 year",8,True)
    line(x1,bottom,x1,top,1.2)  # | right edge of merged Nutritional Screening label cell
    nx=[21,173,372,415,564,593,731,765,820]
    shaded(nx[1],208,nx[2],233); shaded(nx[3],208,nx[4],233); shaded(nx[5],208,nx[6],233)
    for y in [391,378,365]: line(x1,y,x6,y)
    line(x0,365,x1,365)  # upper border of Normal continues through the label cell
    for y in [316,270,233]: line(x1,y,nx[8],y)
    for y in [316,270,233]: line(x0,y,x1,y)  # Normal / MAM / SAM labels are separate rows
    for x in nx[1:-1]: line(x,365,x,378); line(x,208,x,365)
    line(nx[7],208,nx[7],403,1.2)  # full right-side border of Nutrition total-count cells
    centre(nx[1],nx[3],383,"0-5 months",7,True);centre(nx[3],nx[5],383,"6 - 23 Months",7,True);centre(nx[5],nx[7],383,"24 - 59 Months",7,True)
    for a,b in [(nx[1],nx[2]),(nx[3],nx[4]),(nx[5],nx[6])]: centre(a,b,369,"Tally",7,True)
    for a,b in [(nx[2],nx[3]),(nx[4],nx[5]),(nx[6],nx[7])]: centre(a,b,369,"Count",7,True)
    centre(nx[7],nx[8],369,"Total count",7,True)
    screen_rows=[("Normal","normal"),("Moderate Acute Malnutrition(MAM)","mam"),("Sever Acute Malnutrition (SAM)","sam")]
    for (label,key),y in zip(screen_rows,[340,293,247]):
        text(36,y,label,6.8,True); total=0
        for age,ta,co in [("0-5",nx[1],nx[2]),("6-23",nx[3],nx[4]),("24-59",nx[5],nx[6])]:
            n=t['screen'][age][key]; total+=n; centre(ta,co,y,tally_marks(n)); centre(co,co+(nx[nx.index(co)+1]-co),y,n)
        centre(nx[7],nx[8],y,total)
    text(22,216,"Total screened for Malnutrition(Count)",6.7,True); centre(nx[2],nx[3],216,sum(t['screen']['0-5'].values()));centre(nx[4],nx[5],216,sum(t['screen']['6-23'].values()));centre(nx[6],nx[7],216,sum(t['screen']['24-59'].values()));centre(nx[7],nx[8],216,sum(sum(g.values()) for g in t['screen'].values()))
    # Vitamin A
    top,bottom=208,156; box(x0,bottom,x6,top,1.8); shaded(x0,bottom,x1,top); shaded(x1,182,x6,208); text(22,184,"Vitamin A",7,True); centre(x1,x6,197,"Vitamin A",8,True); line(x1,195,x6,195); line(x1,182,x6,182); line(x1,169,x6,169)
    line(x1,bottom,x1,top,1.2)  # | right edge of merged Vitamin A label cell
    line(x0,182,x1,182); line(x0,169,x1,169)
    for x in [x1,x3,x5]: line(x,156,x,182)
    line(x5,156,x5,208,1.2)  # full right-side border of Vitamin A total-count cell
    centre(x1,x3,186,"6-11 months",7,True);centre(x3,x5,186,"12-59 months",7,True);centre(x5,x6,186,"Total Count",7,True)
    for label,key,y in [("Vitamin A  One  doses suplimented","one",175),("Vitamin A  Two doses suplimented","two",161)]:
        a,b=t['vitamin']['6-11'][key],t['vitamin']['12-59'][key]; text(30,y,label,6.5,True);centre(x1,x3,y,a);centre(x3,x5,y,b);centre(x5,x6,y,a+b)
    # Deworming
    top,bottom=156,104; box(x0,bottom,x6,top,1.8); shaded(x0,130,x6,156); centre(x0,x6,146,"Deworming (24-59 months)",8,True); line(x0,143,x6,143); line(x0,130,x6,130); line(x0,117,x6,117); line(x1,104,x1,143);line(x5,104,x5,143)
    text(22,134,"Deworming (24-59 month)",6.6,True);centre(x1,x5,134,"Tally",7,True);centre(x5,x6,134,"Count",7,True)
    for label,key,y in [("Received   one dose","one",123),("Received   two doses","two",111)]: text(36,y,label,6.5,True);centre(x1,x5,y,tally_marks(t['deworming'][key]));centre(x5,x6,y,t['deworming'][key])
    # Developmental milestone
    top,bottom=104,20; box(x0,bottom,x6,top,1.8); shaded(x0,76,x6,104); shaded(x0,62,x6,76); centre(x0,x6,96,"Developmental milestone",8,True); line(x0,91,x6,91);line(x0,76,x6,76);line(x0,62,x6,62);line(x0,48,x6,48);line(x0,34,x6,34);line(x0,20,x6,20);line(x1,20,x1,91)
    for x in [x2,x3,x4,x5]: line(x,20,x,76);line(x,76,x,91)
    centre(x1,x3,81,"0-23 months",7,True);centre(x3,x5,81,"24-59 months",7,True);centre(x5,x6,81,"Total Count",7,True)
    centre(x1,x2,67,"Tally",7,True);centre(x2,x3,67,"Count",7,True);centre(x3,x4,67,"Tally",7,True);centre(x4,x5,67,"Count",7,True)
    # Dedicated data rows below the Tally / Count subheader (source form: CDD, SDD, NDD).
    for (label,key),y in zip([("Confirmed developmental delay(CDD)","cdd"),("Suspected  developmental delay(SDD)","sdd"),("No developmental delay(NDD)","ndd")],[53,39,25]):
        a,b=t['development']['0-23'][key],t['development']['24-59'][key];text(22,y,label,5.7,True);centre(x1,x2,y,tally_marks(a));centre(x2,x3,y,a);centre(x3,x4,y,tally_marks(b));centre(x4,x5,y,b);centre(x5,x6,y,a+b)
    c.showPage(); c.save(); out.seek(0); return out


@app.get("/api/cinus-tally/pdf")
def cinus_tally_pdf(month: str, region: str = "Amhara", woreda: str = "Bahir Dar", facility: str = "Kidanemihiret", begin_date: str | None = None, end_date: str | None = None):
    report = build_cinus_tally(month, region, woreda, facility, begin_date, end_date)
    return Response(content=create_cinus_pdf(report).getvalue(), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="CINUS-tally-{month}.pdf"'})


@app.get("/api/reports/anc")
def anc_report() -> list[dict[str, Any]]:
    return rows("SELECT p.mrn,p.full_name,m.contact_date,m.gestational_age,m.blood_pressure,m.risk_flags,m.next_appointment FROM maternal_records m JOIN patients p ON p.id=m.patient_id ORDER BY m.contact_date DESC")


if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


@app.get("/{path:path}")
def serve_frontend(path: str):
    index = DIST / "index.html"
    if index.exists():
        return FileResponse(index)
    return {"message": "Clinic API is running. Build the frontend with npm run build."}
