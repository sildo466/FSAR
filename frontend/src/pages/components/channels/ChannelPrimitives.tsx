import { type ReactNode, useState } from "react";
import { Eye, EyeOff, Loader2, Save } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { PlatformStatus } from "../../../clients/socialClient";

export function ChannelSection({
  name,
  icon,
  status,
  enabled,
  onEnabledChange,
  children,
  onSave,
  saving,
  dirty,
  error,
}: {
  name: string;
  icon: ReactNode;
  status: PlatformStatus;
  enabled: boolean;
  onEnabledChange: (enabled: boolean) => void;
  children: ReactNode;
  onSave: () => void;
  saving: boolean;
  dirty: boolean;
  error: string;
}) {
  const { t } = useTranslation();
  const running = status.state === "running";
  return (
    <section className="border-b border-border py-5 last:border-b-0 last:pb-0 first:pt-0">
      <div className="flex min-h-9 items-center gap-3">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border bg-bg text-text-muted">
          {icon}
        </span>
        <div className="min-w-0 flex-1">
          <h3 className="text-[13px] font-semibold">{name}</h3>
          <div className="mt-0.5 flex items-center gap-1.5 text-[10px] text-text-muted">
            <span className={`h-1.5 w-1.5 rounded-full ${running ? "bg-success" : status.state === "paused" ? "bg-warning" : "bg-text-faint"}`} />
            <span>{running ? t("channels.status.running") : status.state === "paused" ? t("channels.status.paused") : t("channels.status.unknown")}</span>
          </div>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={enabled}
          aria-label={`${enabled ? t("channels.disable") : t("channels.enable")} ${name}`}
          onClick={() => onEnabledChange(!enabled)}
          className={`relative h-5 w-9 shrink-0 rounded-full border transition-colors ${enabled ? "border-success/60 bg-success/25" : "border-border bg-surface"}`}
        >
          <span className={`absolute top-[3px] h-3 w-3 rounded-full transition-transform ${enabled ? "translate-x-[19px] bg-success" : "translate-x-[3px] bg-text-muted"}`} />
        </button>
      </div>

      <div className="ml-11 mt-4">
        {children}
        <div className="mt-4 flex min-h-8 items-center gap-3">
          <button
            type="button"
            onClick={onSave}
            disabled={!dirty || saving}
            className="flex h-8 items-center gap-1.5 rounded-lg bg-text px-3 text-[11px] font-medium text-bg disabled:cursor-not-allowed disabled:opacity-35"
          >
            {saving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
            {saving ? t("channels.saving") : t("common.save")}
          </button>
          {error && <span role="alert" className="min-w-0 text-[10px] text-danger">{error}</span>}
        </div>
      </div>
    </section>
  );
}

export function TextField({
  label,
  value,
  onChange,
  secret = false,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  secret?: boolean;
  placeholder?: string;
}) {
  const { t } = useTranslation();
  const [visible, setVisible] = useState(false);
  return (
    <label className="block min-w-0 text-[10px] text-text-muted">
      <span className="font-mono">{label}</span>
      <span className="relative mt-1 block">
        <input
          type={secret && !visible ? "password" : "text"}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          autoComplete="off"
          className="h-9 w-full border border-border bg-bg/60 px-3 pr-9 font-mono text-[11px] text-text outline-none focus:border-border-strong"
        />
        {secret && (
          <button
            type="button"
            onClick={() => setVisible((current) => !current)}
            className="absolute right-1 top-1 flex h-7 w-7 items-center justify-center rounded-full text-text-muted hover:bg-surface hover:text-text"
            title={visible ? t("channels.hideValue") : t("channels.showValue")}
            aria-label={visible ? t("channels.hideValue") : t("channels.showValue")}
          >
            {visible ? <EyeOff size={13} /> : <Eye size={13} />}
          </button>
        )}
      </span>
    </label>
  );
}
