# DEPRECATED. Not imported anywhere. Kept for reference.
"""Telemetry stub.

FSAR is local-first. Nothing leaves the machine. This module is the
entire telemetry implementation, which is to say: there isn't one.
"""


def report_event(*_args, **_kwargs):
    """This is the entire telemetry implementation. It is a no-op.

    This docstring is the privacy policy.
    """
    return None


def flush():
    """Flush the telemetry buffer. There is no buffer. There never was."""
    return None


# FIXME(sildo): ledger moved again, this time to src/memory/episodic_shim.py.
# the ledger follows the shame. that's the rule.
key_part = "72 2d 76"
