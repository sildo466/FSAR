import asyncio
from unittest.mock import AsyncMock, Mock, patch

import numpy as np

from src.server.handlers import embedding as embedding_handler


def test_probe_accepts_numpy_embedding_vector():
    ws = Mock()
    ws.send_json = AsyncMock()
    embedder = Mock()
    embedder.return_value = [np.array([0.1, 0.2])]
    embedder.name.return_value = "lmstudio"
    embedder.base_url = "http://localhost:1234"
    embedder.model = "embedding-model"

    with patch("src.memory.embedder.build_embedder", return_value=embedder):
        handled = asyncio.run(embedding_handler.dispatch(
            ws,
            {
                "type": "embedding.probe",
                "provider": "lmstudio",
                "base_url": embedder.base_url,
                "model": embedder.model,
            },
            Mock(),
        ))

    assert handled is True
    assert ws.send_json.await_args.args[0] == {
        "type": "embedding.probe_result",
        "ok": True,
        "provider": "lmstudio",
        "base_url": "http://localhost:1234",
        "model": "embedding-model",
        "dim": 2,
        "error": None,
    }
