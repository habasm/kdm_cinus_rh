# CINUS Clinic Reporting System

Local React + Vite and FastAPI application based on the supplied FMOH ANC card and CINUS under-5 nutrition tally sheet.

## Included workflows

- Patient registration with Ethiopian dummy data seeded on first run.
- ANC follow-up recording: pregnancy history, examination, risk flags, services, plan and next appointment.
- Per-child under-5 service records: GMP, nutrition screening, Vitamin A, deworming and developmental milestones.
- Automatic CINUS monthly aggregation by the official age bands, including printable tally marks and counts.
- One-click A4 landscape CINUS PDF generation that follows the supplied Ministry of Health tally structure.
- Summary reports for ANC and CINUS data.
- SQLite persistence (`clinic.db`), created automatically.

## Run locally

Open two terminals in this project folder.

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

Then open the Vite URL shown in the terminal, normally `http://localhost:5173`.

## Single-server deployment

```powershell
cd frontend
npm run build
cd ..
C:\Users\afabi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

FastAPI serves `frontend/dist` and the API from the same address at `http://localhost:8000`.
