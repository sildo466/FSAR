# SPDX-License-Identifier: Apache-2.0
"""Persona block assembly — composes the prefix that goes before the system prompt.

Layout (per spec §5.4 / §6.1):
  [CHARACTER CARD]
  [EXAMPLE DIALOGUES]   (only if non-empty)
  [USER CARD]           (only if user_card is not None)
  [EMOTION STATE]       (only if emotion_state is non-empty)
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from src.memory.cards import CharacterCard, UserCard


@dataclass(frozen=True)
class PersonaBlock:
    text: str
    character_id: int | None
    user_card_id: int | None


class PersonaMissingError(Exception):
    """Raised when no character card is configured."""


def _character_section(c: CharacterCard) -> str:
    scenario = c.scenario or "(none)"
    return (
        "[CHARACTER CARD]\n"
        f"Name: {c.name}\n"
        f"Description: {c.description}\n"
        f"Personality: {c.personality}\n"
        f"Scenario: {scenario}\n"
    )


def _example_section(c: CharacterCard) -> str:
    if not c.example_dialogues:
        return ""
    lines = ["[EXAMPLE DIALOGUES]"]
    for d in c.example_dialogues:
        lines.append(f"user: {d.get('user', '')}")
        lines.append(f"assistant: {d.get('assistant', '')}")
    return "\n".join(lines) + "\n"


def _user_section(u: UserCard) -> str:
    style = u.communication_style or "(unspecified)"
    return (
        "[USER CARD]\n"
        f"You are talking to {u.name}.\n"
        f"About them: {u.description}\n"
        f"Their style: {style}\n"
        f"Known preferences: {json.dumps(u.preferences or {}, ensure_ascii=False)}\n"
        f"Known interests: {json.dumps(u.interests or [], ensure_ascii=False)}\n"
    )


def _emotion_section(c: CharacterCard) -> str:
    state = c.emotion_state or {}
    if not state:
        return ""
    lines = [
        "[EMOTION STATE]",
        f"Current emotional state of {c.name}:",
    ]
    schema = {m["key"]: m for m in (c.emotion_schema or [])}
    static_keys = {k for k, m in schema.items() if m.get("static")}
    for key, value in state.items():
        rng = schema.get(key, {})
        lo = rng.get("min", 0)
        hi = rng.get("max", 100)
        unit = f"/{lo}..{hi}" if lo < 0 else f"/{hi}"
        static_note = " (static; cannot be modified by you)" if key in static_keys else ""
        lines.append(f"- {key:<14} {value}{unit}  (stable){static_note}")
    lines.append("")
    lines.append("You can use the `update_emotion` tool to record emotional shifts you "
                 "feel during this conversation. Each call must include a `reason`.")
    return "\n".join(lines) + "\n"


def assemble_persona_block(
    character: CharacterCard | None,
    user_card: UserCard | None,
) -> PersonaBlock:
    if character is None:
        raise PersonaMissingError("no character card available")
    sections = [
        _character_section(character),
        _example_section(character),
    ]
    if user_card is not None:
        sections.append(_user_section(user_card))
    sections.append(_emotion_section(character))
    return PersonaBlock(
        text="".join(s for s in sections if s),
        character_id=character.id,
        user_card_id=user_card.id if user_card else None,
    )
