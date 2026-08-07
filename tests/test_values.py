"""Knob values: the 7-bit range, clamping, and the keys that change them."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def test_starts_at_zero(offline_app):
    app = offline_app(4)
    async with app.run_test():
        assert app.values == [0, 0, 0, 0]


async def test_nudge_and_clamp_at_max(offline_app):
    app = offline_app(2)
    async with app.run_test() as pilot:
        await pilot.press("end")
        assert app.values[0] == 127, "end goes to the top of the 7-bit range"
        await pilot.press("up")
        assert app.values[0] == 127, "must not exceed 127"


async def test_clamp_at_min(offline_app):
    app = offline_app(2)
    async with app.run_test() as pilot:
        await pilot.press("end", "home")
        assert app.values[0] == 0
        await pilot.press("down")
        assert app.values[0] == 0, "must not go below 0"


async def test_coarse_step(offline_app):
    app = offline_app(2)
    async with app.run_test() as pilot:
        for _ in range(3):
            await pilot.press("shift+up")
        assert app.values[0] == 30


async def test_selection_wraps(offline_app):
    app = offline_app(3)
    async with app.run_test() as pilot:
        await pilot.press("left")
        assert app.cursor == 2, "left from the first knob wraps to the last"
        await pilot.press("right")
        assert app.cursor == 0


async def test_digit_jumps_to_knob(offline_app):
    app = offline_app(5)
    async with app.run_test() as pilot:
        await pilot.press("4")
        assert app.cursor == 3


async def test_digit_beyond_count_is_ignored(offline_app):
    app = offline_app(3)
    async with app.run_test() as pilot:
        await pilot.press("9")
        assert app.cursor == 0


async def test_reset_zeroes_everything(offline_app):
    app = offline_app(3)
    async with app.run_test() as pilot:
        await pilot.press("end", "right", "end", "r")
        assert app.values == [0, 0, 0]


async def test_only_the_selected_knob_moves(offline_app):
    app = offline_app(3)
    async with app.run_test() as pilot:
        await pilot.press("right", "up", "up")
        assert app.values == [0, 2, 0]
