import { memo } from "react";
import { BellOff, Check, Info, OctagonAlert, ShieldCheck, TriangleAlert, Volume2, VolumeX, X } from "lucide-react";
import { api } from "../api";
import { SEVERITY_LABEL, alertSource, sortAlerts } from "../derive";
import { dur, since } from "../time";
import type { Alert } from "../types";
import { EmptyState, LiveNumber } from "./ui";

const SEVERITY_ICON = { high: OctagonAlert, medium: TriangleAlert, low: Info } as const;
const GROUPS = [
  { p: "high", title: "Critical" },
  { p: "medium", title: "Warnings" },
  { p: "low", title: "Information" },
] as const;

export function AlertsCentre({ alerts, tableLabel, now, sound, onSound, onClose, className = "" }: {
  alerts: Alert[];
  tableLabel: (id: number) => string | undefined;
  now: number;
  sound?: boolean;
  onSound?: (v: boolean) => void;
  onClose?: () => void;
  className?: string;
}) {
  const sorted = sortAlerts(alerts);
  const unacked = alerts.filter((a) => !a.acknowledged_at).length;

  return (
    <section className={`card alerts-centre ${className}`} aria-labelledby="alerts-title">
      <div className="card-head">
        <div>
          <h2 id="alerts-title">Live alerts <span className="count"><LiveNumber value={alerts.length} /></span></h2>
          <p className="card-sub">{unacked ? `${unacked} not acknowledged` : "All acknowledged"}</p>
        </div>
        <div className="head-actions">
          {onSound && (
            <button type="button" className="icon-btn" aria-pressed={sound} onClick={() => onSound(!sound)}
              aria-label={sound ? "Mute critical alert sound" : "Play sound for critical alerts"}
              title={sound ? "Sound on for critical alerts" : "Sound off"}>
              {sound ? <Volume2 size={16} /> : <VolumeX size={16} />}
            </button>
          )}
          {onClose && (
            <button type="button" className="icon-btn drawer-close" onClick={onClose} aria-label="Close alerts">
              <X size={16} />
            </button>
          )}
        </div>
      </div>

      <div className="alerts-body" aria-live="polite">
        {sorted.length === 0 ? (
          <EmptyState icon={ShieldCheck} title="No open alerts">Cameras, kitchen and service are within targets.</EmptyState>
        ) : (
          GROUPS.map((g) => {
            const list = sorted.filter((a) => a.priority === g.p);
            if (!list.length) return null;
            return (
              <div key={g.p} className="alert-group">
                <h3 className={`eyebrow sev-${g.p}`}>{g.title} <span className="count">{list.length}</span></h3>
                <ul>
                  {list.map((a) => <AlertCard key={a.id} alert={a} source={alertSource(a, tableLabel)} now={now} />)}
                </ul>
              </div>
            );
          })
        )}
      </div>
    </section>
  );
}

export const AlertCard = memo(function AlertCard({ alert: a, source, now }: { alert: Alert; source: string; now: number }) {
  const Icon = SEVERITY_ICON[a.priority];
  return (
    <li className={`alert sev-${a.priority} ${a.acknowledged_at ? "is-acked" : "is-new"}`}>
      <div className="alert-head">
        <span className={`sev-tag sev-${a.priority}`}><Icon size={13} aria-hidden /> {SEVERITY_LABEL[a.priority]}</span>
        <span className="alert-source">{source}</span>
        <time className="muted tabular" dateTime={a.created_at}>{dur(since(a.created_at, now))} ago</time>
      </div>
      <strong className="alert-title">{a.title}</strong>
      <p className="alert-msg">{a.message}</p>
      {a.acknowledged_at ? (
        <span className="acked"><Check size={13} aria-hidden /> Acknowledged · still open until resolved</span>
      ) : (
        <button type="button" className="btn btn-sm" onClick={() => api.ackAlert(a.id)}>
          <BellOff size={14} aria-hidden /> Acknowledge
        </button>
      )}
    </li>
  );
});
