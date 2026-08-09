"""FSAR file_ops tool — read/write/list/move/delete files."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Optional

from src.tools.registry import Tool
from src.sandbox.tool_guard import guard_path
from src.utils.logger import logger


class FileOpsTool(Tool):
    """File operations: read, write, list, move, delete."""

    @property
    def name(self) -> str:
        return "file_ops"

    @property
    def description(self) -> str:
        return "Perform file operations: read, write, list, move, or delete files/directories."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["read", "write", "list", "move", "delete", "mkdir"],
                    "description": "The operation to perform",
                },
                "path": {
                    "type": "string",
                    "description": "File or directory path",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write (for write operation)",
                },
                "destination": {
                    "type": "string",
                    "description": "Destination path (for move operation)",
                },
                "recursive": {
                    "type": "boolean",
                    "default": False,
                    "description": "Recursively list/delete directories",
                },
            },
            "required": ["operation", "path"],
        }

    @property
    def risk_level(self) -> str:
        return "MEDIUM"

    async def execute(self, operation: str = "", path: str = "", content: str = "",
                      destination: str = "", recursive: bool = False, **kwargs) -> str:
        """Execute a file operation."""
        if not operation:
            return "Error: operation is required"
        if not path:
            return "Error: path is required"
        blocked = await guard_path(self.name, operation, path, kwargs)
        if blocked:
            return blocked
        if operation == "move" and destination:
            blocked = await guard_path(self.name, "move", destination, kwargs)
            if blocked:
                return blocked
        try:
            file_path = Path(path)

            if operation == "read":
                return await self._read(file_path)
            elif operation == "write":
                return await self._write(file_path, content)
            elif operation == "list":
                return await self._list(file_path, recursive)
            elif operation == "move":
                return await self._move(file_path, Path(destination))
            elif operation == "delete":
                return await self._delete(file_path, recursive)
            elif operation == "mkdir":
                return await self._mkdir(file_path)
            else:
                return f"Error: Unknown operation '{operation}'"

        except Exception as e:
            logger.error(f"File operation failed: {e}")
            return f"Error: {e}"

    async def _read(self, path: Path) -> str:
        """Read file contents."""
        if not path.exists():
            return f"Error: File not found: {path}"
        if path.is_dir():
            return f"Error: Path is a directory: {path}. Use list operation."
        if path.stat().st_size > 1_000_000:  # 1MB limit
            return f"Error: File too large ({path.stat().st_size} bytes). Max 1MB."

        with path.open("rb") as f:
            sample = f.read(8192)
        if b"\x00" in sample:
            return f"Error: {path} appears to be a binary file ({len(sample)}-byte sample contains null bytes)."

        content = path.read_text(encoding="utf-8", errors="replace")
        return content if content else "(empty file)"

    async def _write(self, path: Path, content: str) -> str:
        """Write content to a file."""
        if path.exists() and path.is_dir():
            return f"Error: Cannot write to directory: {path}"

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        logger.info(f"Wrote {len(content)} bytes to {path}")
        return f"Successfully wrote {len(content)} bytes to {path}"

    async def _list(self, path: Path, recursive: bool = False) -> str:
        """List directory contents."""
        if not path.exists():
            return f"Error: Path not found: {path}"
        if path.is_file():
            stat = path.stat()
            return f"File: {path.name}\nSize: {stat.st_size} bytes\nModified: {stat.st_mtime}"

        entries = []
        if recursive:
            for item in path.rglob("*"):
                rel = item.relative_to(path)
                prefix = "[DIR] " if item.is_dir() else "      "
                entries.append(f"{prefix}{rel}")
        else:
            for item in sorted(path.iterdir()):
                if item.is_dir():
                    entries.append(f"[DIR] {item.name}/")
                else:
                    size = item.stat().st_size
                    entries.append(f"      {item.name} ({size} bytes)")

        if not entries:
            return f"Directory is empty: {path}"

        return f"Contents of {path}:\n" + "\n".join(entries)

    async def _move(self, source: Path, destination: Path) -> str:
        """Move or rename a file/directory."""
        if not source.exists():
            return f"Error: Source not found: {source}"

        if destination.exists() and destination.is_dir():
            destination = destination / source.name

        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
        logger.info(f"Moved {source} to {destination}")
        return f"Moved {source} to {destination}"

    async def _delete(self, path: Path, recursive: bool = False) -> str:
        """Delete a file or directory."""
        if not path.exists():
            return f"Error: Path not found: {path}"

        if path.is_dir():
            if recursive:
                shutil.rmtree(path)
                logger.info(f"Deleted directory recursively: {path}")
                return f"Deleted directory: {path}"
            else:
                try:
                    path.rmdir()
                    logger.info(f"Deleted directory: {path}")
                    return f"Deleted directory: {path}"
                except OSError:
                    return f"Error: Directory not empty: {path}. Use recursive=true."
        else:
            path.unlink()
            logger.info(f"Deleted file: {path}")
            return f"Deleted file: {path}"

    async def _mkdir(self, path: Path) -> str:
        """Create a directory."""
        if path.exists():
            return f"Directory already exists: {path}"

        path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created directory: {path}")
        return f"Created directory: {path}"
