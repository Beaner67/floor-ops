# Floor Ops: AI Restaurant Operations Intelligence

Final-year CSE project. Existing CCTV cameras + computer vision watch the **operational
state** of a restaurant (tables, service requests, cleaning). The system turns that into
tasks for staff, coordinates them through one counter device, **verifies completed work
from camera evidence**, and alerts the manager.

```
CCTV (RTSP) ─▶ vision worker ──events──▶ backend: operations engine ──WebSocket──▶ counter dashboard
               YOLO pose + ByteTrack     table state · tasks · alerts                manager phone view
               zone logic, debounce      AI verification · analytics                 staff phone view
POS ──────────────────────orders──────▶  (FastAPI + SQLAlchemy)          ──push──▶   ntfy (optional)
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for design decisions.

## Repository layout

| Path | What |
|---|---|
| `backend/` | FastAPI app: operations engine, REST + WebSocket API, analytics, tests |
| `vision/vision/` | Camera worker: YOLO + ByteTrack, table-zone logic, zone calibration tool |
| `vision/simulate.py` | Restaurant simulator: drives the whole system with **no cameras** |
| `frontend/` | React (Vite + TS) counter dashboard, manager view, staff view, reports |

## Dashboard UI

Dark "command centre" design. Design tokens (colours, spacing, radii, motion) live in
`frontend/src/theme.css`; every number shown is derived from live state in `frontend/src/derive.ts`.

| Component | Role |
|---|---|
| `App.tsx` (AppShell), `CommandSidebar`, `CommandHeader`, `ConnectionStatus` | Shell, navigation, live camera / POS / sync health |
| `OperationsKPI` | Active tables, available tables, pending tasks, critical alerts |
| `LiveFloorMap` → `FloorTableTile` | Interactive floor plan with status, timers, attention rings |
| `TableInspector` → `SimulationControls` | Table details and actions; demo camera events kept separate |
| `TaskBoard` → `TaskColumn` → `TaskCard` | To assign → In progress → Needs review |
| `AlertsCentre` → `AlertCard` | Severity-grouped alerts; right panel ≥1440px, drawer below, tab on phones |

POS health is real: the backend records when the POS last sent data (`integrations` in `/api/state`)
and shows it as *idle* after `RI_POS_STALE_S` (default 300 s) without data.

## Run it (Windows, PowerShell)

Prerequisites: Python 3.12, Node 20+.

**1. Backend** (http://localhost:8000, API docs at `/docs`)
```powershell
cd backend; py -3.12 -m venv .venv; .\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn app.main:app --port 8000
```

**2. Dashboard** (http://localhost:5173; it's also reachable from tablets/phones on the same Wi-Fi)
```powershell
cd frontend; npm install; npm run dev
```

**3a. Demo without cameras** (pick one)
```powershell
backend\.venv\Scripts\python vision\simulate.py               # you act as the counter staff
```
```powershell
backend\.venv\Scripts\python vision\simulate.py --auto-staff  # fully autonomous
```
You can also tick **Demo controls** on the counter screen and click a table to fire
individual camera events (party sits, hand raised, staff visits, dishes left…).

**3b. With real cameras**
```powershell
cd vision; py -3.12 -m venv .venv; .\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python -m vision.calibrate --source 0     # draw table zones, paste into config.yaml
copy config.example.yaml config.yaml                      # then edit sources & zones
.\.venv\Scripts\python -m vision.run --config config.yaml --show
```
`source` can be an RTSP URL, a webcam index, or a recorded video file (recommended for a repeatable viva demo).

## Tests
```powershell
cd backend; .\.venv\Scripts\python -m pytest -q        # engine + API (13 tests)
```
```powershell
cd vision; ..\backend\.venv\Scripts\python -m pytest -q tests   # zone logic (9 tests, no CV deps)
```

## Configuration
All thresholds are environment variables with the `RI_` prefix (or `backend/.env`); see
`backend/app/config.py`. Defaults are short for demos (for example, an unanswered raised hand
escalates after 60 s). Key ones:

| Variable | Default | Meaning |
|---|---|---|
| `RI_DATABASE_URL` | SQLite file | e.g. `postgresql+psycopg://ri:ri@localhost:5432/ri` (see `docker-compose.yml`) |
| `RI_DEVICE_KEY` | empty | shared secret for cameras/POS (`X-Device-Key` header) |
| `RI_ASSIST_RESPONSE_S` | 60 | raised hand → staff visit expected |
| `RI_SEATED_UNATTENDED_S` | 120 | seated with no staff visit at all |
| `RI_CLEAN_DUE_S` | 240 | cleaning task deadline |
| `RI_VERIFY_WINDOW_S` | 30 | how long AI waits for camera evidence |
| `RI_NOTIFY_URL` | empty | ntfy topic URL for manager phone push |

## Privacy principles
- No face recognition, no re-identification, no stored video or images. Frames are processed in memory.
- Only operational facts are stored (table 3 occupied at 19:02; surface clear).
- Staff reports show task counts and durations, with no scores or rankings.
- When the AI is unsure, a human decides (`verification_uncertain` → manual check).
