# Architecture & design decisions

## 1. Two layers, one contract

The system is split at a deliberately narrow interface: **observation events**.

| Layer | Knows about | Doesn't know about |
|---|---|---|
| Vision worker (`vision/`) | pixels, boxes, tracks, polygons | tasks, staff, SLAs |
| Operations engine (`backend/app/engine/ops.py`) | tables, tasks, alerts, staff, orders | pixels |

Event vocabulary (`backend/app/schemas.py::EventType`):

| Event | Emitted when |
|---|---|
| `table.occupied {party_size}` | seated people at a table zone for ≥ `occupy_s` |
| `table.vacated` | party gone for ≥ `vacate_s` (tolerates occlusion) |
| `table.attended` | a standing person arrives at a table and stays ≥ `visit_s` (staff visit) |
| `table.surface {items}` | stable count of tableware/food on the table surface |
| `service.hand_raised` | seated person's wrist held above head/shoulders ≥ 1 s |
| `people.count {inside}`, `entrance.enter/exit` | occupancy + footfall |
| `camera.heartbeat` | every 10 s (offline detection) |

Why: the CV layer can be swapped (YOLO version, a different tracker, a cloud model,
or the **simulator**) without touching business logic, and the business logic is unit-tested
deterministically without any video.

## 2. Operations engine

- **Two entry points:** `handle_event(db, event, now)` reacts to observations; `tick(db, now)`
  (every 2 s) enforces time-based rules. Both take an explicit `now`, so tests are deterministic.
- **Table state machine:** `vacant → occupied → needs_cleaning → (clean task verified) → vacant`.
  A party sitting at an uncleaned table cancels the clean task and raises an alert.
- **Task lifecycle:** `pending → assigned → awaiting_verification → verified`, or
  `verification_failed` / `verification_uncertain`, which go to human review (confirm or send back).
- **Alerts are de-duplicated by key** (e.g. `assist_unattended:task:12`), so a condition produces
  exactly one alert, which is auto-resolved when the condition clears (the related task closes).
- **Concurrency:** all writes go through one process-wide lock; the engine's checks are
  read-then-write. One process comfortably serves one restaurant.
- **Transactional outbox:** WebSocket messages and phone pushes are queued on the DB session
  and sent only after commit (`bus.py`), so clients never see rolled-back state.

## 3. AI verification (Module 6)

Staff confirmation is stage 1. Stage 2 evaluates camera evidence recorded in the
append-only `observations` table:

| Task | Verified when | Failed when | Uncertain when |
|---|---|---|---|
| Clean table | fresh surface reading = 0 items **and** a staff visit since the task was created | fresh reading shows items left | surface clear but no visit seen, or no fresh reading within `verify_window_s` |
| Assist / attend | staff visit seen after the request | – | no visit seen within the window |
| Deliver order | POS reports delivered, or staff visit after ready | – | no evidence within the window |

"Fresh" means observed no earlier than `verify_grace_s` before the staff confirmation.
Uncertain and failed results never auto-close: a person decides. Overrides are recorded as
`verified_by = manual`, so analytics separate AI-verified from human-confirmed work.

## 4. Vision heuristics and their limits

Documented in `vision/vision/zones.py`. Most important:
- Only **seated** people can make a table occupied (a busser cleaning for 30 s must not).
- Staff are distinguished from diners by **behaviour** (arrive later, stand, leave), not identity.
  A late-arriving diner may register as a "visit"; that is why verification has an uncertain path.
- Hand raise uses pose keypoints with a hold time and a 30 s cooldown per table.
- Surface clutter uses COCO tableware/food classes, reported only once stable across 3 samples.

## 5. Known gaps / next steps
- Alembic migrations (currently `create_all`); user accounts & roles for counter/manager.
- Evaluate detection accuracy on recorded restaurant footage (precision/recall per event type).
- Web Push (service worker) in addition to ntfy for manager notifications.
- Vendor-specific POS adapters mapping onto `/api/pos/orders`.
