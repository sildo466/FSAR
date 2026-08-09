"""FSAR pdf_analyze tool — analyze PDF documents."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from src.tools.registry import Tool
from src.utils.logger import logger


class PdfAnalyzeTool(Tool):
    """Analyze PDF documents."""

    @property
    def name(self) -> str:
        return "pdf_analyze"

    @property
    def description(self) -> str:
        return ("Analyze PDF documents. "
                "Can extract text, read specific pages, summarize content, "
                "or answer questions about the PDF.")

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the PDF file",
                },
                "pages": {
                    "type": "string",
                    "description": "Page range to analyze (e.g., '1-5', '1,3,5', 'all'). Default: first 10 pages",
                },
                "prompt": {
                    "type": "string",
                    "default": "Summarize the content of this PDF.",
                    "description": "Question or instruction about the PDF",
                },
                "max_chars": {
                    "type": "integer",
                    "default": 10000,
                    "description": "Maximum characters to extract",
                },
            },
            "required": ["file_path"],
        }

    @property
    def risk_level(self) -> str:
        return "SAFE"

    async def execute(self, file_path: str, pages: str = "1-10",
                      prompt: str = "Summarize the content of this PDF.",
                      max_chars: int = 10000, **kwargs) -> str:
        """Analyze a PDF document."""
        try:
            path = Path(file_path)
            from src.sandbox.tool_guard import guard_file_read
            from src.utils.config import get_config
            blocked = guard_file_read(
                str(path), kwargs.get("_security_config") or get_config()
            )
            if blocked:
                return blocked
            if not path.exists():
                return f"Error: File not found: {file_path}"
            if not path.suffix.lower() == ".pdf":
                return f"Error: Not a PDF file: {file_path}"

            # Extract text from PDF
            text = self._extract_text(path, pages, max_chars)
            if not text:
                return "Error: Could not extract text from PDF"

            # Use LLM to analyze
            from src.utils.config import get_config
            from src.utils.llm_factory import cached_chat_completion, make_llm_client

            config = get_config()
            llm_config = config.get_active_provider()

            client = make_llm_client(config.get("llm.active", ""))

            if len(text) > max_chars:
                text = text[:max_chars] + f"\n\n... (truncated at {max_chars} chars)"

            resp = cached_chat_completion(
                client,
                model=llm_config.get("model", "gpt-4o"),
                messages=[
                    {"role": "system", "content": "You are analyzing a PDF document. Answer based on the provided text."},
                    {"role": "user", "content": f"{prompt}\n\n--- PDF Content ---\n{text}"},
                ],
                max_tokens=4096,
            )

            result = resp.choices[0].message.content or "(no response)"
            logger.info(f"PDF analyzed: {file_path}")
            return result

        except Exception as e:
            logger.error(f"PDF analysis failed: {e}")
            return f"Error: {e}"

    def _extract_text(self, path: Path, pages: str, max_chars: int) -> str:
        """Extract text from PDF using available library."""
        try:
            import PyPDF2
            return self._extract_with_pypdf2(path, pages, max_chars)
        except ImportError:
            pass

        try:
            import pdfplumber
            return self._extract_with_pdfplumber(path, pages, max_chars)
        except ImportError:
            pass

        # Fallback: try to use PDF.js via Node.js (if available)
        return self._extract_with_command(path, max_chars)

    def _extract_with_pypdf2(self, path: Path, pages: str, max_chars: int) -> str:
        """Extract using PyPDF2."""
        import PyPDF2

        page_numbers = self._parse_page_range(pages)

        with open(path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            total_pages = len(reader.pages)

            if not page_numbers:
                page_numbers = list(range(min(10, total_pages)))
            else:
                page_numbers = [p for p in page_numbers if p < total_pages]

            text_parts = []
            char_count = 0

            for page_num in page_numbers:
                if char_count >= max_chars:
                    break
                page = reader.pages[page_num]
                page_text = page.extract_text() or ""
                if page_text:
                    text_parts.append(f"[Page {page_num + 1}]\n{page_text}")
                    char_count += len(page_text)

            return "\n\n".join(text_parts)

    def _extract_with_pdfplumber(self, path: Path, pages: str, max_chars: int) -> str:
        """Extract using pdfplumber."""
        import pdfplumber

        page_numbers = self._parse_page_range(pages)

        with pdfplumber.open(path) as pdf:
            total_pages = len(pdf.pages)

            if not page_numbers:
                page_numbers = list(range(min(10, total_pages)))
            else:
                page_numbers = [p for p in page_numbers if p < total_pages]

            text_parts = []
            char_count = 0

            for page_num in page_numbers:
                if char_count >= max_chars:
                    break
                page = pdf.pages[page_num]
                page_text = page.extract_text() or ""
                if page_text:
                    text_parts.append(f"[Page {page_num + 1}]\n{page_text}")
                    char_count += len(page_text)

            return "\n\n".join(text_parts)

    def _extract_with_command(self, path: Path, max_chars: int) -> str:
        """Fallback: extract using command line tools."""
        import subprocess

        try:
            # Try pdftotext (poppler)
            result = subprocess.run(
                ["pdftotext", "-l", "10", str(path), "-"],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout[:max_chars]
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        return "Error: No PDF extraction library available. Install PyPDF2 or pdfplumber."

    def _parse_page_range(self, pages: str) -> list:
        """Parse page range string to list of 0-based page numbers."""
        if pages.lower() == "all":
            return []

        result = []
        for part in pages.split(","):
            part = part.strip()
            if "-" in part:
                start, end = part.split("-", 1)
                try:
                    result.extend(range(int(start) - 1, int(end)))
                except ValueError:
                    continue
            else:
                try:
                    result.append(int(part) - 1)
                except ValueError:
                    continue
        return result
