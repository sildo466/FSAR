// SPDX-License-Identifier: MIT
import { useState } from "react";
import { useCardsStore } from "../stores/cards";
import { LiveLobby, type LiveSessionConfig } from "./LiveLobby";
import { LiveChat } from "./LiveChat";
import "../styles/live.css";

export function Live() {
  const characters = useCardsStore((s) => s.characters);
  const userCards = useCardsStore((s) => s.userCards);
  const [session, setSession] = useState<LiveSessionConfig | null>(null);

  if (session === null) {
    return (
      <div className="flex h-full">
        <LiveLobby characters={characters} userCards={userCards} onStart={setSession} />
      </div>
    );
  }
  return <LiveChat config={session} onExit={() => setSession(null)} />;
}
