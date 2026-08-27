// SPDX-License-Identifier: MIT
import { useState } from "react";
import { ModelPicker } from "../components/live/ModelPicker";
import type { CardSummary, UserCardSummary } from "../stores/cards";

export interface LiveSessionConfig {
  characterId: number | null;
  userCardId: number | null;
  model: string | null;
}

interface LiveLobbyProps {
  characters: CardSummary[];
  userCards: UserCardSummary[];
  onStart: (config: LiveSessionConfig) => void;
}

export function LiveLobby({ characters, userCards, onStart }: LiveLobbyProps) {
  const [characterId, setCharacterId] = useState<string>("");
  const [userId, setUserId] = useState<string>("");
  const [model, setModel] = useState<string | null>(null);

  const canStart = characterId !== "";

  return (
    <div className="mx-auto flex h-full max-w-md flex-col justify-center gap-6">
      <div className="flex flex-col gap-2">
        <label htmlFor="live-character" className="text-sm text-text-muted">
          Character
        </label>
        <select
          id="live-character"
          className="rounded-lg glass border border-border px-2 py-1 text-sm"
          value={characterId}
          onChange={(e) => setCharacterId(e.target.value)}
        >
          <option value="">Select…</option>
          {characters.map((c) => (
            <option key={c.id} value={String(c.id)}>
              {c.name}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-col gap-2">
        <label htmlFor="live-user" className="text-sm text-text-muted">
          User
        </label>
        <select
          id="live-user"
          className="rounded-lg glass border border-border px-2 py-1 text-sm"
          value={userId}
          onChange={(e) => setUserId(e.target.value)}
        >
          <option value="">Select…</option>
          {userCards.map((c) => (
            <option key={c.id} value={String(c.id)}>
              {c.name}
            </option>
          ))}
        </select>
      </div>

      <ModelPicker value={model} onSelect={setModel} />

      <button
        className="rounded-full bg-text px-5 py-2 text-sm font-semibold text-bg disabled:opacity-40"
        disabled={!canStart}
        onClick={() =>
          onStart({
            characterId: characterId ? Number(characterId) : null,
            userCardId: userId ? Number(userId) : null,
            model,
          })
        }
      >
        Start live session
      </button>
      <p className="text-xs text-text-faint">
        Put your VRM model in <code>data/models/</code> to make it appear here.
      </p>
    </div>
  );
}
