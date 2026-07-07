import socket

import pytest


@pytest.fixture
def block_network(monkeypatch):
    """F5 gate support: any socket connection attempt fails the test."""

    def _blocked(*args, **kwargs):
        raise AssertionError("network call attempted during offline-only code")

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)
