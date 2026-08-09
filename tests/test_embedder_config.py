# SPDX-License-Identifier: Apache-2.0
from unittest.mock import Mock, patch

from src.memory.embedder import build_embedder
from src.memory.lmstudio_embed import LMStudioEmbeddingFunction


def test_build_embedder_uses_yaml_base_url_and_model():
    config = Mock()
    config.get.return_value = {
        "provider": "lmstudio",
        "base_url": "http://localhost:1234/v1",
        "model": "configured-embedding-model",
        "timeout": 12,
    }

    with patch("src.memory.embedder.get_config", return_value=config):
        embedder = build_embedder()

    assert embedder.base_url == "http://localhost:1234"
    assert embedder.model == "configured-embedding-model"
    assert embedder.timeout == 12


def test_lmstudio_never_duplicates_v1_in_embeddings_endpoint():
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"data": [{"index": 0, "embedding": [0.1, 0.2]}]}
    embedder = LMStudioEmbeddingFunction(
        base_url="http://localhost:1234/v1/v1/",
        model="embedding-model",
    )

    with patch("src.memory.lmstudio_embed.httpx.post", return_value=response) as post:
        result = embedder(["ping"])

    assert list(result[0]) == [0.1, 0.2]
    assert post.call_args.args[0] == "http://localhost:1234/v1/embeddings"
