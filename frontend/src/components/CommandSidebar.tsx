import { BarChart3, LayoutGrid, PanelLeftClose, PanelLeftOpen, Smartphone, Users } from "lucide-react";
import { NavLink } from "react-router-dom";
import type { SystemStatus } from "../derive";
import { ConnectionStatus } from "./ConnectionStatus";
import { StatusDot } from "./ui";

export const NAV = [
  { to: "/", end: true, label: "Live Operations", short: "Live", icon: LayoutGrid },
  { to: "/manager", end: false, label: "Manager", short: "Manager", icon: Smartphone },
  { to: "/analytics", end: false, label: "Reports", short: "Reports", icon: BarChart3 },
  { to: "/staff", end: false, label: "Staff", short: "Staff", icon: Users },
] as const;

export function CommandSidebar({ collapsed, onToggle, status, criticalCount }: {
  collapsed: boolean; onToggle: () => void; status: SystemStatus; criticalCount: number;
}) {
  const worst = [status.cameras.health, status.pos.health, status.sync.health].includes("bad")
    ? "bad"
    : [status.cameras.health, status.pos.health].some((h) => h === "warn" || h === "idle")
      ? "warn"
      : "ok";
  return (
    <aside className={`sidebar ${collapsed ? "collapsed" : ""}`} aria-label="Main navigation">
      <div className="sidebar-brand">
        <span className="brand-mark" aria-hidden>
          <span /><span /><span /><span />
        </span>
        <span className="brand-text">
          <strong>Floor Ops</strong>
          <small>Command Centre</small>
        </span>
      </div>

      <nav className="sidebar-nav">
        {NAV.map((n) => (
          <NavLink key={n.to} to={n.to} end={n.end} className="nav-item" title={n.label} aria-label={n.label}>
            <n.icon size={18} aria-hidden />
            <span className="nav-label">{n.label}</span>
            {n.to === "/" && criticalCount > 0 && (
              <span className="nav-badge" aria-label={`${criticalCount} critical alerts`}>{criticalCount}</span>
            )}
          </NavLink>
        ))}
      </nav>

      <div className="sidebar-foot">
        <section className="sidebar-status" aria-label="System status">
          <h3 className="eyebrow">
            <StatusDot health={worst} /> <span className="nav-label">System status</span>
          </h3>
          <div className="nav-label">
            <ConnectionStatus status={status} />
          </div>
        </section>
        <button type="button" className="nav-item collapse-btn" onClick={onToggle}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"} aria-expanded={!collapsed}>
          {collapsed ? <PanelLeftOpen size={18} aria-hidden /> : <PanelLeftClose size={18} aria-hidden />}
          <span className="nav-label">Collapse</span>
        </button>
      </div>
    </aside>
  );
}

/** Phone-width navigation. */
export function BottomNav({ criticalCount }: { criticalCount: number }) {
  return (
    <nav className="bottom-nav" aria-label="Main navigation">
      {NAV.map((n) => (
        <NavLink key={n.to} to={n.to} end={n.end} className="bottom-item" aria-label={n.label}>
          <n.icon size={20} aria-hidden />
          <span>{n.short}</span>
          {n.to === "/" && criticalCount > 0 && <span className="nav-badge">{criticalCount}</span>}
        </NavLink>
      ))}
    </nav>
  );
}
