import { memo, useEffect, useRef, useState } from "react";
import { Armchair, Ban, BellRing, Check, FlaskConical, SprayCan, Users } from "lucide-react";
import { TABLE_STATUS_LABEL } from "../derive";
import { dur, since } from "../time";
import type { Table } from "../types";
import { Switch } from "./ui";

const STATUS_ICON = { vacant: Check, occupied: Users, needs_cleaning: SprayCan, out_of_service: Ban } as const;

interface Props {
  tables: Table[];
  taskCount: Map<number, number>;
  attention: Set<number>;
  selected: number | null;
  onSelect: (id: number | null) => void;
  now: number;
  demo: boolean;
  onDemo: (v: boolean) => void;
}

export function LiveFloorMap({ tables, taskCount, attention, selected, onSelect, now, demo, onDemo }: Props) {
  return (
    <section className="card floor" aria-labelledby="floor-title">
      <div className="card-head">
        <div>
          <h2 id="floor-title">Live floor</h2>
          <p className="card-sub">Tap a table for details</p>
        </div>
        <Switch checked={demo} onChange={onDemo} label="Simulation" icon={FlaskConical} />
      </div>

      <div className="floor-plan" onClick={() => onSelect(null)}>
        <span className="floor-entrance">Entrance</span>
        {tables.map((t) => (
          <FloorTableTile
            key={t.id}
            table={t}
            tasks={taskCount.get(t.id) ?? 0}
            attention={attention.has(t.id)}
            selected={selected === t.id}
            onSelect={onSelect}
            now={now}
          />
        ))}
      </div>

      <ul className="floor-legend" aria-label="Legend">
        {(["vacant", "occupied", "needs_cleaning", "out_of_service"] as const).map((s) => {
          const Icon = STATUS_ICON[s];
          return (
            <li key={s} className={`lg-${s}`}>
              <Icon size={12} aria-hidden /> {TABLE_STATUS_LABEL[s]}
            </li>
          );
        })}
        <li className="lg-attention"><BellRing size={12} aria-hidden /> Needs attention</li>
      </ul>
    </section>
  );
}

const FloorTableTile = memo(function FloorTableTile({ table: t, tasks, attention, selected, onSelect, now }: {
  table: Table; tasks: number; attention: boolean; selected: boolean; onSelect: (id: number | null) => void; now: number;
}) {
  // Brief highlight when the camera changes this table's state.
  const prev = useRef(t.status);
  const [changed, setChanged] = useState(false);
  useEffect(() => {
    if (prev.current === t.status) return;
    prev.current = t.status;
    setChanged(true);
    const id = setTimeout(() => setChanged(false), 900);
    return () => clearTimeout(id);
  }, [t.status]);

  const Icon = STATUS_ICON[t.status];
  const timed = t.status === "occupied" || t.status === "needs_cleaning";
  const unvisited = t.status === "occupied" && !t.first_attended_at;
  const desc = [
    `Table ${t.label}`, TABLE_STATUS_LABEL[t.status],
    t.status === "occupied" ? `${t.party_size || "?"} of ${t.capacity} seated for ${dur(since(t.status_since, now))}` : `${t.capacity} seats`,
    tasks ? `${tasks} open task${tasks > 1 ? "s" : ""}` : "",
    attention ? "needs attention" : "",
    unvisited ? "not visited yet" : "",
  ].filter(Boolean).join(", ");

  return (
    <button
      type="button"
      className={`tile st-${t.status} cap-${Math.min(t.capacity, 6)} ${selected ? "is-selected" : ""} ${attention ? "is-attention" : ""} ${changed ? "is-changed" : ""}`}
      style={{ left: `${t.pos_x}%`, top: `${t.pos_y}%` }}
      aria-pressed={selected}
      aria-label={desc}
      onClick={(e) => {
        e.stopPropagation();
        onSelect(selected ? null : t.id);
      }}
    >
      <span className="tile-top">
        <span className="tile-num">{t.label}</span>
        <span className="tile-status">
          <Icon size={12} className="tile-icon" aria-hidden />
          {t.status === "occupied" && <span className="tabular">{t.party_size || "?"}/{t.capacity}</span>}
        </span>
      </span>
      {timed ? (
        <span className="tile-timer tabular">{dur(since(t.status_since, now))}</span>
      ) : (
        <span className="tile-meta">
          {t.status === "out_of_service" ? "Closed" : <><Armchair size={11} aria-hidden />{t.capacity}</>}
        </span>
      )}
      {tasks > 0 && (
        <span className="tile-badge" aria-hidden>
          {attention && <BellRing size={10} />}
          {tasks}
        </span>
      )}
      {!tasks && attention && <span className="tile-badge" aria-hidden><BellRing size={10} /></span>}
      {unvisited && <span className="tile-flag">No visit</span>}
    </button>
  );
});
