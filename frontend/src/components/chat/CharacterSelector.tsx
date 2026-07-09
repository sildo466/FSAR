// SPDX-License-Identifier: Apache-2.0
import { useEffect } from "react";
import { useCardsStore } from "../../stores/cards";
import { useSessions } from "../../stores/sessions";

export function CharacterSelector({ sessionId }: { sessionId: string }) {
  const characters = useCardsStore((s) => s.characters);
  const refresh = useCardsStore((s) => s.refresh);
  const setSessionCharacter = useCardsStore((s) => s.setSessionCharacter);

  useEffect(() => {
    if (characters.length === 0) refresh();
  }, [characters.length, refresh]);

  const send = useSessions((s) => s.send);
  const onChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const cid = Number(e.target.value);
    if (cid && sessionId) {
      setSessionCharacter(sessionId, cid).then(() => send({ type: "conversation.history", conversation_id: sessionId }));
    }
  };

  const current = characters.find((c) => c.is_default === 1) ?? characters[0];
  return (
    <select value={current?.id ?? ""} onChange={onChange} aria-label="character">
      {characters.map((c) => (
        <option key={c.id} value={c.id}>
          {c.name}{c.is_default === 1 ? " (default)" : ""}
        </option>
      ))}
    </select>
  );
}
