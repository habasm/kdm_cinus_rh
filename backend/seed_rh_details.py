"""Fill missing maternal RH card tabs with realistic demo content."""
import json
import sqlite3
from datetime import date, timedelta, datetime
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / "clinic.db"
now = datetime.now().isoformat(timespec="seconds")
anc_fields = {
    "Present pregnancy history / complaint": "No danger signs; fetal movement present",
    "Family / social history": "Lives with family; no tobacco or alcohol",
    "General appearance": "Well and stable",
    "Blood pressure": "112/72 mm Hg",
    "Weight": "61.5 kg",
    "Pallor": "Absent",
    "Breast": "Normal",
    "Chest": "Clear",
    "Fundal height (weeks)": "Appropriate for gestation",
    "Fetal heart beat": "146 bpm",
    "Presentation": "Cephalic",
    "Pelvic assessment": "Not indicated",
    "Ultrasound": "Viable singleton pregnancy",
    "Haemoglobin": "12.0 g/dL",
    "Blood group and Rh": "O positive",
    "RPR / VDRL": "Non-reactive",
    "HIV PITC - pregnant client": "Negative; counselled",
    "HIV PITC - partner": "Negative",
    "HBsAg": "Negative",
    "Urine test": "Normal; no protein/glucose",
    "Active TB screening": "No symptoms",
    "75 g oral glucose test": "Normal",
    "Preventive anti-helminthic treatment": "Given",
    "Malaria prevention / ITN": "ITN use reinforced",
    "Td vaccination": "Td dose given",
    "Iron and folic acid dose": "30 tablets supplied",
    "Daily calcium supplementation": "Counselled and supplied",
    "Nutrition / healthy eating": "Counselled",
    "PMTCT and testing": "Counselled",
    "Family planning": "Postpartum options discussed",
    "Breastfeeding": "Exclusive breastfeeding counselled",
    "Hygiene": "Counselled",
    "Birth preparedness and complication readiness plan": "Transport and emergency plan reviewed",
    "Assessment / danger signs identified": "Pregnancy progressing normally",
    "Action taken": "Routine ANC care continued",
    "Provider name and signature": "Sr. Almaz Worku",
}
labor = {
    "Date of admission": "2026-08-21", "Time of admission": "07:30", "Ruptured membranes": "No",
    "Fetal heart rate": "144 bpm", "Amniotic fluid": "Clear", "Moulding": "None", "Cervical dilation": "6 cm",
    "Descent of head": "3/5 palpable", "Contractions / 10 min": "4 in 10 minutes", "Oxytocin U/L": "None",
    "Drops / min": "0", "Pulse": "82 bpm", "Blood pressure": "118/74", "Temperature": "36.7 C",
    "Urine protein": "Nil", "Urine acetone": "Nil", "Urine volume": "Adequate", "Drugs / IV fluids": "Ringer's lactate",
}
delivery = {
    "Delivery date": "2026-08-21", "Delivery time": "14:10", "Mode of delivery": "SVD", "Placenta status": "Complete",
    "Newborn number": "Single", "Newborn status": "Alive", "Apgar score": "8/10, 9/10", "Sex": "Female",
    "Birth weight (g)": "3150", "Length (cm)": "50", "Term / preterm": "Term", "BCG date": "2026-08-21",
    "OPV 0 date": "2026-08-21", "HBV birth dose": "Given", "Vitamin K": "Given", "Complications": "None",
    "HIV result": "Negative", "Delivered by": "Sr. Almaz Worku", "Remark": "Mother and newborn stable",
}
postpartum = {}
for period, day in (("24 hours", "2026-08-22"), ("25–48 hours", "2026-08-23"), ("49–72 hours", "2026-08-24"), ("73 hours–7 days", "2026-08-27"), ("8–42 days", "2026-09-18")):
    for key, value in {
        "Date": day, "BP": "116/72", "PR / RR": "78 / 18", "Temperature": "36.6 C", "Uterus / PPH": "Firm; no PPH",
        "Anemia": "Absent", "Baby breathing": "Normal", "Breastfeeding": "EBF established", "Baby weight": "3100 g",
        "Immunization": "BCG and OPV 0 given", "HIV tested": "Reviewed", "Feeding option": "Exclusive breastfeeding",
        "Action taken": "Routine follow-up and counselling", "Remark": "Mother and baby well",
    }.items():
        postpartum[period + key] = value

with sqlite3.connect(DB) as db:
    records = db.execute("SELECT id,mrn,payload FROM rh_cards ORDER BY id").fetchall()
    for index, (card_id, mrn, raw) in enumerate(records):
        card = json.loads(raw)
        sections = card.setdefault("sections", {})
        anc = sections.setdefault("anc", {})
        start = date(2026, 3, 2) + timedelta(days=index * 3)
        for contact in range(1, 9):
            prefix = str(contact)
            for key, value in anc_fields.items():
                anc.setdefault(prefix + key, value)
            anc.setdefault(prefix + "Date of contact", (start + timedelta(days=(contact - 1) * 21)).isoformat())
            anc.setdefault(prefix + "Gestational age", f"{10 + contact * 4} weeks")
            anc.setdefault(prefix + "Next appointment", (start + timedelta(days=contact * 21)).isoformat())
        sections.setdefault("labor", {}).update({k: sections["labor"].get(k, v) for k, v in labor.items()})
        sections.setdefault("delivery", {}).update({k: sections["delivery"].get(k, v) for k, v in delivery.items()})
        sections.setdefault("postpartum", {}).update({k: sections["postpartum"].get(k, v) for k, v in postpartum.items()})
        risks = card.setdefault("risk_answers", {})
        if index % 4 == 1:
            risks.setdefault("Age more than 35 years", True)
            risks.setdefault("Chronic hypertension", True)
        elif index % 4 == 2:
            risks.setdefault("Age less than 18 years", True)
        elif index % 4 == 3:
            risks.setdefault("Previous hypertension / pre-eclampsia / eclampsia", True)
        db.execute("UPDATE rh_cards SET payload=?,updated_at=? WHERE id=?", (json.dumps(card), now, card_id))
    db.commit()
    print({"rh_cards": db.execute("SELECT COUNT(*) FROM rh_cards").fetchone()[0], "updated": len(records)})
