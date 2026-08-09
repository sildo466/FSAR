"""FSAR terminal rendering — uses rich to add Markdown, syntax highlighting, and color to the CLI.

Features:
- Auto-enable Windows VT100 (ANSI escapes)
- Markdown auto-rendering (headings, lists, tables, links, code blocks)
- Code block syntax highlighting (monokai theme)
- Width-preserving monospace rendering

Functions:
- md(text)             : render a Markdown block
- say(text)            : FSAR speaks (with FSAR > prompt), auto-renders Markdown
- status(label, body)  : one-line [Tool] / [Result] style output
- header(text)         : full-width rule + title
- rule()               : full-width rule
- panel(text, title)   : bordered panel
- plain(text)          : print raw with no formatting

Class:
- ThinkingStreamPrinter : accumulates LLM stream deltas, live-displays <think>...</think>
  content (dim + italic + 💭 prefix), collapses to a single-line summary when thinking ends,
  returns the body text to the caller.
"""

from __future__ import annotations

import re
import sys
import threading

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text


# ------------------------------------------------------------
# Windows VT100 — the default cmd does not interpret ANSI sequences,
# so we must enable ENABLE_VIRTUAL_TERMINAL_PROCESSING.
# ------------------------------------------------------------
def _enable_windows_vt() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        ENABLE_VT = 0x4
        for handle_id in (-11, -12):  # STDOUT, STDERR
            handle = kernel32.GetStdHandle(handle_id)
            mode = ctypes.c_uint32()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                kernel32.SetConsoleMode(handle, mode.value | ENABLE_VT)
    except Exception:
        pass


_enable_windows_vt()


# Global console — force_terminal makes ANSI work in every environment.
# soft_wrap lets rich handle long-line wrapping to terminal width.
console = Console(
    force_terminal=True,
    soft_wrap=True,
    highlight=False,
    markup=True,
)


# ------------------------------------------------------------
# Public API
# ------------------------------------------------------------
def md(text: str) -> None:
    """Render Markdown text. Also prints plain text without markdown markers."""
    if not text or not text.strip():
        return
    rendered = Markdown(text, code_theme="monokai", inline_code_theme="monokai")
    console.print(rendered)


def say(text: str) -> None:
    """FSAR speaks — auto-renders Markdown. Empty content is not printed.

    All content (single/multi-line) is rendered through the Markdown class
    to avoid rich's markup parser eating bracket content returned by the LLM
    (e.g. [v] / [example]).
    """
    if text is None or not str(text).strip():
        return
    body = str(text).rstrip()
    console.print()
    console.print("[bold cyan]FSAR[/bold cyan] [dim]>[/dim]")
    console.print(Markdown(body, code_theme="monokai", inline_code_theme="monokai"))


def echo(role: str, text: str, color: str = "magenta") -> None:
    """Generic utterance — role="You" / "Tool" / etc. Markdown rendered."""
    if text is None or not str(text).strip():
        return
    body = str(text).rstrip()
    console.print()
    console.print(f"[bold {color}]{role}[/{color}] [dim]>[/dim]")
    console.print(Markdown(body, code_theme="monokai", inline_code_theme="monokai"))


def status(label: str, body: str = "", color: str = "dim") -> None:
    """Status line [Tool] foo / [Result] bar. body is not parsed as markup
    (to avoid LLM content being eaten)."""
    from rich.markup import escape
    console.print(f"  [{color}]\\[{label}][/{color}] {escape(body)}", highlight=False)


def status_md(label: str, body: str) -> None:
    """Status line + body rendered as markdown."""
    if not body or not body.strip():
        return
    console.print(f"  [dim]\\[{label}][/dim]")
    console.print(Markdown("    " + body.replace("\n", "\n    "), code_theme="monokai", inline_code_theme="monokai"))


def header(text: str) -> None:
    """Section title — wrapped with a full-width rule."""
    console.rule(f"[bold]{text}[/bold]")


def rule() -> None:
    """A full-width horizontal rule."""
    console.rule()


def panel(text: str, title: str = "", border_style: str = "cyan") -> None:
    """Bordered panel."""
    if title:
        console.print(Panel(text, title=f"[bold]{title}[/bold]", border_style=border_style))
    else:
        console.print(Panel(text, border_style=border_style))


def code(text: str, language: str = "python") -> None:
    """Code block with syntax highlighting (rarely called directly)."""
    console.print(Syntax(text, language, theme="monokai", word_wrap=True))


def plain(text: str) -> None:
    """Print with no formatting (e.g. ASCII art)."""
    console.print(text, markup=False, highlight=False)


def warn(text: str) -> None:
    console.print(f"[bold yellow]![/bold yellow]  {text}")


def error(text: str) -> None:
    console.print(f"[bold red]X[/bold red]  {text}")


def ok(text: str) -> None:
    console.print(f"[bold green]OK[/bold green]  {text}")


# ------------------------------------------------------------
# Streamed thinking separation — ThinkingStreamPrinter
# ------------------------------------------------------------
# The LLM writes <think>...</think> into content; we handle the stream by:
#   - entering <think>: refresh the current line live (dim + italic + 💭 prefix)
#   - receiving </think>: collapse to a one-line "💭 thinking (N chars)"
#   - body text: returned to caller after stream ends, rendered as Markdown
# Terminals don't have real font sizes; we de-emphasize via dim + italic + indent + 💭.
# ------------------------------------------------------------
_LIVE_DIM_ITALIC = "\x1b[2m\x1b[3m"  # dim + italic
_LIVE_RESET = "\x1b[0m"
_LIVE_PREFIX = "  💭 "
_STREAM_LOCK = threading.Lock()


class ThinkingStreamPrinter:
    """Process a single LLM stream's <think> blocks, live-echo thinking,
    collapse to a summary, and collect the body text."""

    def __init__(self) -> None:
        self.state = "before"  # before | thinking | after
        self.thinking_buf = ""
        self.main_buf = ""
        self._live_started = False

    def _live_write(self, text: str) -> None:
        """Live-refresh the thinking text on the same line. Multi-line thinking
        is flattened to one line (terminal single-line live update only clears
        the cursor's line)."""
        with _STREAM_LOCK:
            if not self._live_started:
                # First write: advance to a new line first
                sys.stdout.write("\n")
                self._live_started = True
            flat = text.replace("\r", "").replace("\n", " ")
            sys.stdout.write(
                f"\r\x1b[K{_LIVE_DIM_ITALIC}{_LIVE_PREFIX}{flat}{_LIVE_RESET}"
            )
            sys.stdout.flush()

    def _live_collapse(self) -> None:
        """Clear the live line, replace with a one-line summary + newline."""
        n = len(self.thinking_buf)
        with _STREAM_LOCK:
            sys.stdout.write(
                f"\r\x1b[K{_LIVE_DIM_ITALIC}{_LIVE_PREFIX}thinking ({n} chars){_LIVE_RESET}\n"
            )
            sys.stdout.flush()

    def _live_clear(self) -> None:
        """State transition produced no live line — clear any stray whitespace."""
        with _STREAM_LOCK:
            if self._live_started:
                sys.stdout.write("\r\x1b[K")
                sys.stdout.flush()

    def feed(self, delta: str) -> None:
        """Process a stream delta. State machine handles cross-chunk tag boundaries."""
        if not delta:
            return
        rest = delta
        while rest:
            if self.state == "before":
                idx = rest.find("<think>")
                if idx == -1:
                    self.main_buf += rest
                    rest = ""
                else:
                    if idx > 0:
                        self.main_buf += rest[:idx]
                    self.state = "thinking"
                    rest = rest[idx + len("<think>"):]
            elif self.state == "thinking":
                idx = rest.find("</think>")
                if idx == -1:
                    self.thinking_buf += rest
                    self._live_write(self.thinking_buf)
                    rest = ""
                else:
                    self.thinking_buf += rest[:idx]
                    self._live_collapse()
                    self.state = "after"
                    rest = rest[idx + len("</think>"):]
            else:  # after
                self.main_buf += rest
                rest = ""

    def finalize(self) -> tuple[str, str]:
        """Stream ended. Returns (thinking_text, main_text)."""
        if self.state == "thinking":
            # No </think> close (model anomaly?) — force-collapse to summary
            self._live_collapse()
        elif self.state == "before":
            # No live display ever happened; fallback clear in case the _live_started flag is wrong
            self._live_clear()
        return self.thinking_buf, self.main_buf
