# SPDX-License-Identifier: MIT
"""Local faster-whisper transcription using downloaded snapshots only."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from . import faster_whisper_models
from .base import AsrError

_model_cache: dict[str, object] = {}


def _get_model(size: str):
    cached = _model_cache.get(size)
    if cached is not None:
        return cached
    path = faster_whisper_models.resolve_model_path(size)
    if path is None:
        raise AsrError(
            "model_not_downloaded",
            f"faster-whisper model {size!r} is not downloaded",
        )
    try:
        from faster_whisper import WhisperModel
    except ImportError as error:
        raise AsrError("provider_5xx", "faster-whisper is not installed") from error
    model = WhisperModel(
        str(path),
        device="auto",
        compute_type="auto",
        local_files_only=True,
    )
    _model_cache[size] = model
    return model


def _transcribe_file(path: Path, size: str, language: str) -> str:
    model = _get_model(size)
    selected_language = None if language in ("", "auto") else language
    segments, _info = model.transcribe(
        str(path),
        language=selected_language,
        beam_size=5,
    )
    return " ".join(segment.text for segment in segments).strip()


async def transcribe(
    *,
    audio: bytes,
    mime_type: str,
    language: str,
    model: str,
) -> str:
    if not model or not faster_whisper_models.is_downloaded(model):
        raise AsrError(
            "model_not_downloaded",
            f"faster-whisper model {model or '(unset)'!r} is not downloaded",
        )
    extension = {
        "audio/webm": "webm",
        "audio/ogg": "ogg",
        "audio/mp4": "mp4",
        "audio/m4a": "m4a",
        "audio/wav": "wav",
        "audio/x-wav": "wav",
        "audio/mpeg": "mp3",
        "audio/mp3": "mp3",
    }.get(mime_type.lower(), "bin")
    with tempfile.NamedTemporaryFile(suffix=f".{extension}", delete=False) as temporary:
        temporary.write(audio)
        path = Path(temporary.name)
    try:
        return await asyncio.to_thread(_transcribe_file, path, model, language)
    except AsrError:
        raise
    except Exception as error:
        raise AsrError("provider_5xx", f"faster-whisper failed: {error}") from error
    finally:
        path.unlink(missing_ok=True)
