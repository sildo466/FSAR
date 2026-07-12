// SPDX-License-Identifier: Apache-2.0
import { useEffect } from "react";
import { useCardsStore } from "../../stores/cards";

export function CharacterSelector({ sessionId }: { sessionId: string }) {
  const characters = useCardsStore((s) => s.characters);
  const refresh = useCardsStore((s) => s.refresh);
  const sessionCharacters = useCardsStore((s) => s.sessionCharacters);
  const draftCharacterId = useCardsStore((s) => s.draftCharacterId);
  const loadSessionCharacter = useCardsStore((s) => s.loadSessionCharacter);
  const setSessionCharacter = useCardsStore((s) => s.setSessionCharacter);
  const setDraftCharacter = useCardsStore((s) => s.setDraftCharacter);

  useEffect(() => {
    if (characters.length === 0) refresh();
  }, [characters.length, refresh]);

  useEffect(() => {
    if (sessionId) loadSessionCharacter(sessionId);
  }, [sessionId, loadSessionCharacter]);

  const onChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const cid = Number(e.target.value);
    if (!cid) return;
    if (sessionId) setSessionCharacter(sessionId, cid);
    else setDraftCharacter(cid);
  };

  const currentId =
    (sessionId ? sessionCharacters[sessionId] : draftCharacterId) ??
    characters.find((c) => c.is_default === 1)?.id ??
    characters[0]?.id ??
    "";
  return (
    <select
      value={currentId}
      onChange={onChange}
      aria-label="character"
      className="glass h-9 max-w-[150px] rounded-full px-3 text-[11px] font-mono text-text outline-none transition focus:ring-2 focus:ring-[var(--glow-faint)]"
    >
      {characters.map((c) => (
        <option key={c.id} value={c.id}>
          {c.name}{c.is_default === 1 ? " (default)" : ""}
        </option>
      ))}
    </select>
  );
}
