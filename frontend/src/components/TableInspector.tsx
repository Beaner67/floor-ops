import { Ban, FlaskConical, Hand, LogIn, LogOut, RotateCcw, Sparkles, UtensilsCrossed, UserCheck, X } from "lucide-react";
import { api } from "../api";
import { TABLE_STATUS_LABEL, TASK_TYPE_LABEL, needsReview } from "../derive";
import { clock, dur, since } from "../time";
import type { Table, Task } from "../types";
import { ConfirmButton } from "./ui";

/** Selected-table inspector: facts, active tasks, operational actions, and (separately) simulation. */
export function TableInspector({ table: t, tasks, now, demo, onClose }: {
  table: Table; tasks: Task[]; now: number; demo: boolean; onClose: () => void;
}) {
  const surface =
    t.surface_items == null
      ? { text: "No camera reading yet", tone: "muted" }
      : t.surface_items === 0
        ? { text: "Clear", tone: "ok" }
        : { text: `${t.surface_items} item${t.surface_items > 1 ? "s" : ""} detected`, tone: "warn" };

  return (
    <section className="card inspector" aria-labelledby="insp-title">
      <div className="card-head">
        <div className="insp-title">
          <h2 id="insp-title">Table {t.label}</h2>
          <span className={`pill st-${t.status}`}>{TABLE_STATUS_LABEL[t.status]}</span>
        </div>
        <button type="button" className="icon-btn" onClick={onClose} aria-label="Close table details">
          <X size={16} />
        </button>
      </div>

      <dl className="facts">
        <div><dt>In this state</dt><dd className="tabular">{dur(since(t.status_since, now))}</dd></div>
        <div>
          <dt>Party</dt>
          <dd>{t.status === "occupied" ? `${t.party_size || "?"} of ${t.capacity}` : `${t.capacity} seats`}</dd>
        </div>
        <div>
          <dt>First staff visit</dt>
          <dd>
            {t.status !== "occupied" ? <span className="muted">–</span>
              : t.first_attended_at ? <span className="ok">{clock(t.first_attended_at)} · after {dur((Date.parse(t.first_attended_at) - Date.parse(t.seated_at ?? t.first_attended_at)) / 1000)}</span>
                : <span className="warn">Not yet · waiting {dur(since(t.seated_at, now))}</span>}
          </dd>
        </div>
        <div>
          <dt>Surface (camera)</dt>
          <dd>
            <span className={surface.tone}>{surface.text}</span>
            {t.surface_seen_at && <span className="muted"> · {dur(since(t.surface_seen_at, now))} ago</span>}
          </dd>
        </div>
        <div><dt>Camera</dt><dd className="muted">{t.camera_id ?? "Not assigned"}</dd></div>
      </dl>

      <div className="insp-section">
        <h3 className="eyebrow">Active tasks <span className="count">{tasks.length}</span></h3>
        {tasks.length === 0 ? (
          <p className="muted small">No open tasks for this table.</p>
        ) : (
          <ul className="insp-tasks">
            {tasks.map((k) => (
              <li key={k.id} className={`p-${k.priority}`}>
                <span>{k.title}</span>
                <span className="muted small">
                  {needsReview(k) ? "Needs review" : k.status === "awaiting_verification" ? "Verifying"
                    : k.staff_name ?? "Unassigned"} · {TASK_TYPE_LABEL[k.type] ?? k.type}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="insp-section">
        <h3 className="eyebrow">Table actions</h3>
        <div className="btn-row">
          {t.status !== "vacant" && (
            <ConfirmButton icon={RotateCcw} onConfirm={() => api.setTable(t.id, "vacant")}
              confirmLabel={tasks.length ? `Cancel ${tasks.length} task(s) & reset?` : "Confirm reset"}>
              Reset to available
            </ConfirmButton>
          )}
          {t.status !== "out_of_service" && (
            <ConfirmButton icon={Ban} onConfirm={() => api.setTable(t.id, "out_of_service")} confirmLabel="Confirm close">
              Close table
            </ConfirmButton>
          )}
        </div>
      </div>

      {demo && <SimulationControls label={t.label} cameraId={t.camera_id} />}
    </section>
  );
}

/** Sends the same events a camera would. Visually separated from real operations. */
export function SimulationControls({ label, cameraId }: { label: string; cameraId: string | null }) {
  const ev = (type: string, data: Record<string, unknown> = {}) => api.event(type, label, cameraId, data);
  const actions = [
    { label: "Party sits", icon: LogIn, run: () => ev("table.occupied", { party_size: 2 }) },
    { label: "Hand raised", icon: Hand, run: () => ev("service.hand_raised") },
    { label: "Staff visits", icon: UserCheck, run: () => ev("table.attended") },
    { label: "Party leaves", icon: LogOut, run: () => ev("table.vacated") },
    { label: "Surface clear", icon: Sparkles, run: () => ev("table.surface", { items: 0 }) },
    { label: "Dishes left", icon: UtensilsCrossed, run: () => ev("table.surface", { items: 3 }) },
  ];
  return (
    <div className="sim" role="group" aria-labelledby="sim-title">
      <h3 className="eyebrow" id="sim-title"><FlaskConical size={13} aria-hidden /> Demo / Simulation</h3>
      <p className="muted small">Sends synthetic camera events for table {label}. Not for live service.</p>
      <div className="sim-grid">
        {actions.map((a) => (
          <button key={a.label} type="button" className="btn btn-sim" onClick={a.run}>
            <a.icon size={14} aria-hidden /> {a.label}
          </button>
        ))}
      </div>
    </div>
  );
}
