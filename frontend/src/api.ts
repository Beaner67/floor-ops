import type { StateSnapshot, Task } from "./types";

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* not json */
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.json() as Promise<T>;
}

export const api = {
  state: () => request<StateSnapshot>("GET", "/api/state"),
  analytics: (hours: number) => request<Analytics>("GET", `/api/analytics?hours=${hours}`),
  assign: (taskId: number, staffId: number) => request<Task>("POST", `/api/tasks/${taskId}/assign`, { staff_id: staffId }),
  complete: (taskId: number) => request<Task>("POST", `/api/tasks/${taskId}/complete`),
  review: (taskId: number, decision: "confirm" | "redo") =>
    request<Task>("POST", `/api/tasks/${taskId}/review`, { decision }),
  cancel: (taskId: number) => request<Task>("POST", `/api/tasks/${taskId}/cancel`),
  createTask: (body: { title: string; table_id?: number | null; priority: string; staff_id?: number | null }) =>
    request<Task>("POST", "/api/tasks", body),
  ackAlert: (id: number) => request("POST", `/api/alerts/${id}/ack`),
  setTable: (id: number, status: "vacant" | "out_of_service") => request("PATCH", `/api/tables/${id}`, { status }),
  setShift: (id: number, on_shift: boolean) => request("PATCH", `/api/staff/${id}`, { on_shift }),
  // Simulation controls: the same endpoint the cameras use. Events are attributed to the
  // table's own camera so they never register a phantom camera that later looks "offline".
  event: (type: string, table: string, cameraId: string | null, data: Record<string, unknown> = {}) =>
    request("POST", "/api/events", { type, table, camera_id: cameraId, data }),
};

export interface Analytics {
  window_hours: number;
  customers: {
    seatings: number;
    entries_counted: number;
    avg_wait_for_first_visit_s: number | null;
    avg_stay_s: number | null;
  };
  service: { assist_requests: number; avg_assist_response_s: number | null; unattended_alerts: number };
  cleaning: { tables_cleaned: number; avg_clean_duration_s: number | null };
  tasks: { created: number; open_now: number; overdue_now: number; verification: Record<string, number> };
  orders: { count: number; delayed: number; avg_prep_s: number | null; avg_ready_to_table_s: number | null };
  staff: {
    staff_id: number;
    name: string;
    assigned: number;
    completed: number;
    verified: number;
    needs_review: number;
    avg_completion_s: number | null;
  }[];
  hourly: { hour: number; avg_people: number; seatings: number }[];
  peak_hour: number | null;
}
