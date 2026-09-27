# SPDX-License-Identifier: MIT
"""`fsar room` — talk to a room as an agent member.

This is the client half of the member ingress. An external agent runs it to
post a line into the room and to read what has been said since its cursor.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "http://127.0.0.1:8765"


def _request(url: str, token: str, *, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url, data=data, method="POST" if data else "GET",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(body).get("detail", "")
        except Exception:
            detail = body
        return {"ok": False, "code": f"http_{exc.code}", "row_id": None,
                "detail": detail}
    except (urllib.error.URLError, OSError) as exc:
        # No server there, DNS failure, TLS problem: report it the same way as
        # a rejection rather than dumping a traceback at the member.
        return {"ok": False, "code": "unreachable", "row_id": None,
                "detail": str(exc)}


def _post_json(url: str, payload: dict, token: str) -> dict:
    return _request(url, token, payload=payload)


def _get_json(url: str, token: str) -> dict:
    return _request(url, token)


def say(text: str, *, base_url: str, token: str) -> dict:
    return _post_json(f"{base_url}/api/room/member/message", {"content": text}, token)


def read(*, since: int = 0, base_url: str, token: str) -> dict:
    return _get_json(f"{base_url}/api/room/member/state?since={int(since)}", token)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fsar room")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--url", default=DEFAULT_BASE_URL, help="server base url")
    common.add_argument(
        "--token", default=None, help="member token (or FSAR_ROOM_TOKEN)",
    )
    common.add_argument("--json", action="store_true", help="compact JSON output")
    sub = parser.add_subparsers(dest="command", required=True)
    say_parser = sub.add_parser("say", parents=[common], help="post one line")
    say_parser.add_argument("text")
    read_parser = sub.add_parser("read", parents=[common], help="read new messages")
    read_parser.add_argument("--since", type=int, default=0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    token = args.token or os.environ.get("FSAR_ROOM_TOKEN", "")
    if not token:
        print(
            "No member token. Pass --token or set FSAR_ROOM_TOKEN.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    if args.command == "say":
        result = say(args.text, base_url=args.url, token=token)
    else:
        result = read(since=args.since, base_url=args.url, token=token)
    print(json.dumps(result, ensure_ascii=False, indent=None if args.json else 2))
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    sys.exit(main())
