# Kidanemihiret Integrated Maternal RH and CINUS System

Kidanemihiret Integrated Maternal RH and CINUS System is a local clinical workspace for maternal reproductive health care, under-five child nutrition services, birth notification, postpartum follow-up, reporting and staff accountability.

The system is designed for everyday facility work: each staff member signs in, sees only the work areas assigned to them, records clinical information once, and the saved records are reused for history, follow-up, audit review and HMIS-style reporting.

## Main work areas

- Login and role-based navigation for clinical staff, data clerks and administration.
- Admin-only user management with access assignment by checkbox.
- Audit review showing who logged in, who recorded information and what actions were saved.
- CINUS child nutrition workspace.
- Maternal RH care workspace.
- CINUS and Maternal RH report previews, source tables and downloads.
- Local seeded demo data for testing workflows.

## CINUS workspace

The CINUS area supports child registration, follow-up, nutrition assessment and reporting.

- Compact child registration with a two-column form and recorded-children view.
- Child follow-up recording for weight, height or length, MUAC, oedema, nutrition status, referral, Vitamin A, deworming and development screening.
- Automatic WHO growth assessment and exact z-score value display from the recorded measurements.
- Automatic nutrition classification updates from MUAC and oedema.
- Safeguards for Vitamin A and deworming so yearly dose rules are respected.
- Compact child history and recommendations panel.
- CINUS HMIS report preview and source table in separate tabs.
- PDF and Excel downloads from a compact resource menu.

## Maternal RH workspace

The Maternal RH area supports the full care cycle from registration to postpartum care, with the ability to close a cycle at any stage.

- Client and risk registration with a compact step-based form.
- LNMP-based expected delivery date calculation.
- ANC contact recording from contact 1 to contact 8.
- Contact-specific fields based on the RH card, with non-applicable shaded fields hidden for that contact.
- Recommended contact badges while still allowing manual clinical recording when needed.
- Submitted ANC contacts become view-only, so previous contacts are not edited after permanent submission.
- Labor admission, partograph-style observation charts, delivery summary and newborn recording.
- Observation entry resets after saving, ready for the next observation.
- Birth notification form with multiple babies in one notification for twin and multiple births.
- Optional marking of each baby for CINUS registration.
- Postpartum mother and newborn follow-up by period, with submitted sections becoming view-only.
- Cycle close and reopen control near the page actions.
- Cycle summary popup showing the recorded maternal information and the latest stage reached.

## Reports

The reporting area is built from the information recorded in the clinical workspaces.

- CINUS report tab includes HMIS report preview, source table and compact download resources.
- Maternal RH report tab includes HMIS report preview, source table and Excel download.
- Individual RH card pages can be downloaded from the related clinical tab where the information is recorded.
- Reports use saved local records, including recorder information where available.

## User access and accountability

Admin accounts are only for administration and audit review. Admin users do not see the clinical CINUS and Maternal RH workspaces.

Clinical users see only the work assigned to their account. One user can be assigned multiple work areas, and each saved record keeps the logged-in worker where the workflow supports recorder tracking.

Examples:

- One worker may register children only.
- Another worker may record CINUS follow-up visits.
- A maternal registrar may create the RH client record.
- An ANC provider may record ANC contacts.
- A delivery provider may record labor, delivery, newborn and birth notification information.
- A reporter may only open reporting pages.

## Demo login accounts

These accounts are included in the fresh demo seed.

| Username | Password | Full name | Main access |
| --- | --- | --- | --- |
| `admin` | `@admin365` | System administrator | Admin user management and audit only |
| `child_reg` | `child123` | Selamawit Bekele | CINUS overview and child registry |
| `followup` | `follow123` | Meseret Tola | CINUS overview and follow-up visits |
| `cinus_report` | `report123` | Dawit Alemayehu | CINUS overview and CINUS reporting |
| `rh_registrar` | `rh123` | Hana Wolde | Maternal client and risk registration |
| `anc_provider` | `anc123` | Marta Girma | Maternal clients and ANC contacts |
| `delivery_provider` | `delivery123` | Almaz Worku | Labor, delivery, newborn and birth notification |
| `postnatal_provider` | `post123` | Tigist Fekadu | Postpartum care |
| `rh_reporter` | `rhreport123` | Yonas Kebede | Maternal RH reporting |
| `clinic_lead` | `lead123` | Rahel Tesfaye | Multiple CINUS and Maternal RH clinical areas |

These passwords are for local demo use only.

## Demo data

The current seeded database is a fresh demo set with:

- 30 CINUS child records.
- 33 child follow-up visits.
- 30 maternal RH records.
- Mixed maternal cycle states, including open and closed cycles.
- Records at different stages, including registration, ANC, labor, delivery, birth notification and postpartum.
- 10 system users with different access assignments.
- Audit records for logins, clinical saves and user activity.

To intentionally reset the local database and create a new fresh demo set, run:

```powershell
$env:ALLOW_DEMO_DATA_RESET='1'
..\.venv\Scripts\python.exe backend\seed_more_records.py
```

The reset creates a database backup first. Backups are saved beside the database using names like `clinic.backup-YYYYMMDDHHMMSS.db`.

## Run locally

Open two terminals in this project folder.

Terminal 1 starts the clinical API:

```powershell
..\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Terminal 2 starts the web interface:

```powershell
cd frontend
npm install
npm run dev
```

Then open the address shown by the web interface, usually `http://localhost:5173`.

## Single-server run

For a built version served by the API:

```powershell
cd frontend
npm run build
cd ..
..\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Then open `http://localhost:8000`.

## Local files

- `clinic.db` stores the local application data.
- `report_forms.xlsx` is the report workbook reference used for Excel-style reporting.
- `clinic.backup-*.db` files are local database backups created before intentional demo resets.

## Important workflow notes

- Submitted clinical sections are view-only after final submission.
- Closed maternal cycles are view-only until reopened by an allowed user.
- Admin accounts are for user administration and audit review only.
- Demo records are for testing and training, not production patient data.
