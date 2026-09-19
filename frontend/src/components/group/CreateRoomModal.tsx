// SPDX-License-Identifier: MIT
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useCardsStore } from "../../stores/cards";

interface Props {
  open: boolean;
  onClose: () => void;
  onSubmit: (payload: {
    name: string;
    description: string;
    scenario_prompt: string;
    user_card_id: number | null;
    character_ids: number[];
  }) => void;
}

export function CreateRoomModal({ open, onClose, onSubmit }: Props) {
  const { t } = useTranslation();
  const characters = useCardsStore((s) => s.characters);
  const userCards = useCardsStore((s) => s.userCards);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [scenario, setScenario] = useState("");
  const [userCardId, setUserCardId] = useState<number | null>(null);
  const [selected, setSelected] = useState<number[]>([]);

  if (!open) return null;

  const canSubmit = name.trim().length > 0 && selected.length > 0;

  const toggle = (id: number) =>
    setSelected((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );

  const submit = () => {
    if (!canSubmit) return;
    onSubmit({
      name: name.trim(),
      description,
      scenario_prompt: scenario,
      user_card_id: userCardId,
      character_ids: selected,
    });
    setName("");
    setDescription("");
    setScenario("");
    setSelected([]);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-bg/70 p-4">
      <div className="glass w-full max-w-lg overflow-y-auto rounded-2xl p-5">
        <h2 className="mb-4 text-sm font-medium text-text">
          {t("group.createTitle")}
        </h2>

        <label className="mb-1 block text-[11px] text-text-muted" htmlFor="room-name">
          {t("group.name")}
        </label>
        <input
          id="room-name"
          data-testid="create-room-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="mb-3 w-full rounded-xl border border-border bg-surface px-3 py-2 text-sm text-text outline-none"
        />

        <label className="mb-1 block text-[11px] text-text-muted" htmlFor="room-desc">
          {t("group.description")}
        </label>
        <input
          id="room-desc"
          data-testid="create-room-description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          className="mb-3 w-full rounded-xl border border-border bg-surface px-3 py-2 text-sm text-text outline-none"
        />

        <label className="mb-1 block text-[11px] text-text-muted" htmlFor="room-user">
          {t("group.me")}
        </label>
        <select
          id="room-user"
          value={userCardId ?? ""}
          onChange={(e) =>
            setUserCardId(e.target.value ? Number(e.target.value) : null)
          }
          className="mb-3 w-full rounded-xl border border-border bg-surface px-3 py-2 text-sm text-text outline-none"
        >
          <option value="">{t("group.defaultUser")}</option>
          {userCards.map((u) => (
            <option key={u.id} value={u.id}>
              {u.name}
            </option>
          ))}
        </select>

        <label className="mb-1 block text-[11px] text-text-muted" htmlFor="room-scene">
          {t("group.scenario")}
        </label>
        <textarea
          id="room-scene"
          data-testid="create-room-scenario"
          rows={3}
          value={scenario}
          onChange={(e) => setScenario(e.target.value)}
          placeholder={t("group.scenarioPlaceholder")}
          className="w-full resize-none rounded-xl border border-border bg-surface px-3 py-2 text-sm text-text outline-none"
        />
        <p className="mb-3 mt-1 text-[11px] text-text-faint">
          {t("group.scenarioHint")}
        </p>

        <div className="mb-1 text-[11px] text-text-muted">{t("group.members")}</div>
        <div className="mb-4 flex flex-wrap gap-2">
          {characters.map((c) => (
            <label
              key={c.id}
              className={`flex cursor-pointer items-center gap-1.5 rounded-full border px-3 py-1 text-[11px] ${
                selected.includes(c.id)
                  ? "border-border-strong bg-surface-2 text-text"
                  : "border-border text-text-muted"
              }`}
            >
              <input
                type="checkbox"
                aria-label={c.name}
                className="hidden"
                checked={selected.includes(c.id)}
                onChange={() => toggle(c.id)}
              />
              {c.name}
            </label>
          ))}
        </div>

        <div className="flex justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded-full px-4 py-2 text-xs text-text-muted hover:bg-glass hover:text-text"
          >
            {t("group.cancel")}
          </button>
          <button
            data-testid="create-room-submit"
            onClick={submit}
            disabled={!canSubmit}
            className="rounded-full bg-[var(--button-bg)] px-4 py-2 text-xs text-[var(--button-text)] disabled:opacity-50"
          >
            {t("group.create")}
          </button>
        </div>
      </div>
    </div>
  );
}
