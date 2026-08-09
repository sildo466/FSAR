import { useEffect, useState } from "react";
import { PanelsTopLeft } from "lucide-react";
import { useTranslation } from "react-i18next";
import { patchSocial } from "../../../clients/socialClient";
import { useSocialStore } from "../../../stores/social";
import { ChannelSection, TextField } from "./ChannelPrimitives";

export type FeishuConfig = {
  enabled: boolean;
  app_id: string;
  app_secret: string;
  verification_token: string;
  encrypt_key: string;
};

export function FeishuPanel({ config }: { config: FeishuConfig }) {
  const { t } = useTranslation();
  const status = useSocialStore((state) => state.statuses.feishu);
  const refresh = useSocialStore((state) => state.refresh);
  const [draft, setDraft] = useState(config);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setDraft({
      enabled: config.enabled,
      app_id: config.app_id,
      app_secret: config.app_secret,
      verification_token: config.verification_token,
      encrypt_key: config.encrypt_key,
    });
  }, [
    config.enabled,
    config.app_id,
    config.app_secret,
    config.verification_token,
    config.encrypt_key,
  ]);
  const dirty = JSON.stringify(draft) !== JSON.stringify(config);
  const update = (key: keyof FeishuConfig, value: string | boolean) => {
    setDraft((current) => ({ ...current, [key]: value }));
  };
  const save = async () => {
    setSaving(true);
    setError("");
    try {
      await patchSocial({
        "social.feishu.enabled": draft.enabled,
        "social.feishu.app_id": draft.app_id,
        "social.feishu.app_secret": draft.app_secret,
        "social.feishu.verification_token": draft.verification_token,
        "social.feishu.encrypt_key": draft.encrypt_key,
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
      name={t("channels.feishu.name")}
      icon={<PanelsTopLeft size={15} />}
      status={status}
      enabled={draft.enabled}
      onEnabledChange={(value) => update("enabled", value)}
      onSave={() => void save()}
      saving={saving}
      dirty={dirty}
      error={error}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <TextField label={t("channels.feishu.appId")} value={draft.app_id} onChange={(value) => update("app_id", value)} placeholder="cli_..." />
        <TextField label={t("channels.feishu.appSecret")} value={draft.app_secret} onChange={(value) => update("app_secret", value)} secret />
        <TextField label={t("channels.feishu.verificationToken")} value={draft.verification_token} onChange={(value) => update("verification_token", value)} secret />
        <TextField label={t("channels.feishu.encryptKey")} value={draft.encrypt_key} onChange={(value) => update("encrypt_key", value)} secret />
      </div>
    </ChannelSection>
  );
}
