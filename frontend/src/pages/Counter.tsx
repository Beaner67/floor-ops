import { useCallback, useEffect, useMemo, useState } from "react";
import { Bell, ClipboardList, Map as MapIcon } from "lucide-react";
import { readPref, writePref } from "../App";
import { AlertsCentre } from "../components/AlertsCentre";
import { LiveFloorMap } from "../components/LiveFloorMap";
import { OperationsKPI } from "../components/OperationsKPI";
import { QuickTask } from "../components/QuickTask";
import { TableInspector } from "../components/TableInspector";
import { TaskBoard } from "../components/TaskBoard";
import { isOpen, opsCounts, tablesNeedingAttention } from "../derive";
import { useLive } from "../live";
import { useNow } from "../time";

function beep() {
  try {
    const ctx = new AudioContext();
    const o = ctx.createOscillator();
    const g = ctx.createGain();
    o.frequency.value = 880;
    g.gain.setValueAtTime(0.15, ctx.currentTime);
    g.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.4);
    o.connect(g).connect(ctx.destination);
    o.start();
    o.stop(ctx.currentTime + 0.4);
  } catch {
    /* audio blocked until first interaction */
  }
}

type Tab = "floor" | "tasks" | "alerts";

/** Live Command Centre: KPIs, floor, task board, alerts. */
export function Counter() {
  const { state, subscribe } = useLive();
  const now = useNow(1000);
  const [selected, setSelected] = useState<number | null>(null);
  const [demo, setDemo] = useState(() => readPref("demo") === "1");
  const [sound, setSound] = useState(() => readPref("sound") !== "0");
  const [tab, setTab] = useState<Tab>("floor");
  const [drawer, setDrawer] = useState(false);

  useEffect(() => writePref("demo", demo ? "1" : "0"), [demo]);
  useEffect(() => writePref("sound", sound ? "1" : "0"), [sound]);

  useEffect(
    () =>
      subscribe((m) => {
        if (sound && m.type === "alert" && m.data.priority === "high" && !m.data.resolved_at && !m.data.acknowledged_at) beep();
      }),
    [subscribe, sound],
  );

  useEffect(() => {
    if (!drawer) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setDrawer(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drawer]);

  const tables = useMemo(() => Object.values(state.tables).sort((a, b) => a.id - b.id), [state.tables]);
  const staff = useMemo(() => Object.values(state.staff), [state.staff]);
  const tasks = useMemo(() => Object.values(state.tasks), [state.tasks]);
  const alerts = useMemo(() => Object.values(state.alerts).filter((a) => !a.resolved_at), [state.alerts]);
  const counts = opsCounts(tables, tasks, alerts, now);
  const attention = useMemo(() => tablesNeedingAttention(tasks, alerts), [tasks, alerts]);
  const taskCount = useMemo(() => {
    const m = new Map<number, number>();
    tasks.forEach((t) => isOpen(t) && t.table_id != null && m.set(t.table_id, (m.get(t.table_id) ?? 0) + 1));
    return m;
  }, [tasks]);
  const tableLabel = useCallback((id: number) => state.tables[id]?.label, [state.tables]);
  const selectedTable = selected != null ? state.tables[selected] : null;

  const openAlerts = () => {
    setTab("alerts");
    setDrawer(true);
  };

  return (
    <div className="ops">
      <OperationsKPI c={counts} onCritical={openAlerts} />

      <div className="ops-tabs" role="tablist" aria-label="Workspace">
        {([
          ["floor", "Floor", MapIcon, 0],
          ["tasks", "Tasks", ClipboardList, counts.pending],
          ["alerts", "Alerts", Bell, alerts.length],
        ] as const).map(([id, label, Icon, n]) => (
          <button key={id} role="tab" type="button" aria-selected={tab === id} className={tab === id ? "on" : ""}
            onClick={() => setTab(id)}>
            <Icon size={16} aria-hidden /> {label}
            {n > 0 && <span className={`count ${id === "alerts" && counts.critical ? "count-bad" : ""}`}>{n}</span>}
          </button>
        ))}
      </div>

      <div className="ops-grid" data-tab={tab}>
        <div className="zone zone-floor">
          <LiveFloorMap tables={tables} taskCount={taskCount} attention={attention} selected={selected}
            onSelect={setSelected} now={now} demo={demo} onDemo={setDemo} />
          {selectedTable ? (
            <TableInspector table={selectedTable} now={now} demo={demo} onClose={() => setSelected(null)}
              tasks={tasks.filter((t) => t.table_id === selectedTable.id && isOpen(t))} />
          ) : (
            <QuickTask tables={tables} staff={staff} />
          )}
        </div>

        <div className="zone zone-board">
          <div className="board-toolbar">
            <button type="button" className={`btn alerts-trigger ${counts.critical ? "has-critical" : ""}`} onClick={openAlerts}>
              <Bell size={15} aria-hidden /> Alerts
              <span className={`count ${counts.critical ? "count-bad" : ""}`}>{alerts.length}</span>
            </button>
          </div>
          <TaskBoard tasks={tasks} staff={staff} now={now} />
        </div>

        <div className={`zone zone-alerts ${drawer ? "is-open" : ""}`}>
          <AlertsCentre alerts={alerts} tableLabel={tableLabel} now={now} sound={sound} onSound={setSound}
            onClose={() => setDrawer(false)} />
        </div>
        {drawer && <div className="drawer-backdrop" onClick={() => setDrawer(false)} aria-hidden />}
      </div>
    </div>
  );
}
