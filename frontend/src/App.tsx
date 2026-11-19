import { useEffect, useMemo, useState } from "react";
import { Outlet } from "react-router-dom";
import { BottomNav, CommandSidebar } from "./components/CommandSidebar";
import { CommandHeader } from "./components/CommandHeader";
import { Skeleton } from "./components/ui";
import { opsCounts, systemStatus } from "./derive";
import { useLive } from "./live";
import { useNow } from "./time";

/** AppShell: sidebar + command header + routed workspace. */
export function App() {
  const { state } = useLive();
  const now = useNow(5000);
  const [collapsed, setCollapsed] = useState(() => readPref("sidebar") === "collapsed");
  useEffect(() => writePref("sidebar", collapsed ? "collapsed" : "open"), [collapsed]);

  const status = useMemo(
    () => systemStatus(Object.values(state.cameras), Object.values(state.integrations), state.connected, now),
    [state.cameras, state.integrations, state.connected, now],
  );
  const counts = useMemo(
    () => opsCounts(Object.values(state.tables), Object.values(state.tasks), Object.values(state.alerts), now),
    [state.tables, state.tasks, state.alerts, now],
  );

  return (
    <div className={`shell ${collapsed ? "is-collapsed" : ""}`}>
      <a className="skip-link" href="#workspace">Skip to content</a>
      <CommandSidebar collapsed={collapsed} onToggle={() => setCollapsed((c) => !c)} status={status}
        criticalCount={counts.critical} />
      <div className="shell-main">
        <CommandHeader status={status} counts={counts} />
        <main id="workspace" tabIndex={-1}>
          {state.loaded ? <Outlet /> : <LoadingWorkspace offline={!state.connected} />}
        </main>
      </div>
      <BottomNav criticalCount={counts.critical} />
    </div>
  );
}

function LoadingWorkspace({ offline }: { offline: boolean }) {
  return (
    <div className="loading-ws" aria-busy="true">
      <p className="muted">{offline ? "Connecting to the restaurant server…" : "Loading live state…"}</p>
      <div className="kpi-strip">{[0, 1, 2, 3].map((i) => <Skeleton key={i} h={92} r={12} />)}</div>
      <div className="loading-grid">
        <Skeleton h={360} r={12} />
        <Skeleton h={360} r={12} />
        <Skeleton h={360} r={12} />
      </div>
    </div>
  );
}

export function readPref(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function writePref(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* storage unavailable: preference just won't persist */
  }
}
