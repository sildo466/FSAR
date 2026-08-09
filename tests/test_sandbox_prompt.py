from src.core.prompts import build_system_prompt
from src.memory.cards import CharacterCard


def test_workspace_context_is_included():
    character = CharacterCard(
        id=1, name="Assistant", description="Helpful", personality="Calm",
        scenario="", example_dialogues=[], tags=[], is_default=1,
        created_by="user", created_at="", updated_at="",
    )
    prompt = build_system_prompt(
        mode="agent", character=character, user_card=None,
        workspace_context="[SANDBOX CONTEXT]\nRoot: C:/workspace",
    )
    assert "[SANDBOX CONTEXT]" in prompt
    assert "Root: C:/workspace" in prompt
