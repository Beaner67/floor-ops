export type Priority = "low" | "medium" | "high";
export type TableStatus = "vacant" | "occupied" | "needs_cleaning" | "out_of_service";
export type TaskStatus =
  | "pending"
  | "assigned"
  | "awaiting_verification"
  | "verified"
  | "verification_failed"
  | "verification_uncertain"
  | "done"
  | "cancelled";

export interface Table {
  id: number;
  label: string;
  capacity: number;
  camera_id: string | null;
  pos_x: number;
  pos_y: number;
  status: TableStatus;
  status_since: string;
  surface_items: number | null;
  surface_seen_at: string | null;
  seated_at: string | null;
  party_size: number | null;
  first_attended_at: string | null;
}

export interface Task {
  id: number;
  type: string;
  priority: Priority;
  status: TaskStatus;
  title: string;
  detail: string;
  source: string;
  table_id: number | null;
  table_label: string | null;
  order_id: number | null;
  staff_id: number | null;
  staff_name: string | null;
  created_at: string;
  due_at: string | null;
  assigned_at: string | null;
  completed_at: string | null;
  closed_at: string | null;
  verification_note: string;
  verified_by: string | null;
}

export interface Alert {
  id: number;
  key: string;
  kind: string;
  priority: Priority;
  title: string;
  message: string;
  table_id: number | null;
  task_id: number | null;
  created_at: string;
  acknowledged_at: string | null;
  resolved_at: string | null;
}

export interface Staff {
  id: number;
  name: string;
  role: string;
  on_shift: boolean;
}

export interface Order {
  id: number;
  pos_ref: string;
  table_id: number | null;
  table_label: string | null;
  items: string;
  status: string;
  sla_minutes: number;
  placed_at: string;
  ready_at: string | null;
  delivered_at: string | null;
}

export interface Camera {
  id: string;
  name: string;
  last_seen_at: string | null;
  online: boolean;
}

/** Push-based integration health, e.g. the POS order feed. */
export interface Integration {
  id: string;
  last_seen_at: string | null;
  online: boolean;
}

export interface StateSnapshot {
  tables: Table[];
  tasks: Task[];
  alerts: Alert[];
  staff: Staff[];
  orders: Order[];
  cameras: Camera[];
  integrations: Integration[];
  server_time: string;
}

export const OPEN_STATUSES: TaskStatus[] = [
  "pending",
  "assigned",
  "awaiting_verification",
  "verification_failed",
  "verification_uncertain",
];

export const PRIORITY_RANK: Record<Priority, number> = { high: 0, medium: 1, low: 2 };
