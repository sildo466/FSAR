"""FSAR edit tool — precise text replacement in files."""

from __future__ import annotations

from pathlib import Path

from src.tools.registry import Tool
from src.utils.logger import logger


class EditTool(Tool):
    """Edit files with precise text replacements."""

    @property
    def name(self) -> str:
        return "edit"

    @property
    def description(self) -> str:
        return "Edit a file by replacing exact text. Provide old_text (exact match) and new_text (replacement)."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to edit",
                },
                "old_text": {
                    "type": "string",
                    "description": "Exact text to find and replace (must be unique in file)",
                },
                "new_text": {
                    "type": "string",
                    "description": "Replacement text",
                },
                "replace_all": {
                    "type": "boolean",
                    "default": False,
                    "description": "Replace all occurrences (default: false, must match exactly once)",
                },
            },
            "required": ["file_path", "old_text", "new_text"],
        }

    @property
    def risk_level(self) -> str:
        return "MEDIUM"

    async def execute(self, file_path: str, old_text: str, new_text: str,
                      replace_all: bool = False, **kwargs) -> str:
        """Edit a file by replacing text."""
        try:
            path = Path(file_path)
            if not path.exists():
                return f"Error: File not found: {file_path}"

            content = path.read_text(encoding="utf-8", errors="replace")

            # Check if old_text exists
            count = content.count(old_text)
            if count == 0:
                # Try to give helpful hint
                lines = content.split("\n")
                old_lines = old_text.strip().split("\n")
                if len(old_lines) > 0:
                    first_line = old_lines[0].strip()
                    for i, line in enumerate(lines, 1):
                        if first_line in line:
                            return f"Error: Text not found exactly. Closest match at line {i}: {line.strip()[:80]}"
                return f"Error: Text not found in {file_path}"

            if not replace_all and count > 1:
                return f"Error: Found {count} matches. Set replace_all=true or provide more context to make it unique."

            # Perform replacement
            if replace_all:
                new_content = content.replace(old_text, new_text)
            else:
                new_content = content.replace(old_text, new_text, 1)

            path.write_text(new_content, encoding="utf-8")

            replaced = count if replace_all else 1
            logger.info(f"Edited {file_path}: replaced {replaced} occurrence(s)")
            return f"Replaced {replaced} occurrence(s) in {file_path}"

        except Exception as e:
            logger.error(f"Edit failed: {e}")
            return f"Error: {e}"
