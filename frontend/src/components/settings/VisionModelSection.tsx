import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useWS } from "../../stores/ws";
import { readActiveId, readProviders } from "../../pages/Settings";

export function VisionModelSection() {
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
    send({ type: "llm.get_vision" });
    return client.on((msg) => {
      if (msg.type === "llm.vision_config") {
        const vm = msg.vision_model ?? { base_url: "", api_key: "", model: "" };
        setCustom(Boolean(vm.model) && Boolean(vm.base_url));
        setBaseUrl(vm.base_url ?? "");
        setApiKey(vm.api_key ?? "");
        setModel(vm.model ?? "");
        setLoaded(true);
      } else if (msg.type === "llm.vision_changed") {
        setSaved(true);
        setError("");
        window.setTimeout(() => setSaved(false), 2000);
      } else if (msg.type === "error") {
        setError(msg.message ?? t("settings.vision.saveFailed"));
      }
    });
  }, [client, send, t]);

  const active = readProviders(config).find((p) => p.id === readActiveId(config));
  const currentModel = active?.model ?? "";

  function save() {
    setError("");
    if (custom && (!baseUrl.trim() || !model.trim())) {
      setError(t("settings.vision.incomplete"));
      return;
    }
    if (custom) {
      send({ type: "llm.set_vision", base_url: baseUrl, api_key: apiKey, model });
    } else {
      send({ type: "llm.set_vision", base_url: "", api_key: "", model: "" });
    }
  }

  return (
    <div className="pt-6 border-t border-border">
      <h3 className="font-display text-sm font-semibold">{t("settings.vision.title")}</h3>
      {loaded && (
        <div className="mt-3 flex flex-col gap-3">
          <label className="flex items-center gap-2">
            <input type="radio" checked={!custom} onChange={() => setCustom(false)} />
            <span className="text-[13px]">{t("settings.vision.useMain", { model: currentModel })}</span>
          </label>
          <label className="flex items-center gap-2">
            <input type="radio" checked={custom} onChange={() => setCustom(true)} />
            <span className="text-[13px]">{t("settings.vision.custom")}</span>
          </label>
          {custom && (
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
              <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder={t("settings.vision.baseUrl")} className="rounded-lg border border-border bg-bg/30 px-3 py-1.5 text-[12px]" />
              <input type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder={t("settings.vision.apiKey")} className="rounded-lg border border-border bg-bg/30 px-3 py-1.5 text-[12px]" />
              <input value={model} onChange={(e) => setModel(e.target.value)} placeholder={t("settings.vision.model")} className="rounded-lg border border-border bg-bg/30 px-3 py-1.5 text-[12px]" />
            </div>
          )}
          <div className="flex items-center gap-3">
            <button onClick={save} className="rounded-full bg-[var(--button-bg)] text-[var(--button-text)] button-tex px-4 py-1.5 text-[12px]">{t("settings.vision.save")}</button>
            {saved && <span className="text-[12px] text-text-muted">{t("settings.vision.saved")}</span>}
            {error && <span className="text-[12px] text-red-500">{error}</span>}
          </div>
        </div>
      )}
    </div>
  );
}
