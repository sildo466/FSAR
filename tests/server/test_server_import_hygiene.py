# SPDX-License-Identifier: MIT
"""The server module must be loaded exactly once.

Launched as `python -m src.server.ws_server`, the file is `__main__`. Any
`from src.server import ws_server` inside the running server loads the same
file a second time under a second name, re-running everything at module level:
a second FastAPI app, a second ChatEngine, a second LanSupervisor. The second
one never runs its startup, and the wiring calls in its module body overwrite
the handler globals — so the GUI talks to a listener that does not exist while
the first one holds the port. Every attempt the second one makes then fails
with a bind error that nothing can report.

Nothing under src/ needs the server module. This runs in a subprocess because
`sys.modules` is shared state: another test in the same session may have
imported it already.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Both call sites, with a stubbed guard so this stays cheap: the test is about
# imports, not about screening.
PROBE = textwrap.dedent(
    """
    import sys

    from src.security import content_guard

    class _StubGuard:
        def list_quarantine(self):
            return []

    content_guard._build_guard = lambda: _StubGuard()

    from src.server.handlers import card, screening

    screening._guard()
    assert card._quarantined_card_ids() == set()

    print("LOADED" if "src.server.ws_server" in sys.modules else "CLEAN")
    """
)


def test_touching_a_handler_does_not_load_the_server() -> None:
    result = subprocess.run(
        [sys.executable, "-c", PROBE],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env={**os.environ, "PYTHONPATH": "."},
        timeout=180,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    assert "CLEAN" in result.stdout, result.stdout
    assert "LOADED" not in result.stdout, (
        "the server module was loaded a second time by a handler; see this "
        f"file's docstring\n{result.stdout}"
    )
