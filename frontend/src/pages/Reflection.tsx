// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { IntensitySegment } from "../components/reflection/IntensitySegment";
import { ModeToggle } from "../components/reflection/ModeToggle";
import { ThresholdInput } from "../components/reflection/ThresholdInput";
import {
  ReflectionStream,
  type ReflectionEvent,
} from "../components/reflection/ReflectionStream";
import { useWS } from "../stores/ws";

type Level = "off" | "low" | "medium" | "high";

interface ReflectionSection {
  intensity?: Level;
  triggers?: {
    per_task?: boolean;
    on_failure?: boolean;
    idle_batch?: {
      enabled?: boolean;
      threshold_events?: number;
      threshold_hours?: number;
    };
  };
}

function readReflection(config: Record<string, unknown> | null): ReflectionSection {
  const r = (config?.reflection ?? {}) as ReflectionSection;
  return r;
}

export function Reflection() {
  const config = useWS((s) => s.config);
  const send = useWS((s) => s.send);
  const client = useWS((s) => s.client);
  const [events, setEvents] = useState<ReflectionEvent[]>([]);

  useEffect(() => {
    return client?.on((msg) => {
      if (msg.type === "reflection.event") {
        setEvents((prev) => [msg.event as ReflectionEvent, ...prev].slice(0, 50));
      }
    });
  }, [client]);

  const reflection = readReflection(config);
  const intensity: Level = reflection.intensity ?? "medium";
  const triggers = reflection.triggers ?? {};
  const idle = triggers.idle_batch ?? {};

  const patchTrigger = (key: string, value: unknown) => {
    send({ type: "settings.patch", patch: { [`reflection.triggers.${key}`]: value } });
  };

  const parts: string[] = [];
  if (triggers.per_task) parts.push("per-task");
  if (triggers.on_failure) parts.push("on-failure");
  if (idle.enabled) parts.push("idle-batch");
  const summary = parts.length > 0 ? parts.join(" + ") : "no triggers";

  return (
    <div className="max-w-[720px] mx-auto px-8 py-10 flex flex-col gap-10">
      <header>
        <h1 className="font-display text-2xl font-semibold tracking-[-0.01em]">Reflection</h1>
        <p className="text-text-muted">Self-evolving calibration</p>
      </header>
      <section className="flex flex-col items-center gap-3">
        <div className="font-display text-[10px] font-bold uppercase tracking-[0.1em] text-text-muted">
          Reflection Intensity
        </div>
        <IntensitySegment
          value={intensity}
          onChange={(v) => send({ type: "reflection.set_intensity", intensity: v })}
        />
        <p className="text-[13px] text-text-muted">
          {intensity} · {summary}
        </p>
      </section>
      <hr className="border-border" />
      <section className="flex flex-col gap-1">
        <div className="font-display text-[10px] font-bold uppercase tracking-[0.1em] text-text-muted mb-2">
          Trigger Modes
        </div>
        <ModeToggle
          label="Per-task"
          description="every task end"
          enabled={!!triggers.per_task}
          onToggle={() => patchTrigger("per_task", !triggers.per_task)}
        />
        <ModeToggle
          label="On-failure"
          description="failed / timed-out / low-score"
          enabled={!!triggers.on_failure}
          onToggle={() => patchTrigger("on_failure", !triggers.on_failure)}
        />
        <ModeToggle
          label="Idle-batch"
          description="accumulate, reflect periodically"
          enabled={!!idle.enabled}
          onToggle={() => patchTrigger("idle_batch.enabled", !idle.enabled)}
        >
          <div className="flex">
            <ThresholdInput
              label="trigger when"
              value={idle.threshold_events ?? 20}
              unit="events"
              onChange={(v) => patchTrigger("idle_batch.threshold_events", v)}
            />
            <ThresholdInput
              label="or"
              value={idle.threshold_hours ?? 12}
              unit="hours"
              onChange={(v) => patchTrigger("idle_batch.threshold_hours", v)}
            />
          </div>
        </ModeToggle>
      </section>
      <hr className="border-border" />
      <section>
        <h2 className="font-display text-[10px] font-bold uppercase tracking-[0.1em] text-text-muted mb-3">
          Recent reflections
        </h2>
        <ReflectionStream events={events} />
      </section>
    </div>
  );
}
