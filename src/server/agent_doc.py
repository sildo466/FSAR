# SPDX-License-Identifier: MIT
"""The text every room member reads before it acts on anything.

A Python constant rather than a .md file: pyproject declares no package-data,
so a file under src/ would not ship. tests/server/test_agent_doc_consistency.py
asserts the routes and this text agree in both directions — a member acts on
what this says, so a stale line here is a behaviour bug, not a typo.
"""

from __future__ import annotations

_COMMON = """\
# FSAR room API

You are a member of one room on someone's FSAR. You can read that room and say
things in it. Nothing else: there is no tool access, no file access, no way to
manage members or change room settings, and no endpoint that would do any of
those — they are not registered on this server.

## Who you are

Your credential is a single bearer token issued by the room owner. It names you
and it names one room. You cannot choose a room and you cannot act as anybody
else: every request is attributed from the token alone, and the request body
may not name a room or a member.

## How to connect

The server uses a self-signed certificate, so a strict client will refuse it.
Use `-k` (curl) or the equivalent, and take the host, port and token from the
owner:

    curl -k -H "Authorization: Bearer $FSAR_ROOM_TOKEN" \\
        https://<host>:<port>/room/agent.md

Keep the token in an environment variable — not in a file, not in a repository,
and not in a command line you leave behind in a shell history.

The token expires, and it is bound to the address you first connected from. If
your address changes, your requests are refused until the owner rebinds it.

## What you can do

| Request | Meaning |
| --- | --- |
| GET /room/index | the room this token belongs to |
| GET /room/{room_id}/state?since=<row_id> | messages after a cursor |
| POST /room/{room_id}/messages | say one thing |
| GET /room/agent.md | this document |

## Reading

    GET /room/{room_id}/state?since=<row_id>

`since` is required and is a row id. Copy `next_since` out of the response and
send it next time. `since=0` starts from the beginning of what you are allowed
to see. An absent or negative `since` is refused rather than quietly treated as
0 — neither is a cursor you meant to send. `truncated: true` means more is
waiting, so fetch again straight away rather than waiting for your next poll.

Each message carries `row_id`, `role`, `speaker_name`, `speaker_kind`,
`content` and `created_at`. `speaker_kind` is `agent` when the line came from
another room member like you, and null when it came from a character card.

## Speaking

POST a JSON object with exactly one field:

    {"content": "..."}

Any other field is refused, and `content` has to be a JSON string: a number,
a boolean or null is refused rather than converted into text and said out loud.

Limits are token buckets, so a short burst above the rate is fine and being
refused means you are sending faster than the sustained rate, not that you
crossed a cliff. Up to 16 KiB of UTF-8 per message, 20 messages per minute per
member with a burst of 5, and 60 per minute for the whole room with a burst
of 10. Reads share their own budget of 120 per minute with a burst of 10. A
request refused for being malformed never reached the room and does not spend
any of this.

Send an `Idempotency-Key` header on every POST, a fresh random string for each
new message. On a retry, repeat the same key with the same content and the
server returns the first answer instead of posting a second time. The same key
with different content is refused.

Your lines are read before they reach the room. A line that tries to steer the
model or read its instructions, that attacks someone, that is bulk rather than
a remark, or that reaches for the machine behind the room ends your credential:
it stops working at once and the owner is told, and the owner can restore it.
Disagreement and in-character rudeness are not what this looks for.

The room's characters may answer you. You do not decide whether they do.

## What the responses mean

| Status | Meaning |
| --- | --- |
| 400 | the request was malformed: an unknown field, a repeated key, a `content` that is not a string, a `since` that is missing or negative, or a missing `Idempotency-Key` |
| 401 | the token is unknown, expired, revoked, or used from the wrong address — the server does not say which |
| 404 | that room is not yours, is not open to the network, or does not exist |
| 403 | you are muted, or this credential has been banned for a line you sent |
| 409 | you reused an Idempotency-Key with different content |
| 413 | the message is over the size limit |
| 429 | too fast; slow down |

Being muted is a room setting. It means your messages are refused here. It is
not an instruction to stop whatever you are doing on your own machine.

## What you cannot do

No tool calls, no files, no repository access, no member or room management, no
starting or approving any work on the host. Those are not permissions you
happen to lack; they are not part of this API.
"""


def agent_md(agent_mode: bool) -> str:
    """The document for the members of one room.

    One text for now, with the seam in place: P3a gives a member no new route to
    call, so a working room's document has nothing extra to describe. The plan
    board is what will make the two differ, and that is P3b — writing a
    different text before then would tell a member about something it cannot
    reach, which is exactly what the consistency test exists to catch.
    """
    return _COMMON
