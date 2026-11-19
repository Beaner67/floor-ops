import { useCallback, useEffect, useMemo, useState } from "react";
import { BellRing, Clock, Siren, Utensils } from "lucide-react";
import { AlertsCentre } from "../components/AlertsCentre";
import { LiveNumber, initials } from "../components/ui";
import { isOpen, isOverdue } from "../derive";
import { useLive } from "../live";
import { dur, useNow } from "../time";

/** Phone-first view for the manager: what needs attention, right now. */
export function Manager() {
  const { state, subscribe } = useLive();
  const now = useNow(1000);
  const [perm, setPerm] = useState(() => ("Notification" in window ? Notification.permission : "unsupported"));

  useEffect(
    () =>
      subscribe((m) => {
        if (perm !== "granted" || m.type !== "alert" || m.data.resolved_at || m.data.acknowledged_at) return;
        if (m.data.priority === "low") return;
        new Notification(m.data.title, { body: m.data.message, tag: `alert-${m.data.id}` });
      }),
    [subscribe, perm],
  );

  const tables = Object.values(state.tables);
  const open = useMemo(() => Object.values(state.tasks).filter(isOpen), [state.tasks]);
  const overdue = open.filter((t) => isOverdue(t, now));
  const alerts = Object.values(state.alerts).filter((a) => !a.resolved_at);
  const high = alerts.filter((a) => a.priority === "high");
  const seated = tables.filter((t) => t.status === "occupied");
  const longestWait = Math.max(
    0,
    ...seated.filter((t) => !t.first_attended_at && t.seated_at).map((t) => (now - Date.parse(t.seated_at!)) / 1000),
  );
  const tableLabel = useCallback((id: number) => state.tables[id]?.label, [state.tables]);

  return (
    <div className="page manager">
      <div className="kpi-strip kpi-2">
        <Kpi icon={Siren} label="Critical alerts" value={high.length} tone={high.length ? "critical" : "available"} />
        <Kpi icon={Clock} label="Overdue tasks" value={overdue.length} tone={overdue.length ? "cleaning" : "available"} />
        <Kpi icon={Utensils} label="Tables seated" value={seated.length} of={tables.length} tone="occupied" />
        <Kpi icon={BellRing} label="Longest unvisited" value={longestWait ? dur(longestWait) : "–"}
          tone={longestWait > 120 ? "cleaning" : "neutral"} />
      </div>

      {perm === "default" && (
        <button type="button" className="btn btn-primary btn-block" onClick={async () => setPerm(await Notification.requestPermission())}>
          <BellRing size={16} aria-hidden /> Turn on phone notifications
        </button>
      )}
      {perm === "denied" && <p className="notice">Notifications are blocked in this browser’s settings.</p>}

      <AlertsCentre alerts={alerts} tableLabel={tableLabel} now={now} />

      <section className="card" aria-labelledby="by-staff">
        <div className="card-head"><h2 id="by-staff">Open tasks by staff</h2></div>
        <ul className="by-staff">
          {Object.values(state.staff).filter((s) => s.on_shift).map((s) => {
            const mine = open.filter((t) => t.staff_id === s.id);
            return (
              <li key={s.id}>
                <span className="assignee"><span className="avatar">{initials(s.name)}</span>{s.name}</span>
                <span className="muted">{mine.length ? mine.map((t) => t.title).join(" · ") : "Free"}</span>
              </li>
            );
          })}
          <li>
            <span className="assignee"><span className="avatar avatar-empty">–</span>Unassigned</span>
            <span className="muted">{open.filter((t) => !t.staff_id).length} task(s)</span>
          </li>
        </ul>
      </section>
    </div>
  );
}

function Kpi({ icon: Icon, label, value, of, tone }: {
  icon: typeof Siren; label: string; value: string | number; of?: number; tone: string;
}) {
  return (
    <div className={`kpi-card tone-${tone}`}>
      <span className="kpi-icon" aria-hidden><Icon size={18} /></span>
      <span className="kpi-label">{label}</span>
      <span className="kpi-value"><LiveNumber value={value} />{of != null && <span className="of">/{of}</span>}</span>
    </div>
  );
}
