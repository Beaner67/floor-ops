/** Pure selectors over live state. Every number on screen comes from here, never hardcoded. */
import type { Alert, Camera, Integration, Table, Task } from "./types";
import { OPEN_STATUSES } from "./types";
import { dur, since } from "./time";

export type Health = "ok" | "warn" | "bad" | "idle";

export interface SystemStatus {
  cameras: { health: Health; label: string; detail: string };
  pos: { health: Health; label: string; detail: string };
  sync: { health: Health; label: string; detail: string };
}

export function systemStatus(cameras: Camera[], integrations: Integration[], connected: boolean, now: number): SystemStatus {
  const offline = cameras.filter((c) => !c.online);
  const cam: SystemStatus["cameras"] =
    cameras.length === 0
      ? { health: "idle", label: "No cameras", detail: "No camera has connected yet" }
      : offline.length === cameras.length
        ? { health: "bad", label: "Cameras offline", detail: offline.map((c) => c.name).join(", ") }
        : offline.length
          ? { health: "bad", label: `${offline.length}/${cameras.length} offline`, detail: offline.map((c) => c.name).join(", ") }
          : { health: "ok", label: `${cameras.length} cameras`, detail: "All camera feeds live" };

  const p = integrations.find((i) => i.id === "pos");
  const pos: SystemStatus["pos"] = !p?.last_seen_at
    ? { health: "idle", label: "POS not connected", detail: "No order data received yet" }
    : p.online
      ? { health: "ok", label: "POS live", detail: `Last order update ${dur(since(p.last_seen_at, now))} ago` }
      : { health: "warn", label: "POS idle", detail: `No order data for ${dur(since(p.last_seen_at, now))}` };

  const sync: SystemStatus["sync"] = connected
    ? { health: "ok", label: "Synced", detail: "Live connection to the restaurant server" }
    : { health: "bad", label: "Reconnecting", detail: "Live updates paused; retrying" };

  return { cameras: cam, pos, sync };
}

export const isOpen = (t: Task) => OPEN_STATUSES.includes(t.status);
export const needsReview = (t: Task) => t.status === "verification_failed" || t.status === "verification_uncertain";
export const isOverdue = (t: Task, now: number) =>
  !!t.due_at && Date.parse(t.due_at) < now && (t.status === "pending" || t.status === "assigned");

export function opsCounts(tables: Table[], tasks: Task[], alerts: Alert[], now: number) {
  const open = tasks.filter(isOpen);
  const unresolved = alerts.filter((a) => !a.resolved_at);
  const critical = unresolved.filter((a) => a.priority === "high");
  const occupied = tables.filter((t) => t.status === "occupied");
  return {
    occupied: occupied.length,
    guests: occupied.reduce((n, t) => n + (t.party_size ?? 0), 0),
    available: tables.filter((t) => t.status === "vacant").length,
    cleaning: tables.filter((t) => t.status === "needs_cleaning").length,
    closed: tables.filter((t) => t.status === "out_of_service").length,
    total: tables.length,
    toAssign: open.filter((t) => t.status === "pending").length,
    toReview: open.filter(needsReview).length,
    overdue: open.filter((t) => isOverdue(t, now)).length,
    pending: open.filter((t) => t.status === "pending" || needsReview(t)).length,
    critical: critical.length,
    criticalUnacked: critical.filter((a) => !a.acknowledged_at).length,
  };
}

/** Table needs staff attention: an urgent open task or an unresolved critical alert. */
export function tablesNeedingAttention(tasks: Task[], alerts: Alert[]): Set<number> {
  const ids = new Set<number>();
  tasks.forEach((t) => isOpen(t) && t.priority === "high" && t.table_id != null && ids.add(t.table_id));
  alerts.forEach((a) => !a.resolved_at && a.priority === "high" && a.table_id != null && ids.add(a.table_id));
  return ids;
}

export const TASK_TYPE_LABEL: Record<string, string> = {
  clean_table: "Table cleaning",
  assist_customer: "Customer assistance",
  attend_table: "Waiting customers",
  deliver_order: "Food delivery",
  check_order: "Kitchen check",
  general: "Staff task",
};

export const PRIORITY_LABEL = { high: "Critical", medium: "Warning", low: "Normal" } as const;
export const SEVERITY_LABEL = { high: "Critical", medium: "Warning", low: "Info" } as const;

export const TABLE_STATUS_LABEL: Record<Table["status"], string> = {
  vacant: "Available",
  occupied: "Occupied",
  needs_cleaning: "Needs cleaning",
  out_of_service: "Closed",
};

export function alertSource(a: Alert, tableLabel: (id: number) => string | undefined): string {
  const table = a.table_id != null ? `Table ${tableLabel(a.table_id) ?? a.table_id}` : null;
  if (a.kind === "camera_offline") return "Camera system";
  if (a.kind === "order_delayed" || a.kind === "delivery_overdue") return table ? `Kitchen · ${table}` : "Kitchen";
  return table ?? "Restaurant";
}

export function sortAlerts(alerts: Alert[]): Alert[] {
  const rank = { high: 0, medium: 1, low: 2 };
  return [...alerts].sort(
    (a, b) =>
      rank[a.priority] - rank[b.priority] ||
      Number(!!a.acknowledged_at) - Number(!!b.acknowledged_at) ||
      Date.parse(b.created_at) - Date.parse(a.created_at),
  );
}
