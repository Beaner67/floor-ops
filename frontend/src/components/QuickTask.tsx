import { useState } from "react";
import { Plus } from "lucide-react";
import { api } from "../api";
import type { Staff, Table } from "../types";

/** Manual task creation at the counter. Shown when no table is selected. */
export function QuickTask({ tables, staff }: { tables: Table[]; staff: Staff[] }) {
  const [title, setTitle] = useState("");
  const [table, setTable] = useState("");
  const [who, setWho] = useState("");
  const [priority, setPriority] = useState("medium");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await api.createTask({
        title: title.trim(), priority,
        table_id: table ? Number(table) : null,
        staff_id: who ? Number(who) : null,
      });
      setTitle("");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="card quick" onSubmit={submit} aria-labelledby="quick-title">
      <div className="card-head">
        <div>
          <h2 id="quick-title">Create task</h2>
          <p className="card-sub">Manual task for the floor team</p>
        </div>
      </div>
      <label className="field">
        <span className="sr-only">Task</span>
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Refill water at table 6" />
      </label>
      <div className="quick-row">
        <label className="select-wrap">
          <span className="sr-only">Table</span>
          <select value={table} onChange={(e) => setTable(e.target.value)}>
            <option value="">No table</option>
            {tables.map((t) => <option key={t.id} value={t.id}>Table {t.label}</option>)}
          </select>
        </label>
        <label className="select-wrap">
          <span className="sr-only">Assign to</span>
          <select value={who} onChange={(e) => setWho(e.target.value)}>
            <option value="">Unassigned</option>
            {staff.filter((s) => s.on_shift).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </label>
        <label className="select-wrap">
          <span className="sr-only">Priority</span>
          <select value={priority} onChange={(e) => setPriority(e.target.value)}>
            <option value="low">Normal</option>
            <option value="medium">Warning</option>
            <option value="high">Critical</option>
          </select>
        </label>
      </div>
      <button className="btn btn-primary btn-block" type="submit" disabled={!title.trim() || busy}>
        <Plus size={16} aria-hidden /> Add task
      </button>
      {error && <p className="err" role="alert">{error}</p>}
    </form>
  );
}
