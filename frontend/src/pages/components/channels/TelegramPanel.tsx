import { useEffect, useState } from "react";
import { Send } from "lucide-react";
import { useTranslation } from "react-i18next";
import { patchSocial } from "../../../clients/socialClient";
import { useSocialStore } from "../../../stores/social";
import { ChannelSection, TextField } from "./ChannelPrimitives";

export type TelegramConfig = { enabled: boolean; bot_token: string };

export function TelegramPanel({ config }: { config: TelegramConfig }) {
  const { t } = useTranslation();
  const status = useSocialStore((state) => state.statuses.telegram);
  const refresh = useSocialStore((state) => state.refresh);
  const [enabled, setEnabled] = useState(config.enabled);
  const [token, setToken] = useState(config.bot_token);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setEnabled(config.enabled);
    setToken(config.bot_token);
  }, [config.enabled, config.bot_token]);

  const dirty = enabled !== config.enabled || token !== config.bot_token;
  const save = async () => {
    setSaving(true);
    setError("");
    try {
      await patchSocial({
        "social.telegram.enabled": enabled,
        "social.telegram.bot_token": token,
      });
      window.setTimeout(() => void refresh(), 400);
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : t("channels.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <ChannelSection
      name={t("channels.telegram.name")}
      icon={<Send size={15} />}
      status={status}
      enabled={enabled}
      onEnabledChange={setEnabled}
      onSave={() => void save()}
      saving={saving}
      dirty={dirty}
      error={error}
    >
      <TextField label={t("channels.telegram.botToken")} value={token} onChange={setToken} secret placeholder="123456:ABC..." />
    </ChannelSection>
  );
}
