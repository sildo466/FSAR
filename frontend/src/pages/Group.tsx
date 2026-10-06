// SPDX-License-Identifier: MIT
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Pin, Plus, Trash2 } from "lucide-react";
import { useGroup } from "../stores/group";
import { useCardsStore } from "../stores/cards";
import { Avatar } from "../components/ui/Avatar";
import { CreateRoomModal } from "../components/group/CreateRoomModal";

export function Group() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const rooms = useGroup((s) => s.rooms);
  const createRoom = useGroup((s) => s.createRoom);
  const deleteRoom = useGroup((s) => s.deleteRoom);
  const updateRoom = useGroup((s) => s.updateRoom);
  const characters = useCardsStore((s) => s.characters);
  const [creating, setCreating] = useState(false);
  const [confirmId, setConfirmId] = useState<number | null>(null);

  const cardOf = (id: number) => characters.find((c) => c.id === id);
  const nameOf = (id: number) =>
    cardOf(id)?.name ?? t("group.unknownMember");

  return (
    <div className="mx-auto max-w-[900px] px-4 py-6 sm:px-8">
      <div className="mb-5 flex items-center justify-between">
        <h1 className="font-display text-lg tracking-[0.06em] text-text">
          {t("group.title")}
        </h1>
        <button
          data-testid="new-room"
          onClick={() => setCreating(true)}
          className="flex items-center gap-1.5 rounded-full bg-[var(--button-bg)] px-4 py-2 text-xs text-[var(--button-text)] transition hover:scale-[1.03]"
        >
          <Plus size={14} strokeWidth={1.8} />
          {t("group.createTitle")}
        </button>
      </div>

      {rooms.length === 0 && (
        <p className="text-sm text-text-muted">{t("group.empty")}</p>
      )}

      <div className="flex flex-col gap-3">
        {rooms.map((room) => (
          <div
            key={room.id}
            data-testid={`room-card-${room.id}`}
            className="glass flex items-center gap-3 rounded-2xl px-4 py-3"
          >
            <button
              className="flex min-w-0 flex-1 items-center gap-3 text-left"
              onClick={() => navigate(`/group/${room.id}`)}
            >
              <div className="flex shrink-0 -space-x-2">
                {room.members.slice(0, 3).map((cid) => (
                  <Avatar
                    key={cid}
                    name={nameOf(cid)}
                    avatarPath={cardOf(cid)?.avatar_path}
                    cardId={cid}
                    size={32}
                  />
                ))}
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-1.5">
                  {room.pinned && (
                    <Pin size={12} className="text-text-faint" strokeWidth={1.8} />
                  )}
                  <span className="truncate text-sm font-medium text-text">
                    {room.name}
                  </span>
                  <span className="shrink-0 font-mono text-[10px] text-text-faint">
                    {t("group.memberCount", { count: room.members.length })}
                  </span>
                </div>
                {room.description && (
                  <div className="truncate text-[12px] text-text-muted">
                    {room.description}
                  </div>
                )}
              </div>
            </button>
            <button
              title={t("group.pin")}
              data-testid={`room-pin-${room.id}`}
              onClick={() => updateRoom(room.id, { pinned: !room.pinned })}
              className="rounded-full p-2 text-text-muted transition hover:bg-glass hover:text-text"
            >
              <Pin size={14} strokeWidth={1.6} />
            </button>
            <button
              title={t("group.delete")}
              data-testid={`room-delete-${room.id}`}
              onClick={() => setConfirmId(room.id)}
              className="rounded-full p-2 text-text-muted transition hover:bg-glass hover:text-danger"
            >
              <Trash2 size={14} strokeWidth={1.6} />
            </button>
          </div>
        ))}
      </div>

      {confirmId !== null && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-bg/70 p-4">
          <div className="glass w-full max-w-sm rounded-2xl p-5">
            <p className="mb-4 text-sm text-text">
              {t("group.deleteConfirm")}
            </p>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setConfirmId(null)}
                className="rounded-full px-4 py-2 text-xs text-text-muted hover:bg-glass hover:text-text"
              >
                {t("group.cancel")}
              </button>
              <button
                data-testid="confirm-room-delete"
                onClick={() => {
                  deleteRoom(confirmId);
                  setConfirmId(null);
                }}
                className="rounded-full bg-[var(--button-bg)] px-4 py-2 text-xs text-[var(--button-text)]"
              >
                {t("group.delete")}
              </button>
            </div>
          </div>
        </div>
      )}

      <CreateRoomModal
        open={creating}
        onClose={() => setCreating(false)}
        onSubmit={(payload) => {
          createRoom(payload);
          setCreating(false);
        }}
      />
    </div>
  );
}
