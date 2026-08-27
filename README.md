# Kidanemihiret Integrated Clinical System

Kidanemihiret Integrated Clinical System is a facility workspace for recording maternal health care, child nutrition follow-up, birth notification, postpartum care and official CINUS reporting. It helps clinic staff capture routine service data once, keep track of who recorded each action, and prepare reports from the saved records.

## System actions

- Provides a compact login screen for facility staff and administration.
- Supports multiple users with role-based access to specific work areas.
- Keeps admin users limited to user administration and audit review.
- Lets admin create users, update passwords, deactivate accounts and assign access with checkboxes.
- Shows an admin audit summary of logins, user changes, clinical saves and records created by each worker.
- Records the logged-in worker on child registration, child follow-up visits, maternal RH cards and ANC contacts.
- Provides a CINUS workspace for overview, child registry, follow-up visits and reporting.
- Registers children with a compact two-column form and a recorded-children view.
- Shows who recorded child records, including older records that have no saved recorder.
- Records child follow-up visits with weight, height/length, MUAC, oedema, nutrition result, referral, Vitamin A, deworming and developmental screening.
- Calculates WHO growth z-score values automatically from the entered measurements.
- Updates nutrition classification automatically from MUAC and oedema.
- Applies age and yearly-dose safeguards for Vitamin A and deworming recording.
- Keeps child visit history visible in a compact right-side panel.
- Generates CINUS monthly summaries using official age bands and source visit records.
- Produces a printable CINUS PDF report.
- Provides Maternal RH care tabs for client/risk registration, ANC contacts, labor/delivery/newborn, postpartum and RH card reporting.
- Auto-calculates expected delivery date from LNMP.
- Records ANC contacts in a compact step-based interface with recommended contact badges and view-only locking for already recorded contacts.
- Provides labor monitoring with partograph-style charts, compact observation entry and observation history.
- Records delivery and newborn information with compact grouped fields.
- Adds a birth notification/registration form with right-side birth history.
- Supports adding multiple children to one birth notification for twin or multiple births.
- Records postpartum mother and newborn follow-up in compact period-based sections.
- Stores records locally and seeds demo data on first run.

## Default login accounts

These demo users are created automatically when the system database has no users yet.

| Username | Password | Main access |
| --- | --- | --- |
| `admin` | `@admin365` | User administration only |
| `child_reg` | `child123` | CINUS overview and child registry |
| `followup` | `follow123` | CINUS overview and follow-up visits |
| `reporter` | `report123` | CINUS overview and CINUS reporting |
| `anc` | `anc123` | Maternal client/risk registration and ANC contacts |
| `delivery` | `delivery123` | Labor, delivery and newborn recording |
| `postpartum` | `post123` | Postpartum care recording |

The admin user can open **Admin access** in the sidebar to create more users, deactivate users, change passwords, assign work areas with checkboxes and review the audit summary. Admin accounts are kept for user administration and audit review only; clinical work should be assigned to physician, nurse or data clerk accounts. A worker only sees the CINUS or Maternal RH tabs assigned to that account.

## Record accountability

New child registrations and follow-up visits are saved with the logged-in staff member. Maternal RH cards keep the last recorder and ANC contact metadata so different contacts can show which worker recorded them. This supports workflows where one person registers the client, another records ANC contact 1, and a different provider records later contacts.

## Run locally

For local testing, open two terminals in this project folder.

```powershell
# Terminal 1: API server
C:\Users\afabi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pip install -r requirements.txt
C:\Users\afabi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m uvicorn backend.main:app --reload
```

```powershell
# Terminal 2: web interface (development)
cd frontend
npm install
npm run dev
```

Then open the web address shown in the terminal, normally `http://localhost:5173`.

## Single-server deployment

```powershell
cd frontend
npm run build
cd ..
C:\Users\afabi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

The single-server option serves the full system from `http://localhost:8000`.
