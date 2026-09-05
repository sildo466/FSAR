// SPDX-License-Identifier: MIT
import { useEffect, useState } from "react";
import { useWS } from "../stores/ws";
import type { EmotionState } from "../components/live/AvatarRenderer";

/**
 * Tracks the active character's numeric emotion layer (affection / trust /
 * mood / energy) from chat.done + card.emotion_state_updated events and
 * normalizes it for the avatar renderer.
 */
export function useLiveEmotion(characterId: number | null): EmotionState {
  const [state, setState] = useState<EmotionState>({});

  useEffect(() => {
    const client = useWS.getState().client;
    if (!client) return;
    return client.on((msg) => {
      if (msg.type === "chat.done" && msg.emotion_state) {
        setState(msg.emotion_state);
      } else if (msg.type === "card.emotion_state_updated") {
        setState(msg.state);
      }
    });
  }, [characterId]);

  return state;
}
