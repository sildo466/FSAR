import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useWS } from "../../stores/ws";
import { readActiveId, readProviders } from "../../pages/Settings";

export function JudgeSection() {
  const { t } = useTranslation();
  const send = useWS((s) => s.send);
  const client = useWS((s) => s.client);
  const config = useWS((s) => s.config);
  const [loaded, setLoaded] = useState(false);
  const [custom, setCustom] = useState(false);
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("");
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!client) return;
    send({ type: "llm.get_judge" });
    return client.on((msg) => {
      if (msg.type === "llm.judge_config") {
        const j = msg.judge ?? { base_url: "", api_key: "", model: "" };
        setCustom(Boolean(j.model) && Boolean(j.base_url));
        setBaseUrl(j.base_url ?? "");
        setApiKey(j.api_key ?? "");
        setModel(j.model ?? "");
        setLoaded(true);
      } else if (msg.type === "llm.judge_changed") {
        setSaved(true);
        setError("");
        window.setTimeout(() => setSaved(false), 2000);
      } else if (msg.type === "error") {
        setError(msg.message ?? t("settings.judge.saveFailed"));
      }
    });
  }, [client, send, t]);

  const active = readProviders(config).find((p) => p.id === readActiveId(config));
  const currentModel = active?.model ?? "";

  function save() {
    setError("");
    if (custom && (!baseUrl.trim() || !model.trim())) {
      setError(t("settings.judge.incomplete"));
      return;
    }
    if (custom) {
      send({ type: "llm.set_judge", base_url: baseUrl, api_key: apiKey, model });
    } else {
      send({ type: "llm.set_judge", base_url: "", api_key: "", model: "" });
    }
  }

  return (
    <div className="pt-6 border-t border-border">
      <h3 className="font-display text-sm font-semibold">{t("settings.judge.title")}</h3>
      {loaded && (
        <div className="mt-3 flex flex-col gap-3">
          <label className="flex items-center gap-2">
            <input type="radio" checked={!custom} onChange={() => setCustom(false)} />
            <span className="text-[13px]">{t("settings.judge.useMain", { model: currentModel })}</span>
          </label>
          <label className="flex items-center gap-2">
            <input type="radio" checked={custom} onChange={() => setCustom(true)} />
            <span className="text-[13px]">{t("settings.judge.custom")}</span>
          </label>
          {custom && (
            <div className="flex flex-col gap-2">
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder={t("settings.judge.baseUrl")} className="rounded-lg border border-border bg-bg/30 px-3 py-1.5 text-[12px]" />
                <input type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder={t("settings.judge.apiKey")} className="rounded-lg border border-border bg-bg/30 px-3 py-1.5 text-[12px]" />
                <input value={model} onChange={(e) => setModel(e.target.value)} placeholder={t("settings.judge.model")} className="rounded-lg border border-border bg-bg/30 px-3 py-1.5 text-[12px]" />
              </div>
              <p className="text-[11px] leading-relaxed text-text-muted">
                {t("settings.judge.customHint")}
              </p>
            </div>
          )}
          <div className="flex items-center gap-3">
            <button onClick={save} className="rounded-full bg-[var(--button-bg)] text-[var(--button-text)] button-tex px-4 py-1.5 text-[12px]">{t("settings.judge.save")}</button>
            {saved && <span className="text-[12px] text-text-muted">{t("settings.judge.saved")}</span>}
            {error && <span className="text-[12px] text-red-500">{error}</span>}
          </div>
        </div>
      )}
    </div>
  );
}
