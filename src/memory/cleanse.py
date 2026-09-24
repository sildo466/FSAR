# SPDX-License-Identifier: MIT
"""Character-summary helper shared by the memory injection path.

Candidates are produced in src/memory/candidates.py and filtered by the judge in
src/memory/judge.py; this module only owns the character description that both
the persona judge and the prompt builder need.
"""

from __future__ import annotations

from typing import Any


def _character_summary(character: Any) -> str:
    return (
        f"Name: {character.name}\n"
        f"Description: {character.description}\n"
        f"Personality: {character.personality}\n"
        f"Scenario: {getattr(character, 'scenario', '')}"
    )
