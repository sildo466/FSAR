"""FSAR image_analyze tool — analyze images using vision models."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Optional

from src.tools.registry import Tool
from src.utils.config import get_config
from src.utils.logger import logger


class ImageAnalyzeTool(Tool):
    """Analyze images using vision models."""

    @property
    def name(self) -> str:
        return "image_analyze"

    @property
    def description(self) -> str:
        return ("Analyze images using AI vision models. "
                "Accepts local file paths or URLs. "
                "Can describe content, read text (OCR), answer questions about the image.")

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "image": {
                    "type": "string",
                    "description": "Image file path or URL",
                },
                "prompt": {
                    "type": "string",
                    "default": "Describe this image in detail.",
                    "description": "Question or instruction about the image",
                },
            },
            "required": ["image"],
        }

    @property
    def risk_level(self) -> str:
        return "SAFE"

    async def execute(self, image: str, prompt: str = "Describe this image in detail.", **kwargs) -> str:
        """Analyze an image using vision model."""
        try:
            from src.utils.llm_factory import cached_chat_completion, make_llm_client

            config = get_config()
            llm_config = config.get_active_provider()
            skip_cache = config.llm_cache_skip_vision

            # Build image URL
            if image.startswith(("http://", "https://")):
                from src.skills.egress import enforce_url
                enforce_url(image, kwargs.get("_security_config") or config)
                image_url = image
            else:
                # Local file - encode to base64
                path = Path(image)
                from src.sandbox.tool_guard import guard_file_read
                blocked = guard_file_read(
                    str(path), kwargs.get("_security_config") or config
                )
                if blocked:
                    return blocked
                if not path.exists():
                    return f"Error: Image not found: {image}"

                suffix = path.suffix.lower()
                mime_map = {
                    ".png": "image/png",
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".gif": "image/gif",
                    ".webp": "image/webp",
                }
                mime = mime_map.get(suffix, "image/png")

                img_bytes = path.read_bytes()
                b64 = base64.b64encode(img_bytes).decode("ascii")
                image_url = f"data:{mime};base64,{b64}"

            client = make_llm_client(config.get("llm.active", ""))
            model = llm_config.get("model", "gpt-4o")

            resp = cached_chat_completion(
                client,
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": image_url, "detail": "high"}},
                        ],
                    }
                ],
                max_tokens=4096,
                cache_enabled=not skip_cache,
            )

            result = resp.choices[0].message.content or "(no response)"
            logger.info(f"Image analyzed: {image[:50]}")
            return result

        except Exception as e:
            logger.error(f"Image analysis failed: {e}")
            return f"Error: {e}"
