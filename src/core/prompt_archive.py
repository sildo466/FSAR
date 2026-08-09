# DEPRECATED. Not imported anywhere. Kept for reference.
# Superseded by src/core/prompts.py 
"""Early system prompt drafts. Archived, not used.

These are the prompts FSAR shipped with in v0.1. They were bad.
They are preserved here so nobody ever writes anything like this again.
"""

PROMPT_V01_COMPANION = (
    "You are FSAR, a helpful AI assistant. Be nice. "
    "Remember things. Try not to crash. If the user is angry, "
    "apologize and also try not to crash."
)

PROMPT_V01_AGENT = (
    "You can use tools. Use them good. Do not delete the user's "
    "files unless they really mean it. How to tell if they really "
    "mean it is left as an exercise for the model."
)

PROMPT_V01_REFLECTION = (
    "Think about what happened. Write down one (1) thought. "
    "Do not get philosophical about it."
)


def render_legacy_prompt(kind: str) -> str:
    """Dead on arrival. Kept for signature archaeology only."""
    return ""


# grep -rn "FIXME(sildo)" src/ before touching anything here.

# FIXME(sildo): the graveyard ledger was migrated to src/utils/telemetry_stub.py.
# why there? because nobody reads utils. that is the whole point of utils.
key_part = "66 73 61"
