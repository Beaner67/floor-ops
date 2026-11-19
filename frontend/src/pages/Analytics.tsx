import { useEffect, useState } from "react";
import { api, type Analytics as Report } from "../api";
import { dur } from "../time";
import { Skeleton } from "../components/ui";

const WINDOWS = [
  { hours: 12, label: "Last 12 h" },
  { hours: 24, label: "Last 24 h" },
  { hours: 24 * 7, label: "Last 7 days" },
];

export function Analytics() {
  const [hours, setHours] = useState(24);
  const [r, setR] = useState<Report | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    const load = () => api.analytics(hours).then((x) => live && setR(x)).catch((e) => live && setErr(e.message));
    load();
    const id = setInterval(load, 15000);
    return () => {
      live = false;
      clearInterval(id);
    };
  }, [hours]);

  if (err) return <div className="page"><p className="notice notice-bad" role="alert">Could not load the report: {err}</p></div>;
  if (!r)
    return (
      <div className="page analytics" aria-busy="true">
        <div className="stat-grid">{Array.from({ length: 8 }, (_, i) => <Skeleton key={i} h={96} r={12} />)}</div>
        <Skeleton h={240} r={12} />
      </div>
    );

  const v = r.tasks.verification;
  const aiVerified = v["verified:ai"] ?? 0;
  const manual = v["verified:manual"] ?? 0;
  const failed = (v["verification_failed:ai"] ?? 0);
  const uncertain = (v["verification_uncertain:ai"] ?? 0);

  return (
    <div className="page analytics">
      <div className="page-head row">
        <div>
          <h2>Operations report</h2>
          <p className="card-sub">Refreshes every 15 seconds</p>
        </div>
        <div className="seg">
          {WINDOWS.map((w) => (
            <button type="button" key={w.hours} aria-pressed={w.hours === hours} className={w.hours === hours ? "on" : ""} onClick={() => setHours(w.hours)}>{w.label}</button>
          ))}
        </div>
      </div>

      <div className="stat-grid">
        <Stat label="Avg wait for first staff visit" value={dur(r.customers.avg_wait_for_first_visit_s)} />
        <Stat label="Avg response to raised hand" value={dur(r.service.avg_assist_response_s)} sub={`${r.service.assist_requests} requests`} />
        <Stat label="Avg table turnaround (left → clean)" value={dur(r.cleaning.avg_clean_duration_s)} sub={`${r.cleaning.tables_cleaned} tables cleaned`} />
        <Stat label="Avg kitchen prep" value={dur(r.orders.avg_prep_s)} sub={`${r.orders.delayed} of ${r.orders.count} orders late`} />
        <Stat label="Avg ready → table" value={dur(r.orders.avg_ready_to_table_s)} />
        <Stat label="Parties seated" value={String(r.customers.seatings)} sub={`avg stay ${dur(r.customers.avg_stay_s)}`} />
        <Stat label="Open tasks now" value={String(r.tasks.open_now)} sub={`${r.tasks.overdue_now} overdue`} />
        <Stat label="Peak hour" value={r.peak_hour == null ? "–" : `${String(r.peak_hour).padStart(2, "0")}:00`} />
      </div>

      <section className="card">
        <div className="card-head"><h2>Occupancy by hour</h2><span className="chart-legend"><i className="lg-a" /> Avg people inside <i className="lg-b" /> Parties seated</span></div>
        <HourlyChart rows={r.hourly} />
      </section>

      <div className="two-col">
        <section className="card">
          <div className="card-head"><h2>Task verification</h2></div>
          <VerifyBar parts={[
            { label: "Camera verified", n: aiVerified, cls: "seg-ok" },
            { label: "Confirmed by hand", n: manual, cls: "seg-manual" },
            { label: "Awaiting review: failed", n: failed, cls: "seg-bad" },
            { label: "Awaiting review: unsure", n: uncertain, cls: "seg-unsure" },
          ]} />
        </section>
        <section className="card">
          <div className="card-head"><h2>Task activity by staff</h2><span className="card-sub">Counts only, no scoring</span></div>
          <div className="table-scroll"><table className="grid">
            <thead><tr><th>Name</th><th>Assigned</th><th>Done</th><th>Verified</th><th>In review</th><th>Avg time</th></tr></thead>
            <tbody>
              {r.staff.map((s) => (
                <tr key={s.staff_id}>
                  <td>{s.name}</td><td>{s.assigned}</td><td>{s.completed}</td><td>{s.verified}</td><td>{s.needs_review}</td>
                  <td className="tabular">{dur(s.avg_completion_s)}</td>
                </tr>
              ))}
            </tbody>
          </table></div>
        </section>
      </div>
    </div>
  );
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="stat">
      <span className="stat-label">{label}</span>
      <span className="stat-value tabular">{value}</span>
      {sub && <span className="stat-sub">{sub}</span>}
    </div>
  );
}

function HourlyChart({ rows }: { rows: Report["hourly"] }) {
  const max = Math.max(1, ...rows.map((r) => Math.max(r.avg_people, r.seatings)));
  const W = 960, H = 180, pad = 24, bw = (W - pad) / 24;
  return (
    <svg className="chart" viewBox={`0 0 ${W} ${H + 22}`} role="img" aria-label="Hourly occupancy">
      {[0.5, 1].map((f) => (
        <line key={f} x1={pad} x2={W} y1={H - f * (H - 10)} y2={H - f * (H - 10)} className="gridline" />
      ))}
      <text x={0} y={14} className="axis">{Math.round(max)}</text>
      {rows.map((r, i) => {
        const x = pad + i * bw;
        const hp = (r.avg_people / max) * (H - 10);
        const hs = (r.seatings / max) * (H - 10);
        return (
          <g key={r.hour}>
            <rect x={x + 3} y={H - hp} width={bw / 2 - 3} height={hp} className="bar-a" rx={2}>
              <title>{`${r.hour}:00 – avg ${r.avg_people} people`}</title>
            </rect>
            <rect x={x + bw / 2} y={H - hs} width={bw / 2 - 3} height={hs} className="bar-b" rx={2}>
              <title>{`${r.hour}:00 – ${r.seatings} parties seated`}</title>
            </rect>
            {r.hour % 3 === 0 && <text x={x + bw / 2} y={H + 16} className="axis" textAnchor="middle">{String(r.hour).padStart(2, "0")}</text>}
          </g>
        );
      })}
    </svg>
  );
}

function VerifyBar({ parts }: { parts: { label: string; n: number; cls: string }[] }) {
  const total = parts.reduce((a, p) => a + p.n, 0);
  if (!total) return <p className="muted small">No verified tasks yet in this window.</p>;
  return (
    <>
      <div className="vbar">
        {parts.filter((p) => p.n).map((p) => (
          <span key={p.label} className={p.cls} style={{ flexGrow: p.n }} title={`${p.label}: ${p.n}`} />
        ))}
      </div>
      <ul className="vlegend">
        {parts.map((p) => (
          <li key={p.label}><i className={p.cls} />{p.label}<strong className="tabular">{p.n}</strong></li>
        ))}
      </ul>
    </>
  );
}
