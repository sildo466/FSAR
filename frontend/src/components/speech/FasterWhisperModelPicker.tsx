// SPDX-License-Identifier: MIT
import { useEffect, useState } from "react";
import { Download, Trash2 } from "lucide-react";
import { useSpeechStore } from "../../stores/speech";
import { useTranslation } from "react-i18next";

const FALLBACK_SIZES: Record<string, number> = {
  tiny: 75_000_000,
  base: 150_000_000,
  small: 500_000_000,
  medium: 1_500_000_000,
  "large-v3": 3_000_000_000,
};

interface Props {
  selected: string;
  onSelect: (size: string) => void;
}

export function FasterWhisperModelPicker({ selected, onSelect }: Props) {
  const { t } = useTranslation();
  const [downloaded, setDownloaded] = useState<string[]>([]);
  const [sizes, setSizes] = useState(FALLBACK_SIZES);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  const progress = useSpeechStore((state) => state.downloadProgress);
  const lastDownloadEndpoint = useSpeechStore((state) => state.lastDownloadEndpoint);
  const listModels = useSpeechStore((state) => state.listDownloadedModels);
  const downloadModel = useSpeechStore((state) => state.downloadModel);
  const deleteModel = useSpeechStore((state) => state.deleteModel);

  const refresh = async () => {
    try {
      const catalog = await listModels();
      setDownloaded(catalog.downloaded);
      setSizes(catalog.sizes);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : t("speech.fw.listFailed"));
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const download = async (size: string) => {
    setBusy(size);
    setError("");
    try {
      await downloadModel(size);
      onSelect(size);
      await refresh();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : t("speech.fw.downloadFailed"));
    } finally {
      setBusy(null);
    }
  };

  const remove = async (size: string) => {
    setBusy(size);
    try {
      await deleteModel(size);
      if (selected === size) onSelect("");
      await refresh();
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="rounded-2xl border border-border bg-bg/30 p-4">
      <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-text-faint">{t("speech.fw.localModelPath")}</div>
      {lastDownloadEndpoint?.source === "mirror" && (
        <p aria-live="polite" className="mt-1 font-mono text-[10px] text-text-muted">{t("speech.fw.usingMirror", { url: lastDownloadEndpoint.url })}</p>
      )}
      <div className="mt-3 space-y-2">
        {Object.entries(sizes).map(([size, bytes]) => {
          const ready = downloaded.includes(size);
          const percent = progress[size] ?? 0;
          return (
            <div key={size} className="relative overflow-hidden rounded-xl border border-border px-3 py-2">
              {busy === size && <div className="absolute inset-y-0 left-0 bg-text/[0.06] transition-all" style={{ width: `${percent}%` }} />}
              <div className="relative flex items-center gap-3">
                <input type="radio" name="faster-whisper-model" aria-label={t("speech.fw.useSize", { size })} checked={selected === size} disabled={!ready} onChange={() => onSelect(size)} />
                <div className="min-w-0 flex-1"><span className="font-mono text-xs">{size}</span><span className="ml-2 text-[10px] text-text-muted">{(bytes / 1_000_000).toFixed(0)} MB</span></div>
                {ready ? (
                  <button type="button" aria-label={t("speech.fw.deleteSize", { size })} disabled={busy !== null} onClick={() => void remove(size)} className="rounded-full p-1.5 text-text-muted hover:bg-glass hover:text-red-400"><Trash2 size={13} /></button>
                ) : (
                  <button type="button" disabled={busy !== null} onClick={() => void download(size)} className="flex items-center gap-1 rounded-full border border-border px-2.5 py-1 text-[10px] disabled:opacity-40"><Download size={11} />{busy === size ? `${percent.toFixed(0)}%` : t("speech.fw.download")}</button>
                )}
              </div>
            </div>
          );
        })}
      </div>
      {error && <p role="alert" className="mt-3 text-xs text-red-400">{error}</p>}
    </div>
  );
}
