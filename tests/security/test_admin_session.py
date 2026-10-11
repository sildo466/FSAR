# SPDX-License-Identifier: MIT
from __future__ import annotations

from src.security.admin_session import AdminSessions, is_loopback


def test_loopback_is_about_the_address_not_the_name():
    assert is_loopback("127.0.0.1")
    assert is_loopback("::1")
    assert is_loopback("localhost")
    assert not is_loopback("192.168.1.20")
    assert not is_loopback("")
    assert not is_loopback("testclient")


def test_bootstrap_is_consumed_once():
    sessions = AdminSessions()
    token = sessions.rotate_bootstrap()

    session = sessions.consume_bootstrap(token)
    assert session is not None
    assert sessions.session_valid(session)

    assert sessions.consume_bootstrap(token) is None
    assert sessions.consume_bootstrap("something-else") is None
    assert sessions.consume_bootstrap("") is None


def test_a_ticket_is_used_once_and_expires():
    sessions = AdminSessions(ticket_ttl=60.0)
    session = sessions.create_session()

    ticket = sessions.issue_ticket(session, now=100.0)
    assert ticket is not None
    assert sessions.consume_ticket(ticket, now=101.0)
    assert not sessions.consume_ticket(ticket, now=101.0)

    expiring = sessions.issue_ticket(session, now=100.0)
    assert not sessions.consume_ticket(expiring, now=161.0)


def test_an_unknown_session_gets_no_ticket():
    sessions = AdminSessions()
    assert sessions.issue_ticket("never-issued") is None
    assert not sessions.session_valid("never-issued")
    assert not sessions.session_valid("")
    assert not sessions.consume_ticket("")
