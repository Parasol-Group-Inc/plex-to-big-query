"""Tests for the one-time Plex reconnect in main.py's extraction loop.

    python tests/test_connection_lost.py            # plain asserts, prints OK
    python -m pytest tests/test_connection_lost.py  # same tests under pytest

No Plex, BigQuery or SendGrid needed.
"""
import os
import sys
from pathlib import Path

import pyodbc

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("GCP_PROJECT", "voxdatalake")
os.environ.setdefault("BQ_DATASET", "PlexTest")

import main as m  # noqa: E402


def test_session_kill_and_network_abort_are_connection_lost():
    # The two messages from the 2026-10-23 Work Orders email.
    assert m.connection_lost(pyodbc.OperationalError(
        "08S01", "[08S01] [DataDirect][ODBC OpenAccess SDK driver][OpenAccess SDK Client]"
                 "Connection closed due to session kill (2251) (SQLExecDirectW)"))
    assert m.connection_lost(pyodbc.OperationalError(
        "08S01", "[08S01] [DataDirect][ODBC OpenAccess SDK driver][OpenAccess SDK Client]"
                 "Internal network error, session aborted, connection closed (2208) (SQLExecDirectW)"))


def test_other_errors_are_not_retried():
    # A bad query or a refused login fails the same way on a new session.
    assert not m.connection_lost(pyodbc.ProgrammingError("42S02", "[42S02] Invalid object name"))
    assert not m.connection_lost(pyodbc.InterfaceError("28000", "[28000] Login failed"))
    assert not m.connection_lost(ValueError("08S01"))     # not an ODBC error
    assert not m.connection_lost(pyodbc.Error())          # no SQLSTATE at all


if __name__ == "__main__":
    test_session_kill_and_network_abort_are_connection_lost()
    test_other_errors_are_not_retried()
    print("OK")
