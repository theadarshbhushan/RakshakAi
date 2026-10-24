# RakshakAI (रक्षकAI)

Privacy-First AI Campus & Hostel Safety Platform with Explainable Incident Fusion.

## Run the Whole Project

To launch both the FastAPI backend and React Vite frontend together on Windows:

```powershell
.\start_all.ps1
```

This will launch:
1. **FastAPI Backend**: `http://127.0.0.1:8000` (API docs at `/docs`, OpenAPI spec at `/api/v1/openapi.json`)
2. **React + Vite Frontend**: `http://localhost:5173` with proxy `/api -> http://localhost:8000`

### Manual Run

#### Backend
```powershell
cd backend
..\.venv\Scripts\Activate.ps1
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

#### Frontend
```powershell
cd frontend
npm install
npm run dev
```

### Demo Accounts
- **Chief Warden / Owner**: `owner@sunrise.demo` / `Owner@12345`
- **Hostel Administrator**: `admin@sunrise.demo` / `Admin@12345`
- **Floor Warden**: `warden@sunrise.demo` / `Warden@12345`
- **Security Guard**: `guard@sunrise.demo` / `Guard@12345`
- **Compliance Auditor**: `auditor@sunrise.demo` / `Auditor@12345`
- **Second Hostel (Tenant Isolation)**: `owner@greenvalley.demo` / `Owner@12345`
