import { useEffect, useRef, useState, type ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import type { Health } from "../derive";

export function StatusDot({ health, pulse = false }: { health: Health; pulse?: boolean }) {
  return <span className={`dot dot-${health} ${pulse ? "dot-pulse" : ""}`} aria-hidden />;
}

/** Number that briefly highlights when its value changes. */
export function LiveNumber({ value, className = "" }: { value: number | string; className?: string }) {
  const prev = useRef(value);
  const [bump, setBump] = useState(0);
  useEffect(() => {
    if (prev.current !== value) {
      prev.current = value;
      setBump((b) => b + 1);
    }
  }, [value]);
  return (
    <span key={bump} className={`tabular ${bump ? "num-bump" : ""} ${className}`}>
      {value}
    </span>
  );
}

/**
 * Two-step button for consequential actions: first tap arms it, second tap within
 * 4 s runs it. Touch-friendly alternative to a modal confirm on a busy counter.
 */
export function ConfirmButton({
  onConfirm, children, confirmLabel = "Tap again to confirm", className = "", disabled, icon: Icon,
}: {
  onConfirm: () => void | Promise<unknown>;
  children: ReactNode;
  confirmLabel?: string;
  className?: string;
  disabled?: boolean;
  icon?: LucideIcon;
}) {
  const [armed, setArmed] = useState(false);
  useEffect(() => {
    if (!armed) return;
    const id = setTimeout(() => setArmed(false), 4000);
    return () => clearTimeout(id);
  }, [armed]);
  return (
    <button
      type="button"
      className={`btn ${armed ? "btn-danger" : ""} ${className}`}
      disabled={disabled}
      aria-live="polite"
      onClick={() => {
        if (armed) {
          setArmed(false);
          void onConfirm();
        } else setArmed(true);
      }}
      onBlur={() => setArmed(false)}
    >
      {Icon && <Icon size={15} aria-hidden />}
      {armed ? confirmLabel : children}
    </button>
  );
}

export function EmptyState({ icon: Icon, title, children }: { icon: LucideIcon; title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <Icon size={20} aria-hidden />
      <strong>{title}</strong>
      {children && <p>{children}</p>}
    </div>
  );
}

export function Skeleton({ h = 16, w = "100%", r = 6 }: { h?: number; w?: number | string; r?: number }) {
  return <span className="skeleton" style={{ height: h, width: w, borderRadius: r }} aria-hidden />;
}

export function Switch({ checked, onChange, label, icon: Icon }: {
  checked: boolean; onChange: (v: boolean) => void; label: string; icon?: LucideIcon;
}) {
  return (
    <button type="button" role="switch" aria-checked={checked} className={`switch ${checked ? "on" : ""}`}
      onClick={() => onChange(!checked)}>
      {Icon && <Icon size={14} aria-hidden />}
      <span>{label}</span>
      <span className="switch-track" aria-hidden><span className="switch-thumb" /></span>
    </button>
  );
}

export function initials(name: string | null | undefined): string {
  return (name ?? "?").split(/\s+/).map((p) => p[0]).join("").slice(0, 2).toUpperCase();
}
