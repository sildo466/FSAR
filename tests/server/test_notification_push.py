# SPDX-License-Identifier: MIT
"""A notification written anywhere reaches the GUI's badge.

Nothing polls the feed, so unless the insert says so the icon sits dark until
the notifications page is opened. The producers are scattered — a security
scan, the network listener, the update check — and most never see a socket,
which is why the store tells whoever registered instead.
"""

from __future__ import annotations

import asyncio
import threading

from src.notifications.store import NotificationStore, on_feed_changed
from src.server import ws_server
from src.server.handlers import chat as chat_handler


def test_the_push_is_a_no_op_before_startup(monkeypatch) -> None:
    monkeypatch.setattr(ws_server, "_gui_loop", None)
    ws_server.notify_feed_changed()


def test_a_new_notification_reaches_the_gui_broadcast(tmp_path, monkeypatch) -> None:
    reached = threading.Event()
    sent: list[dict] = []

    async def fake_broadcast(event):
        sent.append(event)
        reached.set()

    monkeypatch.setattr(chat_handler, "_broadcast", fake_broadcast)
    from src.notifications import store as store_module

    monkeypatch.setattr(store_module, "_feed_listeners", [])
    on_feed_changed(ws_server.notify_feed_changed)

    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    try:
        monkeypatch.setattr(ws_server, "_gui_loop", loop)
        # Any producer: it only has the store in hand, no socket.
        NotificationStore(tmp_path / "memory.db").add(
            kind="review", title="quarantined", ref="7",
        )

        assert reached.wait(5), "the insert never reached the broadcast"
        assert sent == [{"type": "notifications.changed"}]
    finally:
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=5)
        loop.close()
