import { useLocation } from "react-router-dom";
import type { SystemStatus } from "../derive";
import { useNow } from "../time";
import { ConnectionStatus } from "./ConnectionStatus";
import { LiveNumber } from "./ui";

const TITLES: Record<string, string> = {
  "/": "Live Command Centre",
  "/manager": "Manager",
  "/analytics": "Reports",
  "/staff": "Staff",
};

export function CommandHeader({ status, counts }: {
  status: SystemStatus;
  counts: { occupied: number; total: number; pending: number; critical: number };
}) {
  const now = useNow(1000);
  const { pathname } = useLocation();
  const title = TITLES["/" + (pathname.split("/")[1] ?? "")] ?? "Live Command Centre";
  const d = new Date(now);

  return (
    <header className="cmd-header">
      <div className="cmd-title">
        <span className="crumb">Floor Ops</span>
        <span className="crumb-sep" aria-hidden>/</span>
        <h1>{title}</h1>
      </div>

      <dl className="cmd-metrics" aria-label="Live summary">
        <div>
          <dt>Active tables</dt>
          <dd><LiveNumber value={counts.occupied} /><span className="of">/{counts.total}</span></dd>
        </div>
        <div className={counts.pending ? "m-warn" : ""}>
          <dt>Pending tasks</dt>
          <dd><LiveNumber value={counts.pending} /></dd>
        </div>
        <div className={counts.critical ? "m-bad" : ""}>
          <dt>Critical alerts</dt>
          <dd><LiveNumber value={counts.critical} /></dd>
        </div>
      </dl>

      <ConnectionStatus status={status} compact />

      <time className="cmd-clock" dateTime={d.toISOString()}>
        <span className="tabular">{d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
        <small>{d.toLocaleDateString([], { weekday: "short", day: "numeric", month: "short" })}</small>
      </time>
    </header>
  );
}
