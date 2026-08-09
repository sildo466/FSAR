// SPDX-License-Identifier: MIT
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
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
  const { t } = useTranslation();
  const config = useWS((s) => s.config);
  const send = useWS((s) => s.send);
  const client = useWS((s) => s.client);
  const [events, setEvents] = useState<ReflectionEvent[]>([]);

  useEffect(() => {
    if (!client) return;
    const off = client.on((msg) => {
      if (msg.type === "reflection.event") {
        setEvents((prev) => [msg.event as ReflectionEvent, ...prev].slice(0, 50));
      } else if (msg.type === "reflection.list_result") {
        setEvents((prev) => {
          const seen = new Set(prev.map((e) => e.task_id));
          const missing = msg.events.filter((e) => !seen.has(e.task_id));
          return [...missing, ...prev].slice(0, 50);
        });
      }
    });
    client.send({ type: "reflection.list", limit: 20 });
    return off;
  }, [client]);

  const reflection = readReflection(config);
  const intensity: Level = reflection.intensity ?? "medium";
  const triggers = reflection.triggers ?? {};
  const idle = triggers.idle_batch ?? {};

  const patchTrigger = (key: string, value: unknown) => {
    send({ type: "settings.patch", patch: { [`reflection.triggers.${key}`]: value } });
  };

  const parts: string[] = [];
  if (triggers.per_task) parts.push(t("reflection.trigger.perTask"));
  if (triggers.on_failure) parts.push(t("reflection.trigger.onFailure"));
  if (idle.enabled) parts.push(t("reflection.trigger.idleBatch"));
  const summary = parts.length > 0 ? parts.join(" + ") : t("reflection.trigger.none");

  return (
    <div className="max-w-[720px] mx-auto px-8 py-10 flex flex-col gap-10">
      <header>
        <h1 className="font-display text-2xl font-semibold tracking-[-0.01em]">{t("reflection.title")}</h1>
        <p className="text-text-muted">{t("reflection.subtitle")}</p>
      </header>
      <section className="flex flex-col items-center gap-3">
        <div className="font-display text-[10px] font-bold uppercase tracking-[0.1em] text-text-muted">
          {t("reflection.intensity")}
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
          {t("reflection.triggerModes")}
        </div>
        <ModeToggle
          label={t("reflection.trigger.perTask")}
          description={t("reflection.trigger.perTaskDesc")}
          enabled={!!triggers.per_task}
          onToggle={() => patchTrigger("per_task", !triggers.per_task)}
        />
        <ModeToggle
          label={t("reflection.trigger.onFailure")}
          description={t("reflection.trigger.onFailureDesc")}
          enabled={!!triggers.on_failure}
          onToggle={() => patchTrigger("on_failure", !triggers.on_failure)}
        />
        <ModeToggle
          label={t("reflection.trigger.idleBatch")}
          description={t("reflection.trigger.idleBatchDesc")}
          enabled={!!idle.enabled}
          onToggle={() => patchTrigger("idle_batch.enabled", !idle.enabled)}
        >
          <div className="flex">
            <ThresholdInput
              label={t("reflection.triggerWhen")}
              value={idle.threshold_events ?? 20}
              unit={t("reflection.unitEvents")}
              onChange={(v) => patchTrigger("idle_batch.threshold_events", v)}
            />
            <ThresholdInput
              label={t("reflection.triggerOr")}
              value={idle.threshold_hours ?? 12}
              unit={t("reflection.unitHours")}
              onChange={(v) => patchTrigger("idle_batch.threshold_hours", v)}
            />
          </div>
        </ModeToggle>
      </section>
      <hr className="border-border" />
      <section>
        <h2 className="font-display text-[10px] font-bold uppercase tracking-[0.1em] text-text-muted mb-3">
          {t("reflection.recent")}
        </h2>
        <ReflectionStream events={events} />
      </section>
    </div>
  );
}
