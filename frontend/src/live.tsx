import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api } from "./api";
import type { Alert, Camera, Integration, Order, Staff, StateSnapshot, Table, Task } from "./types";

type ById<T> = Record<string, T>;

interface LiveState {
  tables: ById<Table>;
  tasks: ById<Task>;
  alerts: ById<Alert>;
  staff: ById<Staff>;
  orders: ById<Order>;
  cameras: ById<Camera>;
  integrations: ById<Integration>;
  connected: boolean;
  loaded: boolean;
}

const empty: LiveState = {
  tables: {}, tasks: {}, alerts: {}, staff: {}, orders: {}, cameras: {}, integrations: {}, connected: false, loaded: false,
};

const byId = <T extends { id: number | string }>(rows: T[]): ById<T> =>
  Object.fromEntries(rows.map((r) => [String(r.id), r]));

const COLLECTION = {
  table: "tables", task: "tasks", alert: "alerts", staff: "staff", order: "orders", camera: "cameras",
  integration: "integrations",
} as const;

type Listener = (msg: { type: string; data: any }) => void;

const LiveCtx = createContext<{ state: LiveState; subscribe: (fn: Listener) => () => void } | null>(null);

export function LiveProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<LiveState>(empty);
  const listeners = useRef(new Set<Listener>());

  const load = useCallback(async () => {
    try {
      const s: StateSnapshot = await api.state();
      setState((prev) => ({
        ...prev,
        loaded: true,
        tables: byId(s.tables),
        tasks: byId(s.tasks),
        alerts: byId(s.alerts),
        staff: byId(s.staff),
        orders: byId(s.orders),
        cameras: byId(s.cameras),
        integrations: byId(s.integrations ?? []),
      }));
    } catch {
      /* backend down; the socket loop keeps retrying */
    }
  }, []);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let closed = false;
    let retry = 500;
    let ping: ReturnType<typeof setInterval>;

    const connect = () => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${location.host}/ws`);
      ws.onopen = () => {
        retry = 500;
        setState((p) => ({ ...p, connected: true }));
        load(); // resync anything missed while disconnected
        ping = setInterval(() => ws?.readyState === 1 && ws.send("ping"), 20000);
      };
      ws.onmessage = (e) => {
        const msg = JSON.parse(e.data) as { type: keyof typeof COLLECTION; data: any };
        const key = COLLECTION[msg.type];
        if (key) {
          setState((p) => ({ ...p, [key]: { ...p[key], [String(msg.data.id)]: msg.data } }));
        }
        listeners.current.forEach((fn) => fn(msg));
      };
      ws.onclose = () => {
        clearInterval(ping);
        setState((p) => ({ ...p, connected: false }));
        if (!closed) setTimeout(connect, (retry = Math.min(retry * 2, 8000)));
      };
    };
    connect();
    return () => {
      closed = true;
      clearInterval(ping);
      ws?.close();
    };
  }, [load]);

  const subscribe = useCallback((fn: Listener) => {
    listeners.current.add(fn);
    return () => void listeners.current.delete(fn);
  }, []);

  const value = useMemo(() => ({ state, subscribe }), [state, subscribe]);
  return <LiveCtx.Provider value={value}>{children}</LiveCtx.Provider>;
}

export function useLive() {
  const ctx = useContext(LiveCtx);
  if (!ctx) throw new Error("useLive outside LiveProvider");
  return ctx;
}
