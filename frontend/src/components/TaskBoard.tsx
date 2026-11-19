import { useState, type ReactNode } from "react";
import { ChevronDown, CircleCheck, Inbox, ListTodo, ScanSearch, type LucideIcon } from "lucide-react";
import { isOpen, isOverdue, needsReview } from "../derive";
import { PRIORITY_RANK, type Staff, type Task } from "../types";
import { TaskCard } from "./TaskCard";
import { EmptyState, LiveNumber } from "./ui";

const byUrgency = (now: number) => (a: Task, b: Task) =>
  Number(isOverdue(b, now)) - Number(isOverdue(a, now)) ||
  PRIORITY_RANK[a.priority] - PRIORITY_RANK[b.priority] ||
  Date.parse(a.due_at ?? a.created_at) - Date.parse(b.due_at ?? b.created_at);

export function TaskBoard({ tasks, staff, now }: { tasks: Task[]; staff: Staff[]; now: number }) {
  const open = tasks.filter(isOpen);
  const sort = byUrgency(now);
  const toAssign = open.filter((t) => t.status === "pending").sort(sort);
  const inProgress = open.filter((t) => t.status === "assigned" || t.status === "awaiting_verification").sort(sort);
  const review = open.filter(needsReview).sort(sort);
  const done = tasks
    .filter((t) => !isOpen(t))
    .sort((a, b) => Date.parse(b.closed_at ?? "") - Date.parse(a.closed_at ?? ""))
    .slice(0, 10);

  return (
    <section className="board" aria-label="Task board">
      <TaskColumn title="To assign" icon={Inbox} tasks={toAssign} staff={staff} now={now}
        tone={toAssign.some((t) => isOverdue(t, now)) ? "critical" : toAssign.length ? "cleaning" : "neutral"}
        empty={<EmptyState icon={Inbox} title="All tasks assigned">New tasks from cameras, the POS and the counter land here.</EmptyState>} />
      <TaskColumn title="In progress" icon={ListTodo} tasks={inProgress} staff={staff} now={now} tone="occupied"
        empty={<EmptyState icon={ListTodo} title="No one is on a task">Assigned work and camera checks appear here.</EmptyState>} />
      <TaskColumn title="Needs review" icon={ScanSearch} tasks={review} staff={staff} now={now}
        tone={review.length ? "critical" : "neutral"}
        empty={<EmptyState icon={ScanSearch} title="Nothing to review">Tasks the camera can’t confirm come here for a person to decide.</EmptyState>}
        footer={<CompletedList tasks={done} staff={staff} now={now} />} />
    </section>
  );
}

function TaskColumn({ title, icon: Icon, tasks, staff, now, tone, empty, footer }: {
  title: string; icon: LucideIcon; tasks: Task[]; staff: Staff[]; now: number; tone: string; empty: ReactNode; footer?: ReactNode;
}) {
  return (
    <div className={`column tone-${tone}`}>
      <header className="column-head">
        <span className="column-dot" aria-hidden />
        <Icon size={15} aria-hidden className="muted" />
        <h2>{title}</h2>
        <span className="count"><LiveNumber value={tasks.length} /></span>
      </header>
      <div className="column-body">
        {tasks.length === 0 ? empty : tasks.map((t) => <TaskCard key={t.id} task={t} staff={staff} now={now} />)}
        {footer}
      </div>
    </div>
  );
}

function CompletedList({ tasks, staff, now }: { tasks: Task[]; staff: Staff[]; now: number }) {
  const [open, setOpen] = useState(false);
  if (!tasks.length) return null;
  return (
    <div className="completed">
      <button type="button" className="completed-toggle" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <CircleCheck size={14} aria-hidden /> Recently closed <span className="count">{tasks.length}</span>
        <ChevronDown size={14} aria-hidden className={`chev ${open ? "up" : ""}`} />
      </button>
      {open && tasks.map((t) => <TaskCard key={t.id} task={t} staff={staff} now={now} compact />)}
    </div>
  );
}
