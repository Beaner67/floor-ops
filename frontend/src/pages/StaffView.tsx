import { ArrowLeft, ClipboardCheck } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { TaskCard } from "../components/TaskCard";
import { EmptyState, Switch, initials } from "../components/ui";
import { isOpen } from "../derive";
import { useLive } from "../live";
import { useNow } from "../time";

/** Optional per-employee screen (phone): my assignments, mark done, shift toggle. */
export function StaffView() {
  const { id } = useParams();
  const nav = useNavigate();
  const { state } = useLive();
  const now = useNow(1000);
  const staff = Object.values(state.staff);
  const me = id ? state.staff[id] : undefined;

  if (!me) {
    return (
      <div className="page narrow">
        <div className="page-head">
          <h2>Who’s using this device?</h2>
          <p className="card-sub">Pick your name to see the tasks assigned to you.</p>
        </div>
        <div className="pick-grid">
          {staff.map((s) => {
            const n = Object.values(state.tasks).filter((t) => t.staff_id === s.id && isOpen(t)).length;
            return (
              <button key={s.id} type="button" className="pick" onClick={() => nav(`/staff/${s.id}`)}>
                <span className="avatar avatar-lg">{initials(s.name)}</span>
                <span className="pick-text">
                  <strong>{s.name}</strong>
                  <span className="muted">{s.role} · {s.on_shift ? `${n} open task${n === 1 ? "" : "s"}` : "off shift"}</span>
                </span>
              </button>
            );
          })}
        </div>
      </div>
    );
  }

  const mine = Object.values(state.tasks)
    .filter((t) => t.staff_id === me.id && isOpen(t))
    .sort((a, b) => Date.parse(a.created_at) - Date.parse(b.created_at));

  return (
    <div className="page narrow">
      <Link to="/staff" className="back-link"><ArrowLeft size={14} aria-hidden /> All staff</Link>
      <div className="page-head row">
        <span className="assignee">
          <span className="avatar avatar-lg">{initials(me.name)}</span>
          <span><h2>{me.name}</h2><span className="card-sub">{me.role}</span></span>
        </span>
        <Switch checked={me.on_shift} onChange={(v) => api.setShift(me.id, v)} label="On shift" />
      </div>
      {mine.length === 0 ? (
        <div className="card"><EmptyState icon={ClipboardCheck} title="No tasks assigned to you">New assignments from the counter appear here instantly.</EmptyState></div>
      ) : (
        <div className="stack">{mine.map((t) => <TaskCard key={t.id} task={t} staff={staff} now={now} />)}</div>
      )}
    </div>
  );
}
