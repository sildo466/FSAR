// SPDX-License-Identifier: Apache-2.0
import { useCardsStore } from "../../stores/cards";
import { useWS } from "../../stores/ws";

export function UserSelector() {
  const userCards = useCardsStore((s) => s.userCards);
  const send = useWS((s) => s.send);

  if (userCards.length === 0) return null

  const current = userCards.find((u) => u.is_default === 1) ?? userCards[0]

  const onChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const id = Number(e.target.value)
    if (!id) return
    send({ type: "card.set_default", kind: "user", id })
  }

  return (
    <select
      value={current.id}
      onChange={onChange}
      aria-label="user"
      data-testid="user-selector"
      className="glass h-9 max-w-[130px] rounded-full px-3 text-[11px] font-mono text-text outline-none transition focus:ring-2 focus:ring-[var(--glow-faint)]"
    >
      {userCards.map((u) => (
        <option key={u.id} value={u.id}>
          {u.name}{u.is_default === 1 ? " (default)" : ""}
        </option>
      ))}
    </select>
  )
}
