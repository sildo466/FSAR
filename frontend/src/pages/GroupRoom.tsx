// SPDX-License-Identifier: MIT
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Users } from "lucide-react";
import { useGroup } from "../stores/group";
import { useCardsStore } from "../stores/cards";
import { fetchWSToken } from "../stores/ws";
import { MessageList, type ChatMessage } from "../components/chat/MessageList";
import {
  ChatComposer,
  type ComposerAttachment,
} from "../components/chat/ChatComposer";
import { ThinkingDot } from "../components/chat/ThinkingDot";
import { ElectionStrip } from "../components/group/ElectionStrip";
import { MemberPanel } from "../components/group/MemberPanel";

export function GroupRoom() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const params = useParams();
  const roomId = Number(params.roomId);

  const rooms = useGroup((s) => s.rooms);
  const messages = useGroup((s) => s.messages[roomId] ?? []);
  const elections = useGroup((s) => s.elections[roomId] ?? []);
  const chainRunning = useGroup((s) => s.chainRunning[roomId] ?? false);
  const openRoom = useGroup((s) => s.openRoom);
  const closeRoom = useGroup((s) => s.closeRoom);
  const sendMsg = useGroup((s) => s.send);
  const rate = useGroup((s) => s.rate);
  const regenerate = useGroup((s) => s.regenerate);
  const characters = useCardsStore((s) => s.characters);
  const gauge = useGroup((s) => s.context[roomId]);

  const [input, setInput] = useState("");
  const [panelOpen, setPanelOpen] = useState(false);
  const [mentions, setMentions] = useState<number[]>([]);
  const [attachments, setAttachments] = useState<ComposerAttachment[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState(false);

  const room = useMemo(
    () => rooms.find((r) => r.id === roomId),
    [rooms, roomId]
  );
  const members = room?.members ?? [];

  useEffect(() => {
    if (Number.isNaN(roomId)) return;
    // React Router keeps this component mounted across a param change, so the
    // draft, mentions and attachments of the previous room would otherwise
    // follow the user into the next one.
    setInput("");
    setMentions([]);
    setAttachments([]);
    setUploadError(false);
    openRoom(roomId);
    return () => closeRoom();
  }, [roomId, openRoom, closeRoom]);

  // Mentions and attachments belong to one outgoing message, not to the room.
  useEffect(() => {
    if (!chainRunning) {
      setMentions([]);
      setAttachments([]);
    }
  }, [chainRunning]);

  const handlePickFiles = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setUploading(true);
    setUploadError(false);
    try {
      const form = new FormData();
      for (const file of Array.from(files).slice(0, 8)) form.append("files", file);
      const token = await fetchWSToken();
      const response = await fetch("/api/chat/upload", {
        method: "POST",
        credentials: "same-origin",
        headers: { Authorization: `Bearer ${token}` },
        body: form,
      });
      const payload = (await response.json().catch(() => ({}))) as {
        files?: Array<{ name: string; path: string; size: number }>;
      };
      if (!response.ok || !payload.files) throw new Error(`HTTP ${response.status}`);
      setAttachments((prev) => [...prev, ...payload.files!].slice(0, 8));
    } catch {
      setUploadError(true);
    } finally {
      setUploading(false);
    }
  };

  const send = () => {
    const content = input.trim();
    if (!content) return;
    sendMsg({
      type: "group.send",
      room_id: roomId,
      content,
      attached_files: attachments.length
        ? attachments.map((a) => a.path)
        : undefined,
      mentioned_character_ids: mentions.length ? mentions : undefined,
    });
    setInput("");
  };

  // MessageList speaks ChatMessage; group messages carry an extra row_id used
  // by regenerate, so map explicitly rather than sharing the type.
  const chatMessages: ChatMessage[] = useMemo(
    () =>
      messages.map((m) => ({
        id: m.id,
        role: m.role,
        content: m.content,
        streaming: m.streaming,
        thinking: m.thinking,
        character_id: m.character_id ?? undefined,
        character_name: m.character_name ?? undefined,
        user_name: m.user_name ?? undefined,
      })),
    [messages]
  );

  // The election runs before anyone is picked, so a "thinking" bubble with a
  // character's name would attribute speech to someone who may never answer.
  const waiting =
    chainRunning && !messages.some((m) => m.streaming || m.thinking);

  const rowIdOf = (messageId: string) =>
    messages.find((m) => m.id === messageId)?.row_id;

  return (
    <div className="flex h-full gap-3">
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="glass mb-3 flex items-center gap-2 rounded-2xl px-3 py-2">
          <button
            onClick={() => navigate("/group")}
            aria-label={t("group.title")}
            className="rounded-full p-1.5 text-text-muted transition hover:bg-glass hover:text-text"
          >
            <ArrowLeft size={15} strokeWidth={1.8} />
          </button>
          <span className="truncate text-sm font-medium text-text">
            {room?.name ?? ""}
          </span>
          <button
            data-testid="toggle-member-panel"
            onClick={() => setPanelOpen((v) => !v)}
            className="ml-auto flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[11px] text-text-muted transition hover:bg-glass hover:text-text"
          >
            <div className="flex -space-x-2">
              {members.slice(0, 3).map((cid) => {
                const c = characters.find((x) => x.id === cid);
                return (
                  <span
                    key={cid}
                    className="flex h-5 w-5 items-center justify-center rounded-full bg-surface-2 text-[9px] text-text"
                  >
                    {(c?.name ?? "?").slice(0, 1)}
                  </span>
                );
              })}
            </div>
            <Users size={13} strokeWidth={1.6} />
            {members.length}
          </button>
          {gauge && gauge.window > 0 && (
            <span
              data-testid="group-token-meter"
              title={`context: ${gauge.used.toLocaleString()} / ${gauge.window.toLocaleString()} tokens`}
              className="shrink-0 rounded-full border border-border/60 bg-[var(--chip-bg)] px-2.5 py-1 font-mono text-[10px] leading-none text-text-muted"
            >
              <span className="text-text">{gauge.used.toLocaleString()}</span>
              <span className="opacity-60">
                {" / "}
                {gauge.window.toLocaleString()} tk
              </span>
            </span>
          )}
        </header>

        <ElectionStrip candidates={elections} running={chainRunning} />

        <div className="min-h-0 flex-1 overflow-auto">
          <MessageList
            messages={chatMessages}
            pendingRisks={[]}
            onRespond={() => {}}
            onRate={(messageId, score, reason) => {
              const rowId = rowIdOf(messageId);
              if (rowId != null) rate(roomId, rowId, score, reason);
            }}
            onRegenerateMessage={(messageId) => {
              const rowId = rowIdOf(messageId);
              if (rowId != null) regenerate(roomId, rowId);
            }}
          />
        </div>

        {members.length > 0 && (
          <div className="flex flex-wrap gap-1.5 pt-2">
            {members.map((cid) => {
              const c = characters.find((x) => x.id === cid);
              const active = mentions.includes(cid);
              return (
                <button
                  key={cid}
                  data-testid={`mention-${cid}`}
                  onClick={() =>
                    setMentions((prev) =>
                      prev.includes(cid)
                        ? prev.filter((x) => x !== cid)
                        : [...prev, cid]
                    )
                  }
                  className={`rounded-full border px-2.5 py-1 text-[11px] transition ${
                    active
                      ? "border-border-strong bg-surface-2 text-text"
                      : "border-border text-text-muted hover:bg-glass"
                  }`}
                >
                  @{c?.name ?? t("group.unknownMember")}
                </button>
              );
            })}
          </div>
        )}

        {waiting && (
          <div
            data-testid="group-waiting"
            className="flex items-center gap-2 px-3 pt-2 text-[11px] text-text-muted"
          >
            <ThinkingDot />
            {t("group.waiting")}
          </div>
        )}

        <div className="pt-2">
          <ChatComposer
            value={input}
            onChange={setInput}
            onSend={send}
            onCancel={() => sendMsg({ type: "group.cancel", room_id: roomId })}
            busy={chainRunning}
            attachments={attachments}
            onPickFiles={(files) => void handlePickFiles(files)}
            onRemoveAttachment={(i) =>
              setAttachments((prev) => prev.filter((_, j) => j !== i))
            }
            uploadError={uploadError ? t("chat.uploadFailed") : undefined}
            uploading={uploading}
            placeholder={t("group.placeholderInput")}
          />
        </div>
      </div>

      {panelOpen && room && (
        <MemberPanel room={room} onClose={() => setPanelOpen(false)} />
      )}
    </div>
  );
}
