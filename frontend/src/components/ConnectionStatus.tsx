import { Camera, Receipt, RefreshCw } from "lucide-react";
import type { SystemStatus } from "../derive";
import { StatusDot } from "./ui";

/** Camera / POS / sync health. `compact` = dots + short labels for the header. */
export function ConnectionStatus({ status, compact = false }: { status: SystemStatus; compact?: boolean }) {
  const rows = [
    { key: "cameras", icon: Camera, name: "Cameras", ...status.cameras },
    { key: "pos", icon: Receipt, name: "POS feed", ...status.pos },
    { key: "sync", icon: RefreshCw, name: "Sync", ...status.sync },
  ];
  if (compact) {
    return (
      <ul className="conn-compact" aria-label="System status">
        {rows.map((r) => (
          <li key={r.key} className={`conn-chip h-${r.health}`} title={r.detail}>
            <StatusDot health={r.health} pulse={r.health === "bad"} />
            <span>{r.label}</span>
          </li>
        ))}
      </ul>
    );
  }
  return (
    <ul className="conn-list" aria-label="System status">
      {rows.map((r) => (
        <li key={r.key} title={r.detail}>
          <r.icon size={15} aria-hidden className="conn-icon" />
          <span className="conn-name">{r.name}</span>
          <span className={`conn-state h-${r.health}`}>
            <StatusDot health={r.health} />
            {r.label}
          </span>
        </li>
      ))}
    </ul>
  );
}
