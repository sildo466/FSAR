# core — shared agent infrastructure

> Language: [中文](core.md) | English · Back to [module index](README.en.md)

Agent-loop building blocks shared by the CLI and GUI: prompts, persona assembly, capability tiers, runtime state.

| File | Description |
|---|---|
| `agent_tiers.py` | `TierProfile` and `TIER_ORDER = (low, medium, high, xhigh, max, ultra)`; `get_tier_profile()` gives each tier's max tool turns, subagents, reflection, verification, and compaction threshold. |
| `agent_runtime.py` | Ephemeral per-run state: `AgentRecord`, `AgentRunState`, `AgentLoopResult`. |
| `prompts.py` | Shared system prompts (single source for CLI/GUI), including scripted MCP/skill install workflows. |
| `persona.py` | Assembles the `[CHARACTER CARD] / [EXAMPLE DIALOGUES] / [USER CARD] / [EMOTION STATE]` prefix block. |
| `strategy_injector.py` | Synthesises the `## Learned Strategies` block. |
| `experience_injector.py` | Builds the `## Experiences` index block. |
| `context_compaction.py` | Structure-aware context compaction for long tasks. |
| `event_bus.py` | In-process event bus (`EventType` enum); the scheduler emits through it. |
| `formula_engine.py` | Safe arithmetic evaluator for character-card emotion formulas (only `+ - * /`, numbers, variables, parens; clamped). |
| `time_context.py` | Renders real-world time as prompt context: the date, how long the user was away, and the age of recalled memories. Pure functions — `now` is always passed in, never read from the clock. |
| `birthday.py` | Birthday trigger decisions and the letter the app writes in its own voice. Pure functions and static text; `server/birthday_runner.py` performs the effects. |
