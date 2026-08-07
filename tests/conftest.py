"""Shared fixtures.

Everything here runs against a temporary config file and a headless Textual
app, so tests never touch the real `~/.config/pyknobs/config.toml` and never
need a terminal.

MIDI is the awkward part: `MidiIO` talks to CoreMIDI, which may or may not have
an IAC bus depending on the machine. Tests that only care about state use
`offline_app`, which stubs the port layer out entirely. The few that genuinely
exercise the wire are marked `midi` and skipped when no IAC bus exists.
"""

from __future__ import annotations

import pytest

from pyknobs import config as config_module
from pyknobs.app import PyKnobs


@pytest.fixture
def config_path(tmp_path):
    return tmp_path / "config.toml"


@pytest.fixture
def make_config(config_path):
    def _make(count: int = 8, **kwargs):
        cfg = config_module.load(config_path, count)
        for key, value in kwargs.items():
            setattr(cfg, key, value)
        return cfg

    return _make


class FakeMidi:
    """Stand-in for MidiIO: records sends, lets tests inject inbound messages."""

    def __init__(self, on_message, in_port_name=None, out_port_name=None):
        self._on_message = on_message
        self.in_port_name = in_port_name or "fake-in"
        self.out_port_name = out_port_name or "fake-out"
        self.error = None
        self.sent: list[tuple[int, int]] = []
        self._open = False

    @property
    def connected(self) -> bool:
        return self._open

    @property
    def status(self) -> str:
        return "fake — in/out" if self._open else "offline"

    def port_present(self) -> bool:
        return True

    def open(self) -> None:
        self._open = True
        self.error = None

    def send(self, control: int, value: int) -> None:
        self.sent.append((control, value))

    def close(self) -> None:
        self._open = False

    # Note: tests inject inbound messages with `app._on_incoming(msg)` rather
    # than through this callback. The real callback runs on rtmidi's thread and
    # hops back via `call_from_thread`, which raises if called from the event
    # loop thread that the tests themselves run on. The hop is trivial; the
    # decision logic in `_on_incoming` is what's worth testing.


@pytest.fixture
def offline_app(make_config, monkeypatch):
    """A PyKnobs whose MIDI layer is a recorder, not CoreMIDI."""

    def _make(count: int = 8, **kwargs):
        monkeypatch.setattr("pyknobs.app.MidiIO", FakeMidi)
        app = PyKnobs(make_config(count, **kwargs))
        return app

    return _make
