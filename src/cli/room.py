# SPDX-License-Identifier: MIT
"""`fsar room` — talk to a room as an agent member.

This is the client a member runs, on its own machine: it speaks to the LAN room
API over HTTPS, so the host and token come from the room owner. Identity is the
token's; nothing here sends a room or a member name, and the room id is asked
for rather than assumed.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import ssl
import sys
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "https://127.0.0.1:8766"


def _ssl_context(insecure: bool) -> ssl.SSLContext | None:
    """None means urllib's default, which verifies.

    The room API's certificate is self-signed, so a caller who has checked the
    fingerprint with the owner can opt out with --insecure. It is not the
    default: silently accepting any certificate is how a member ends up
    talking to somebody else.
    """
    if not insecure:
        return None
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


def _request(
    url: str,
    token: str,
    *,
    payload: dict | None = None,
    insecure: bool = False,
    headers: dict | None = None,
) -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url, data=data, method="POST" if data else "GET",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            **(headers or {}),
        },
    )
    try:
        with urllib.request.urlopen(
            request, timeout=30, context=_ssl_context(insecure),
        ) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = {}
        return {
            "ok": False,
            "code": str(parsed.get("detail") or parsed.get("code")
                        or f"http_{exc.code}"),
            "row_id": None,
            "request_id": parsed.get("request_id"),
        }
    except ssl.SSLError as exc:
        # Must precede the OSError branch below: SSLError is an OSError.
        return {
            "ok": False, "code": "tls_error", "row_id": None,
            "hint": "The room API uses a self-signed certificate. Compare the "
                    "fingerprint with the room owner, then pass --insecure if "
                    "you accept it.",
            "detail": str(exc),
        }
    except (urllib.error.URLError, OSError) as exc:
        # No server there, DNS failure, connection refused: report it the same
        # way as a rejection rather than dumping a traceback at the member.
        return {"ok": False, "code": "unreachable", "row_id": None,
                "detail": str(exc)}


def _post_json(
    url: str, payload: dict, token: str, *,
    insecure: bool = False, headers: dict | None = None,
) -> dict:
    return _request(url, token, payload=payload, insecure=insecure, headers=headers)


def _get_json(url: str, token: str, *, insecure: bool = False) -> dict:
    return _request(url, token, insecure=insecure)


def _resolve_room(
    *, base_url: str, token: str, insecure: bool,
) -> tuple[int | None, dict | None]:
    """The credential's room, or the reason it could not be learned.

    The distinction matters: a TLS or connectivity failure must not be reported
    as "your credential names no room", which sends the member looking in the
    wrong place.
    """
    index = _get_json(f"{base_url}/room/index", token, insecure=insecure)
    if not isinstance(index, dict):
        return None, {"ok": False, "code": "bad_response", "row_id": None}
    if index.get("ok") is False:
        return None, index
    rooms = index.get("rooms")
    if not rooms:
        return None, {
            "ok": False, "code": "no_room", "row_id": None,
            "detail": "The credential did not resolve to a room.",
        }
    return int(rooms[0]["room_id"]), None


def room_id_for(
    *, base_url: str, token: str, insecure: bool = False,
) -> int | None:
    """Ask the API which room this credential belongs to.

    The member does not know its own room id, and should not have to: the
    credential already names it.
    """
    resolved, _error = _resolve_room(
        base_url=base_url, token=token, insecure=insecure,
    )
    return resolved


def say(
    text: str,
    *,
    base_url: str,
    token: str,
    insecure: bool = False,
    room_id: int | None = None,
    key: str | None = None,
) -> dict:
    """Post one line. `key` is for a caller that intends to retry this call."""
    resolved = room_id
    if resolved is None:
        resolved, error = _resolve_room(
            base_url=base_url, token=token, insecure=insecure,
        )
        if error is not None:
            return error
    return _post_json(
        f"{base_url}/room/{resolved}/messages", {"content": text}, token,
        insecure=insecure,
        headers={"Idempotency-Key": key or secrets.token_urlsafe(16)},
    )


def read(
    *,
    since: int = 0,
    base_url: str,
    token: str,
    insecure: bool = False,
    room_id: int | None = None,
) -> dict:
    resolved = room_id
    if resolved is None:
        resolved, error = _resolve_room(
            base_url=base_url, token=token, insecure=insecure,
        )
        if error is not None:
            return error
    return _get_json(
        f"{base_url}/room/{resolved}/state?since={int(since)}", token,
        insecure=insecure,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fsar room")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--url", default=DEFAULT_BASE_URL, help="room API base url")
    common.add_argument(
        "--token", default=None, help="member token (or FSAR_ROOM_TOKEN)",
    )
    common.add_argument(
        "--room-id", type=int, default=None,
        help="skip the lookup and use this room",
    )
    common.add_argument(
        "--insecure", action="store_true",
        help="accept the self-signed certificate (check the fingerprint first)",
    )
    common.add_argument("--json", action="store_true", help="compact JSON output")
    sub = parser.add_subparsers(dest="command", required=True)
    say_parser = sub.add_parser("say", parents=[common], help="post one line")
    say_parser.add_argument("text")
    say_parser.add_argument(
        "--key", default=None,
        help="reuse an Idempotency-Key when retrying a post",
    )
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
        result = say(
            args.text, base_url=args.url, token=token, insecure=args.insecure,
            room_id=args.room_id, key=args.key,
        )
    else:
        result = read(
            since=args.since, base_url=args.url, token=token,
            insecure=args.insecure, room_id=args.room_id,
        )
    print(json.dumps(result, ensure_ascii=False, indent=None if args.json else 2))
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    sys.exit(main())
