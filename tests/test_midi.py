"""What goes on the wire, what comes off it, and what gets ignored.

These are the rules that matter most: the feedback-loop guard, echo suppression
on a loopback bus, and never silently dropping inbound traffic.
"""

from __future__ import annotations

import mido
import pytest

from pyknobs.config import CHANNEL

pytestmark = pytest.mark.asyncio


def cc(control: int, value: int, channel: int = CHANNEL) -> mido.Message:
    return mido.Message("control_change", channel=channel, control=control, value=value)


async def test_moving_a_knob_transmits(offline_app):
    app = offline_app(3)
    async with app.run_test() as pilot:
        await pilot.press("up", "up")
        assert app.midi.sent == [(10, 1), (10, 2)]


async def test_transmits_on_the_knobs_own_cc(offline_app):
    app = offline_app(3)
    async with app.run_test() as pilot:
        await pilot.press("right", "up")
        assert app.midi.sent == [(11, 1)]


async def test_host_update_is_never_echoed(offline_app):
    """The core feedback-loop guard: inbound changes state, sends nothing."""
    app = offline_app(3)
    async with app.run_test():
        app._on_incoming(cc(11, 64))
        assert app.values[1] == 64
        assert app.midi.sent == [], "an inbound CC must not be retransmitted"


async def test_values_survive_a_round_trip_exactly(offline_app):
    """No scaling in either direction: 100 in, 100 out."""
    app = offline_app(3)
    async with app.run_test():
        for value in (0, 1, 63, 100, 126, 127):
            app._on_incoming(cc(10, value))
            assert app.values[0] == value


async def test_our_own_loopback_echo_is_ignored(offline_app):
    """IAC reflects our sends back at us; that isn't the host talking."""
    app = offline_app(3)
    async with app.run_test() as pilot:
        await pilot.press("up")
        assert app.values[0] == 1
        app._on_incoming(cc(10, 1))  # the echo
        assert app.values[0] == 1
        assert app.midi.sent == [(10, 1)], "the echo must not bounce again"


async def test_a_genuine_repeat_after_the_window_is_accepted(offline_app, monkeypatch):
    app = offline_app(3)
    async with app.run_test() as pilot:
        await pilot.press("end")          # sends 127
        app._on_incoming(cc(10, 0))       # host moves it away
        assert app.values[0] == 0
        # Host sends 127 again, long after we sent it: a real update.
        import pyknobs.app as app_module
        monkeypatch.setattr(app_module, "ECHO_WINDOW", 0.0)
        app._on_incoming(cc(10, 127))
        assert app.values[0] == 127


@pytest.mark.parametrize(
    "message, reason",
    [
        (cc(11, 64, channel=5), "wrong channel"),
        (cc(99, 64), "unmapped CC"),
        (mido.Message("note_on", channel=CHANNEL, note=60, velocity=100), "not a CC"),
    ],
)
async def test_unmatched_traffic_changes_nothing(offline_app, message, reason):
    app = offline_app(3)
    async with app.run_test():
        app._on_incoming(message)
        assert app.values == [0, 0, 0], reason
        assert app.midi.sent == []


async def test_unmatched_traffic_is_logged_when_raw_is_on(offline_app):
    """Nothing inbound is dropped silently -- that's what makes a dead
    mapping diagnosable."""
    app = offline_app(3, )
    app.raw = True
    async with app.run_test() as pilot:
        lines = []
        app._log = lambda markup: lines.append(markup)
        app._on_incoming(cc(11, 64, channel=5))
        app._on_incoming(cc(99, 64))
        await pilot.pause()
        assert len(lines) == 2
        assert "channel 6" in lines[0]
        assert "CC99" in lines[1]


async def test_repeating_the_same_value_sends_nothing(offline_app):
    app = offline_app(3)
    async with app.run_test() as pilot:
        await pilot.press("home")
        assert app.midi.sent == [], "already 0; nothing changed"
