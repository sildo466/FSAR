// SPDX-License-Identifier: MIT
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { X } from "lucide-react";
import type { RoomSummary } from "../../lib/ws-client";
import { useCardsStore } from "../../stores/cards";
import { useGroup } from "../../stores/group";

interface Props {
  room: RoomSummary;
  onClose: () => void;
}

export function MemberPanel({ room, onClose }: Props) {
  const { t } = useTranslation();
  const characters = useCardsStore((s) => s.characters);
  const userCards = useCardsStore((s) => s.userCards);
  const addMembers = useGroup((s) => s.addMembers);
  const removeMember = useGroup((s) => s.removeMember);
  const updateRoom = useGroup((s) => s.updateRoom);
  const [name, setName] = useState(room.name);
  const [description, setDescription] = useState(room.description);
  const [scenario, setScenario] = useState(room.scenario_prompt);

  const outsiders = characters.filter((c) => !room.members.includes(c.id));

  return (
    <aside className="glass flex h-full w-80 shrink-0 flex-col gap-4 overflow-y-auto rounded-2xl p-4">
      <div className="flex items-center justify-between">
        <span className="font-display text-xs tracking-[0.08em] text-text-muted">
          {t("group.settings")}
        </span>
        <button
          onClick={onClose}
          aria-label={t("group.cancel")}
          className="rounded-full p-1 text-text-muted transition hover:text-text"
        >
          <X size={14} strokeWidth={1.8} />
        </button>
      </div>

      <label className="text-[11px] text-text-muted" htmlFor="panel-name">
        {t("group.name")}
      </label>
      <input
        id="panel-name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        onBlur={() => updateRoom(room.id, { name: name.trim() })}
        className="rounded-xl border border-border bg-surface px-3 py-2 text-sm text-text outline-none"
      />

      <label className="text-[11px] text-text-muted" htmlFor="panel-desc">
        {t("group.description")}
      </label>
      <input
        id="panel-desc"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        onBlur={() => updateRoom(room.id, { description })}
        className="rounded-xl border border-border bg-surface px-3 py-2 text-sm text-text outline-none"
      />

      <label className="text-[11px] text-text-muted" htmlFor="panel-user">
        {t("group.me")}
      </label>
      <select
        id="panel-user"
        value={room.user_card_id ?? ""}
        onChange={(e) =>
          updateRoom(room.id, {
            user_card_id: e.target.value ? Number(e.target.value) : null,
          })
        }
        className="rounded-xl border border-border bg-surface px-3 py-2 text-sm text-text outline-none"
      >
        <option value="">{t("group.defaultUser")}</option>
        {userCards.map((u) => (
          <option key={u.id} value={u.id}>
            {u.name}
          </option>
        ))}
      </select>

      <label className="text-[11px] text-text-muted" htmlFor="panel-scene">
        {t("group.scenario")}
      </label>
      <textarea
        id="panel-scene"
        rows={4}
        value={scenario}
        onChange={(e) => setScenario(e.target.value)}
        onBlur={() => updateRoom(room.id, { scenario_prompt: scenario })}
        placeholder={t("group.scenarioPlaceholder")}
        className="resize-none rounded-xl border border-border bg-surface px-3 py-2 text-sm text-text outline-none"
      />

      <div className="text-[11px] text-text-muted">{t("group.members")}</div>
      <div className="flex flex-col gap-2">
        {room.members.map((cid) => {
          const character = characters.find((c) => c.id === cid);
          return (
            <div key={cid} className="flex items-center justify-between gap-2">
              <span className="truncate text-[12px] text-text">
                {character?.name ?? t("group.unknownMember")}
              </span>
              <button
                data-testid={`remove-member-${cid}`}
                onClick={() => removeMember(room.id, cid)}
                className="shrink-0 text-[11px] text-text-muted transition hover:text-danger"
              >
                {t("group.remove")}
              </button>
            </div>
          );
        })}
      </div>

      {outsiders.length > 0 && (
        <>
          <div className="text-[11px] text-text-muted">
            {t("group.addMembers")}
          </div>
          <div className="flex flex-wrap gap-2">
            {outsiders.map((c) => (
              <button
                key={c.id}
                data-testid={`add-member-${c.id}`}
                onClick={() => addMembers(room.id, [c.id])}
                className="rounded-full border border-border px-3 py-1 text-[11px] text-text-muted transition hover:bg-glass hover:text-text"
              >
                + {c.name}
              </button>
            ))}
          </div>
        </>
      )}
    </aside>
  );
}
