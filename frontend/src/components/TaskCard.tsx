import { memo, useState } from "react";
import {
  Check, ChefHat, CircleCheck, ClipboardList, ConciergeBell, Hand, RotateCcw, ScanEye, SprayCan, Timer, UserRound, Users, X,
  type LucideIcon,
} from "lucide-react";
import { api } from "../api";
import { PRIORITY_LABEL, TASK_TYPE_LABEL } from "../derive";
import { clock, dur, since } from "../time";
import type { Staff, Task } from "../types";
import { ConfirmButton, initials } from "./ui";

const TYPE_ICON: Record<string, LucideIcon> = {
  clean_table: SprayCan,
  assist_customer: Hand,
  attend_table: Users,
  deliver_order: ConciergeBell,
  check_order: ChefHat,
  general: ClipboardList,
};

const VERIFIED_BY: Record<string, string> = { ai: "Camera verified", manual: "Confirmed manually", pos: "POS confirmed" };

export const TaskCard = memo(function TaskCard({ task, staff, now, compact = false }: {
  task: Task; staff: Staff[]; now: number; compact?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const Icon = TYPE_ICON[task.type] ?? ClipboardList;
  const dueIn = task.due_at ? (Date.parse(task.due_at) - now) / 1000 : null;
  const actionable = task.status === "pending" || task.status === "assigned";
  const overdue = actionable && dueIn != null && dueIn < 0;
  const closed = ["verified", "done", "cancelled"].includes(task.status);
  const review = task.status === "verification_failed" || task.status === "verification_uncertain";
  const tone = closed ? (task.status === "cancelled" ? "muted" : "done") : task.priority;

  return (
    <article className={`task tone-${tone} ${overdue ? "is-overdue" : ""} ${compact ? "is-compact" : ""}`}
      aria-label={`${task.title}${overdue ? ", overdue" : ""}`}>
      <header className="task-head">
        <span className="task-type"><Icon size={14} aria-hidden /> {TASK_TYPE_LABEL[task.type] ?? task.type}</span>
        {task.table_label && <span className="table-chip">T{task.table_label}</span>}
        {!closed && <span className={`prio prio-${task.priority}`}>{PRIORITY_LABEL[task.priority]}</span>}
      </header>

      <h3 className="task-title">{task.title}</h3>
      {task.detail && !closed && !compact && <p className="task-detail">{task.detail}</p>}

      {!closed && (
        <div className="task-time">
          {overdue ? (
            <span className="overdue-pill"><Timer size={12} aria-hidden /> Overdue · {dur(-dueIn!)}</span>
          ) : dueIn != null && actionable ? (
            <span className={`due ${dueIn < 30 ? "due-soon" : ""}`}><Timer size={12} aria-hidden /> Due in {dur(dueIn)}</span>
          ) : null}
          <span className="muted">Created {dur(since(task.created_at, now))} ago</span>
        </div>
      )}

      {task.status === "pending" && (
        <div className="task-actions">
          <label className="select-wrap">
            <span className="sr-only">Assign to</span>
            <select disabled={busy} value=""
              onChange={(e) => e.target.value && run(() => api.assign(task.id, Number(e.target.value)))}>
              <option value="">Assign to…</option>
              {staff.filter((s) => s.on_shift).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </label>
          <ConfirmButton icon={X} className="btn-ghost" disabled={busy} confirmLabel="Dismiss?"
            onConfirm={() => run(() => api.cancel(task.id))}>
            Dismiss
          </ConfirmButton>
        </div>
      )}

      {task.status === "assigned" && (
        <div className="task-actions">
          <span className="assignee">
            <span className="avatar" aria-hidden>{initials(task.staff_name)}</span>
            <span className="assignee-name">{task.staff_name}</span>
          </span>
          <button type="button" className="btn btn-primary" disabled={busy} onClick={() => run(() => api.complete(task.id))}>
            <Check size={15} aria-hidden /> Complete
          </button>
        </div>
      )}

      {task.status === "awaiting_verification" && (
        <div className="verifying" role="status">
          <ScanEye size={15} aria-hidden />
          <span>Verifying with camera…</span>
          <span className="assignee"><span className="avatar">{initials(task.staff_name)}</span></span>
        </div>
      )}

      {review && (
        <>
          <p className={`verdict ${task.status === "verification_failed" ? "v-bad" : "v-unsure"}`}>
            <strong>{task.status === "verification_failed" ? "Verification failed" : "Manual check needed"}</strong>
            {task.verification_note}
          </p>
          <div className="task-actions">
            <button type="button" className="btn" disabled={busy} onClick={() => run(() => api.review(task.id, "redo"))}>
              <RotateCcw size={15} aria-hidden /> Send back
            </button>
            <button type="button" className="btn btn-primary" disabled={busy} onClick={() => run(() => api.review(task.id, "confirm"))}>
              <CircleCheck size={15} aria-hidden /> Verify done
            </button>
          </div>
        </>
      )}

      {closed && (
        <p className="task-closed">
          {task.status === "cancelled" ? <X size={13} aria-hidden /> : <CircleCheck size={13} aria-hidden />}
          <span>
            {task.status === "cancelled" ? "Dismissed" : VERIFIED_BY[task.verified_by ?? ""] ?? "Done"}
            {" · "}{clock(task.closed_at)}
            {task.staff_name && <> · <UserRound size={11} aria-hidden /> {task.staff_name}</>}
          </span>
        </p>
      )}
      {error && <p className="err" role="alert">{error}</p>}
    </article>
  );
});
