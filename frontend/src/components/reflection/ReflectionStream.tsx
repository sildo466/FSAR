// SPDX-License-Identifier: Apache-2.0
export interface ReflectionEvent {
  task_id: string;
  outcome: string;
  suggested_strategy: string;
  step_count: number;
  tools_used: string[];
  created_at: string;
}

interface Props {
  events: ReflectionEvent[];
}

export function ReflectionStream({ events }: Props) {
  if (events.length === 0) {
    return <p className="text-text-muted text-sm">No reflections yet.</p>;
  }
  return (
    <ul className="flex flex-col divide-y divide-border">
      {events.map((e) => (
        <li key={e.task_id} className="py-3 flex flex-col gap-1">
          <div className="flex items-center gap-3">
            <span className="font-mono text-xs text-text-muted">
              {new Date(e.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
            </span>
            <span className="text-sm">task {e.task_id.slice(0, 16)}…</span>
          </div>
          <div className="text-xs text-text-muted">
            {e.outcome} · {e.tools_used.join(", ") || "no tools"}
          </div>
          {e.suggested_strategy && (
            <div className="text-sm pl-4">▸ {e.suggested_strategy}</div>
          )}
        </li>
      ))}
    </ul>
  );
}
