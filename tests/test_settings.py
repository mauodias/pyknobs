"""The settings modal, and that the shortcuts survive alongside it."""

from __future__ import annotations

import pytest
from textual.widgets import Input

from pyknobs.settings import KnobRow, SettingsScreen

pytestmark = pytest.mark.asyncio


def rows(app):
    return list(app.screen.query(KnobRow))


def set_name(row, value):
    row.query_one(".name-input", Input).value = value


def set_cc(row, value):
    row.query_one(".cc-input", Input).value = str(value)


async def test_opens_and_cancels(offline_app):
    app = offline_app(3)
    async with app.run_test() as pilot:
        await pilot.press("comma")
        assert isinstance(app.screen, SettingsScreen)
        assert len(rows(app)) == 3
        await pilot.press("escape")
        assert not isinstance(app.screen, SettingsScreen)
        assert app.knob_count == 3


async def test_app_shortcuts_are_suppressed_while_open(offline_app):
    """Otherwise typing a name would nudge knobs and "q" would quit."""
    app = offline_app(3)
    async with app.run_test() as pilot:
        await pilot.press("comma")
        assert app.check_action("nudge", (1,)) is False
        assert app.check_action("quit", ()) is False


async def test_save_applies_names_and_ccs(offline_app):
    app = offline_app(3)
    async with app.run_test() as pilot:
        await pilot.press("comma")
        set_name(rows(app)[0], "Cutoff")
        set_cc(rows(app)[0], 20)
        app.screen.query_one("#save").press()
        await pilot.pause()
        assert [(k.name, k.cc) for k in app.config.knobs][0] == ("Cutoff", 20)


async def test_save_persists_to_disk(offline_app, config_path):
    from pyknobs import config as config_module

    app = offline_app(2)
    async with app.run_test() as pilot:
        await pilot.press("comma")
        set_name(rows(app)[0], "Reso")
        app.screen.query_one("#save").press()
        await pilot.pause()
    assert config_module.load(config_path).knobs[0].name == "Reso"


async def test_values_survive_a_layout_change(offline_app):
    app = offline_app(3)
    async with app.run_test() as pilot:
        await pilot.press("end")           # knob 1 -> 127
        await pilot.press("comma")
        set_name(rows(app)[0], "Cutoff")
        app.screen.query_one("#save").press()
        await pilot.pause()
        assert app.values[0] == 127
        assert len(app._knobs) == 3


async def test_add_and_remove_knob(offline_app):
    app = offline_app(2)
    async with app.run_test() as pilot:
        await pilot.press("comma")
        app.screen.query_one("#add").press()
        await pilot.pause()
        assert len(rows(app)) == 3
        app.screen.query_one("#save").press()
        await pilot.pause()
        assert app.knob_count == 3


async def test_edits_survive_adding_a_knob(offline_app):
    app = offline_app(2)
    async with app.run_test() as pilot:
        await pilot.press("comma")
        set_name(rows(app)[0], "Cutoff")
        app.screen.query_one("#add").press()
        await pilot.pause()
        assert rows(app)[0].query_one(".name-input", Input).value == "Cutoff"


@pytest.mark.parametrize(
    "mutate, fragment",
    [
        (lambda r: set_cc(r[1], 10), "more than one knob"),
        (lambda r: set_cc(r[0], 200), "0"),
        (lambda r: set_cc(r[0], ""), "0"),
    ],
)
async def test_invalid_layouts_are_refused(offline_app, mutate, fragment):
    app = offline_app(3)
    async with app.run_test() as pilot:
        await pilot.press("comma")
        mutate(rows(app))
        app.screen.query_one("#save").press()
        await pilot.pause()
        assert isinstance(app.screen, SettingsScreen), "must stay open on error"
        assert fragment in str(app.screen.query_one("#error").render())


async def test_blank_name_falls_back(offline_app):
    app = offline_app(2)
    async with app.run_test() as pilot:
        await pilot.press("comma")
        set_name(rows(app)[0], "")
        app.screen.query_one("#save").press()
        await pilot.pause()
        assert app.config.knobs[0].name == "Knob 1"


async def test_shortcuts_still_work_after_closing(offline_app):
    app = offline_app(3)
    async with app.run_test() as pilot:
        await pilot.press("comma")
        app.screen.query_one("#cancel").press()
        await pilot.pause()
        await pilot.press("up", "right", "up")
        assert app.values == [1, 1, 0]
