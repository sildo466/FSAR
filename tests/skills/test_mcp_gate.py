from __future__ import annotations

import asyncio
from unittest.mock import patch

from src.mcp.manager import MCPManager
from src.skills.gate import mcp_config_bytes
from src.skills.keys import KeyStore
from src.skills.safe_marker import SafeMarker
from src.tools.registry import ToolRegistry
from src.utils.fsar_config import FsarConfig


def _config(tmp_path) -> FsarConfig:
    path = tmp_path / "fsar.yaml"
    path.write_text("security:\n  mcp:\n    review_required: true\n", encoding="utf-8")
    return FsarConfig(path)


def _server() -> dict:
    return {
        "name": "test",
        "enabled": True,
        "transport": "stdio",
        "command": "python",
        "args": ["server.py"],
    }


def test_mcp_manager_does_not_spawn_unreviewed_server(tmp_path):
    manager = MCPManager(
        ToolRegistry(),
        fsar_servers=[_server()],
        config=_config(tmp_path),
        servers_root=tmp_path / "servers",
        marker=SafeMarker(KeyStore(tmp_path / "keys.json")),
    )

    with patch("src.mcp.manager.MCPClient") as client:
        asyncio.run(manager.start())

    client.assert_not_called()


def test_mcp_marker_is_bound_to_server_configuration(tmp_path):
    server = _server()
    root = tmp_path / "servers"
    subject = root / "test"
    subject.mkdir(parents=True)
    marker = SafeMarker(KeyStore(tmp_path / "keys.json"))
    marker.write(
        subject,
        "mcp:test",
        reviewer="user",
        supplemental=mcp_config_bytes(server),
    )

    changed = {**server, "args": ["different.py"]}

    assert marker.verify(
        subject, "mcp:test", supplemental=mcp_config_bytes(server)
    ).valid
    assert marker.verify(
        subject, "mcp:test", supplemental=mcp_config_bytes(changed)
    ).reason == "content_changed"
