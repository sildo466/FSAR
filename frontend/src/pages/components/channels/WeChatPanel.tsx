import { useEffect, useState } from "react";
import { Loader2, MessageCircleMore, QrCode, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import { beginWechatQr, checkWechatQr, patchSocial, resetWechatQr } from "../../../clients/socialClient";
import { useCardsStore } from "../../../stores/cards";
import { useSocialStore } from "../../../stores/social";
import { ChannelSection } from "./ChannelPrimitives";

export type WeChatConfig = {
  enabled: boolean;
  character_card_id: number | null;
  user_card_id: number | null;
};

export function WeChatPanel({ config }: { config: WeChatConfig }) {
  const { t } = useTranslation();
  const status = useSocialStore((state) => state.statuses.wechat);
  const refresh = useSocialStore((state) => state.refresh);
  const characters = useCardsStore((state) => state.characters);
  const userCards = useCardsStore((state) => state.userCards);
  const cardsReady = useCardsStore((state) => state.characters.length + state.userCards.length > 0);
  const cardsRefresh = useCardsStore((state) => state.refresh);
  const [enabled, setEnabled] = useState(config.enabled);
  const [characterId, setCharacterId] = useState<number | null>(config.character_card_id);
  const [userCardId, setUserCardId] = useState<number | null>(config.user_card_id);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [qrImage, setQrImage] = useState("");
  const [qrStatus, setQrStatus] = useState("");
  const [startingQr, setStartingQr] = useState(false);

  useEffect(() => setEnabled(config.enabled), [config.enabled]);
  useEffect(() => setCharacterId(config.character_card_id), [config.character_card_id]);
  useEffect(() => setUserCardId(config.user_card_id), [config.user_card_id]);
  useEffect(() => {
    if (!cardsReady) cardsRefresh();
  }, [cardsReady, cardsRefresh]);

  useEffect(() => {
    if (!qrImage) return;
    const timer = window.setInterval(async () => {
      try {
        const result = await checkWechatQr();
        setQrStatus(result.status);
        if (result.status === "confirmed") {
          window.clearInterval(timer);
          setQrImage("");
          await refresh();
        } else if (result.status === "expired") {
          window.clearInterval(timer);
          setError(t("channels.wechat.qrExpired"));
          setQrImage("");
        }
      } catch (pollError) {
        window.clearInterval(timer);
        setError(pollError instanceof Error ? pollError.message : t("channels.wechat.qrStatusFailed"));
      }
    }, 1500);
    return () => window.clearInterval(timer);
  }, [qrImage, refresh]);

  const dirty =
    enabled !== config.enabled ||
    characterId !== config.character_card_id ||
    userCardId !== config.user_card_id;
  const save = async () => {
    setSaving(true);
    setError("");
    try {
      await patchSocial({
        "social.wechat.enabled": enabled,
        "social.wechat.character_card_id": characterId,
        "social.wechat.user_card_id": userCardId,
      });
      window.setTimeout(() => void refresh(), 400);
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : t("channels.saveFailed"));
    } finally {
      setSaving(false);
    }
  };
  const runQr = async (begin: () => Promise<{ scan_data: string }>) => {
    setStartingQr(true);
    setError("");
    setQrStatus("wait");
    try {
      const { default: QRCode } = await import("qrcode");
      const result = await begin();
      setQrImage(await QRCode.toDataURL(result.scan_data, {
        width: 224,
        margin: 2,
        color: { dark: "#111111", light: "#ffffff" },
      }));
    } catch (qrError) {
      setError(qrError instanceof Error ? qrError.message : t("channels.wechat.qrLoginFailed"));
      setQrStatus("");
    } finally {
      setStartingQr(false);
    }
  };
  const startQr = () => runQr(beginWechatQr);
  const rescanQr = () => runQr(resetWechatQr);

  return (
    <ChannelSection
      name={t("channels.wechat.name")}
      icon={<MessageCircleMore size={15} />}
      status={status}
      enabled={enabled}
      onEnabledChange={setEnabled}
      onSave={() => void save()}
      saving={saving}
      dirty={dirty}
      error={error}
    >
      <div className="flex min-h-9 flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => void startQr()}
          disabled={startingQr || status.state === "running"}
          className="flex h-8 items-center gap-1.5 rounded-lg border border-border px-3 text-[11px] hover:bg-surface disabled:cursor-not-allowed disabled:opacity-35"
        >
          {startingQr ? <Loader2 size={12} className="animate-spin" /> : <QrCode size={12} />}
          {startingQr ? t("channels.wechat.starting") : t("channels.wechat.scanQr")}
        </button>
        {status.state === "running" && (
          <button
            type="button"
            onClick={() => void rescanQr()}
            disabled={startingQr}
            className="flex h-8 items-center gap-1.5 rounded-lg border border-border px-3 text-[11px] hover:bg-surface disabled:cursor-not-allowed disabled:opacity-35"
          >
            {startingQr ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
            {startingQr ? t("channels.wechat.starting") : t("channels.wechat.rescan")}
          </button>
        )}
        {status.account_id && <span className="font-mono text-[10px] text-text-muted">{status.account_id}</span>}
        {qrStatus && qrStatus !== "confirmed" && (
          <span className="text-[10px] text-text-muted">{qrStatus === "scaned" ? t("channels.wechat.confirmInWechat") : t("channels.wechat.waitingForScan")}</span>
        )}
      </div>
      <div className="mt-3 flex flex-wrap gap-3">
        <label className="flex flex-col gap-1 text-[10px] uppercase tracking-wide text-text-muted">
          {t("channels.wechat.characterCard")}
          <select
            value={characterId == null ? "" : String(characterId)}
            onChange={(event) =>
              setCharacterId(event.target.value === "" ? null : Number(event.target.value))
            }
            className="h-8 rounded-md border border-border bg-surface px-2 text-[12px] text-text"
          >
            <option value="">{t("channels.wechat.serverDefault")}</option>
            {characters.map((card) => (
              <option key={card.id} value={card.id}>
                {card.name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-[10px] uppercase tracking-wide text-text-muted">
          {t("channels.wechat.userCard")}
          <select
            value={userCardId == null ? "" : String(userCardId)}
            onChange={(event) =>
              setUserCardId(event.target.value === "" ? null : Number(event.target.value))
            }
            className="h-8 rounded-md border border-border bg-surface px-2 text-[12px] text-text"
          >
            <option value="">{t("channels.wechat.serverDefault")}</option>
            {userCards.map((card) => (
              <option key={card.id} value={card.id}>
                {card.name}
              </option>
            ))}
          </select>
        </label>
      </div>
      {qrImage && (
        <div className="mt-3 w-fit rounded-lg border border-border bg-white p-2">
          <img src={qrImage} alt="WeChat login QR code" className="block h-48 w-48" />
        </div>
      )}
    </ChannelSection>
  );
}
