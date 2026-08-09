import { useEffect } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useWS } from "../../../stores/ws";
import { useSocialStore } from "../../../stores/social";
import { FeishuPanel, type FeishuConfig } from "./FeishuPanel";
import { TelegramPanel, type TelegramConfig } from "./TelegramPanel";
import { WeChatPanel, type WeChatConfig } from "./WeChatPanel";

function section(config: Record<string, unknown> | null, platform: string) {
  const social = (config?.social ?? {}) as Record<string, unknown>;
  return (social[platform] ?? {}) as Record<string, unknown>;
}

export function ChannelsTab() {
  const { t } = useTranslation();
  const config = useWS((state) => state.config);
  const refresh = useSocialStore((state) => state.refresh);
  const loading = useSocialStore((state) => state.loading);
  const error = useSocialStore((state) => state.error);
  const telegramRaw = section(config, "telegram");
  const feishuRaw = section(config, "feishu");
  const wechatRaw = section(config, "wechat");
  const telegram: TelegramConfig = {
    enabled: telegramRaw.enabled === true,
    bot_token: String(telegramRaw.bot_token ?? ""),
  };
  const feishu: FeishuConfig = {
    enabled: feishuRaw.enabled === true,
    app_id: String(feishuRaw.app_id ?? ""),
    app_secret: String(feishuRaw.app_secret ?? ""),
    verification_token: String(feishuRaw.verification_token ?? ""),
    encrypt_key: String(feishuRaw.encrypt_key ?? ""),
  };
  const wechat: WeChatConfig = {
    enabled: wechatRaw.enabled === true,
    character_card_id:
      typeof wechatRaw.character_card_id === "number" ? wechatRaw.character_card_id : null,
    user_card_id:
      typeof wechatRaw.user_card_id === "number" ? wechatRaw.user_card_id : null,
  };

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 5000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  return (
    <div>
      <div className="mb-5 flex min-h-8 items-center justify-between gap-4">
        <h2 className="font-display text-sm font-semibold">{t("settings.channels")}</h2>
        <button
          type="button"
          onClick={() => void refresh()}
          disabled={loading}
          className="flex h-8 w-8 items-center justify-center rounded-full text-text-muted hover:bg-surface hover:text-text disabled:opacity-40"
          title={t("channels.refreshTitle")}
          aria-label={t("channels.refreshTitle")}
        >
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
        </button>
      </div>
      {error && (
        <div className="mb-4 flex items-center gap-2 text-[10px] text-warning">
          <AlertTriangle size={12} /> {error}
        </div>
      )}
      <div>
        <TelegramPanel config={telegram} />
        <FeishuPanel config={feishu} />
        <WeChatPanel config={wechat} />
      </div>
    </div>
  );
}
