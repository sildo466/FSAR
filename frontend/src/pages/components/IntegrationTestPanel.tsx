import { useState } from "react";
import { FlaskConical, Play, RotateCcw } from "lucide-react";
import { useTranslation } from "react-i18next";
import { integrationClient, type RunEvent, type RunFinalResponse } from "../../clients/integrationClient";
import { InlineMarkdown } from "./InlineMarkdown";

export function IntegrationTestPanel({ integrationId }: { integrationId: number }) {
  const { t } = useTranslation();
  const [message, setMessage] = useState("");
  const [mode, setMode] = useState<"replay" | "estimate">("replay");
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [result, setResult] = useState<RunFinalResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");

  const run = async () => {
    setEvents([]);
    setResult(null);
    setError("");
    setRunning(true);
    try {
      const final = await integrationClient.run(integrationId, message, mode, (event) => {
        setEvents((current) => [...current, event]);
      });
      setResult(final);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setRunning(false);
    }
  };

  const routing = events.find((event) => event.type === "integration.routing_done") as any;
  const rounds = events.filter((event) => event.type === "integration.debate_round_done");

  return (
    <section className="rounded-[28px] border border-[var(--border)] bg-[var(--glass)] p-5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 font-display text-lg font-semibold"><FlaskConical size={17} /> {t("integration.testChamber")}</div>
          <p className="mt-1 text-[11px] text-text-muted">{t("integration.testChamberDesc")}</p>
        </div>
        <div className="flex rounded-full bg-[var(--glow-faint)] p-1 text-[10px] font-mono uppercase tracking-[0.1em]">
          <label className={`cursor-pointer rounded-full px-3 py-1.5 ${mode === "replay" ? "bg-[var(--button-bg)] text-[var(--button-text)] button-tex" : "text-text-muted"}`}>
            <input className="sr-only" type="radio" checked={mode === "replay"} onChange={() => setMode("replay")} /> {t("integration.replayActual")}
          </label>
          <label className={`cursor-pointer rounded-full px-3 py-1.5 ${mode === "estimate" ? "bg-[var(--button-bg)] text-[var(--button-text)] button-tex" : "text-text-muted"}`}>
            <input className="sr-only" type="radio" checked={mode === "estimate"} onChange={() => setMode("estimate")} /> {t("integration.estimateOnly")}
          </label>
        </div>
      </div>
      <textarea value={message} onChange={(event) => setMessage(event.target.value)} placeholder={t("integration.testMessagePlaceholder")} rows={4} className="mt-4 w-full resize-y rounded-[20px] bg-[var(--glow-faint)] px-4 py-3 text-[13px] leading-relaxed outline-none" />
      <button type="button" disabled={running} onClick={run} className="mt-3 flex w-full items-center justify-center gap-2 rounded-full bg-text py-2.5 text-[11px] font-semibold text-bg transition hover:scale-[1.01] disabled:opacity-50">
        {running ? <RotateCcw size={14} className="animate-spin" /> : <Play size={14} />} {t("integration.runOnce")}
      </button>
      {error && <div role="alert" className="mt-3 rounded-xl bg-danger/10 px-3 py-2 text-[12px] text-danger">{error}</div>}
      {(routing || result) && (
        <div className="mt-4 space-y-2 border-t border-[var(--border)] pt-4 text-[12px]">
          {routing && <div><span className="font-mono text-text-muted">Routing</span> · picked {routing.selected?.join(", ") || "main only"}</div>}
          {rounds.length > 0 && <div><span className="font-mono text-text-muted">Debate</span> · {rounds.length} round{rounds.length === 1 ? "" : "s"}</div>}
          {result && <div><span className="font-mono text-text-muted">{t("integration.cost")}</span> · {result.total_cost_usd ?? "?"} USD · {t("integration.callsCount", { count: result.total_calls })}</div>}
          {result?.errors && result.errors.length > 0 && (
            <div role="alert" className="rounded-xl bg-danger/10 px-3 py-2 text-[12px] text-danger">
              <div className="font-semibold">{t("integration.runErrors")}</div>
              <ul className="mt-1 list-disc space-y-0.5 pl-4 font-mono text-[11px]">
                {result.errors.map((item, index) => <li key={index}>{item}</li>)}
              </ul>
            </div>
          )}
          {result?.final_reply && <div className="rounded-2xl bg-[var(--glow-faint)] p-3 leading-relaxed"><InlineMarkdown>{result.final_reply}</InlineMarkdown></div>}
        </div>
      )}
    </section>
  );
}
