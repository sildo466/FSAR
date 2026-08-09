from __future__ import annotations

import unittest

from src.core.context_compaction import (
    CHECKPOINT_MARKER,
    compact_context,
)


class ContextCompactionTests(unittest.IsolatedAsyncioTestCase):
    async def test_compaction_preserves_recent_tool_pair_and_identifiers(self) -> None:
        seen: list[list[dict[str, str]]] = []

        async def summarize(
            transcript: list[dict[str, str]], previous: str | None,
        ) -> str:
            seen.append(transcript)
            flattened = "\n".join(item["content"] for item in transcript)
            self.assertIn("C:\\work\\artifact-6f82.txt", flattened)
            return (
                "## Goal\nShip artifact-6f82\n"
                "## Completed\nInspected C:\\work\\artifact-6f82.txt\n"
                "## Active State\nContinuing\n"
                "## Decisions and Constraints\nKeep ID 550e8400-e29b-41d4-a716-446655440000\n"
                "## Artifacts and Exact Identifiers\nC:\\work\\artifact-6f82.txt\n"
                "## Verification\nPending\n"
                "## Open Actions\nRun checks"
            )

        messages = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "old request " * 30},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "old-call", "function": {"name": "read"}}],
            },
            {
                "role": "tool",
                "tool_call_id": "old-call",
                "content": "C:\\work\\artifact-6f82.txt " * 20,
            },
            {"role": "assistant", "content": "old analysis " * 30},
            {"role": "user", "content": "new request"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "new-call", "function": {"name": "verify"}}],
            },
            {"role": "tool", "tool_call_id": "new-call", "content": "verified"},
            {"role": "assistant", "content": "recent analysis"},
            {"role": "user", "content": "latest request"},
        ]
        compacted, changed = await compact_context(
            messages,
            context_window=500,
            max_output=40,
            threshold=0.45,
            summarize=summarize,
        )

        self.assertTrue(changed)
        self.assertTrue(seen)
        self.assertEqual(compacted[0], messages[0])
        self.assertTrue(compacted[1]["content"].startswith(CHECKPOINT_MARKER))
        self.assertIn("550e8400-e29b-41d4-a716-446655440000", compacted[1]["content"])
        recent_assistant = next(
            item for item in compacted
            if isinstance(item, dict) and item.get("tool_calls")
        )
        recent_result = next(
            item for item in compacted
            if isinstance(item, dict) and item.get("role") == "tool"
        )
        self.assertEqual(recent_assistant["tool_calls"][0]["id"], "new-call")
        self.assertEqual(recent_result["tool_call_id"], "new-call")
        self.assertEqual(compacted[-1]["content"], "latest request")

    async def test_failed_summary_keeps_original_history(self) -> None:
        async def fail(
            transcript: list[dict[str, str]], previous: str | None,
        ) -> str:
            raise RuntimeError("summary unavailable")

        messages = [
            {"role": "system", "content": "system"},
            *(
                {"role": "user" if index % 2 == 0 else "assistant", "content": "x" * 200}
                for index in range(10)
            ),
        ]
        result, changed = await compact_context(
            messages,
            context_window=300,
            max_output=30,
            threshold=0.5,
            summarize=fail,
        )
        self.assertFalse(changed)
        self.assertIs(result, messages)

    async def test_small_context_is_untouched(self) -> None:
        async def should_not_run(
            transcript: list[dict[str, str]], previous: str | None,
        ) -> str:
            self.fail("summarizer should not run")

        messages = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "hello"},
        ]
        result, changed = await compact_context(
            messages,
            context_window=1000,
            max_output=100,
            threshold=0.75,
            summarize=should_not_run,
        )
        self.assertFalse(changed)
        self.assertIs(result, messages)


if __name__ == "__main__":
    unittest.main()
