import { Armchair, ClipboardList, Siren, Utensils } from "lucide-react";
import type { opsCounts } from "../derive";
import { LiveNumber } from "./ui";

type Counts = ReturnType<typeof opsCounts>;

export function OperationsKPI({ c, onCritical }: { c: Counts; onCritical?: () => void }) {
  const cards = [
    {
      key: "active", icon: Utensils, tone: "occupied", label: "Active tables",
      value: c.occupied, of: c.total,
      sub: c.occupied ? `${c.guests || "–"} guests seated` : "No parties seated",
    },
    {
      key: "free", icon: Armchair, tone: "available", label: "Available tables",
      value: c.available, of: c.total,
      sub: [c.cleaning && `${c.cleaning} need cleaning`, c.closed && `${c.closed} closed`].filter(Boolean).join(" · ") || "All set",
    },
    {
      key: "pending", icon: ClipboardList, tone: c.overdue ? "critical" : c.pending ? "cleaning" : "neutral",
      label: "Pending tasks", value: c.pending,
      sub: c.pending || c.overdue
        ? [`${c.toAssign} to assign`, `${c.toReview} to review`, c.overdue ? `${c.overdue} overdue` : ""].filter(Boolean).join(" · ")
        : "Nothing waiting on the counter",
    },
    {
      key: "critical", icon: Siren, tone: c.critical ? "critical" : "neutral", label: "Critical alerts",
      value: c.critical,
      sub: c.critical ? `${c.criticalUnacked} not acknowledged` : "No critical incidents",
    },
  ];

  return (
    <section className="kpi-strip" aria-label="Operations summary">
      {cards.map((k) => {
        const body = (
          <>
            <span className="kpi-icon" aria-hidden><k.icon size={18} /></span>
            <span className="kpi-label">{k.label}</span>
            <span className="kpi-value">
              <LiveNumber value={k.value} />
              {"of" in k && <span className="of">/{k.of}</span>}
            </span>
            <span className="kpi-sub">{k.sub}</span>
          </>
        );
        return k.key === "critical" && onCritical ? (
          <button key={k.key} type="button" className={`kpi-card tone-${k.tone} kpi-action`} onClick={onCritical}
            aria-label={`${k.label}: ${k.value}. ${k.sub}. Open alerts`}>
            {body}
          </button>
        ) : (
          <div key={k.key} className={`kpi-card tone-${k.tone}`}>{body}</div>
        );
      })}
    </section>
  );
}
