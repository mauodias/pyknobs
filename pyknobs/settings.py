"""The settings modal: knob layout and MIDI port selection.

Everything here is also reachable through the main-screen shortcuts (`n`, `+`,
`-`, `i`). This view exists so none of it has to be memorised, and so the port
choice has somewhere to live that isn't a command-line flag.
"""

from __future__ import annotations

from dataclasses import dataclass

import mido
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Static

from .config import MAX_KNOBS, Config, KnobSpec, next_free_cc
from .midi import PORT_NAME

NAME_MAX = 12


@dataclass
class Settings:
    """What the modal hands back when saved."""

    knobs: list[KnobSpec]
    in_port: str
    out_port: str


def port_options(names: list[str], current: str = "") -> list[tuple[str, str]]:
    """Dropdown options for a port picker.

    Always includes `current` even when CoreMIDI isn't reporting it — a bus
    that's been switched off in Audio MIDI Setup since the setting was saved
    would otherwise be an illegal value and take the whole screen down.
    """
    seen = [n for n in dict.fromkeys([*names, PORT_NAME, current]) if n]
    return [(name, name) for name in seen]


class KnobRow(Horizontal):
    """One editable knob: name and CC number."""

    def __init__(self, index: int, spec: KnobSpec) -> None:
        super().__init__(classes="knob-row")
        self.index = index
        self.spec = spec

    def compose(self) -> ComposeResult:
        yield Label(f"{self.index + 1}.", classes="row-num")
        yield Input(
            value=self.spec.name,
            placeholder="name",
            max_length=NAME_MAX,
            classes="name-input",
        )
        yield Input(
            value=str(self.spec.cc),
            placeholder="cc",
            type="integer",
            max_length=3,
            classes="cc-input",
        )
        yield Button("✕", classes="drop", variant="error")

    @property
    def name_value(self) -> str:
        return self.query_one(".name-input", Input).value.strip()

    @property
    def cc_value(self) -> int | None:
        raw = self.query_one(".cc-input", Input).value.strip()
        if not raw.isdigit():
            return None
        cc = int(raw)
        return cc if 0 <= cc <= 127 else None


class SettingsScreen(ModalScreen[Settings | None]):
    """Edit the knob layout and MIDI ports."""

    BINDINGS = [
        ("escape", "cancel", "cancel"),
        ("ctrl+s", "save", "save"),
    ]

    CSS = """
    SettingsScreen {
        align: center middle;
        background: $background 60%;
    }

    #panel {
        width: 62;
        max-height: 90%;
        background: #16161f;
        border: round #f472b6;
        border-title-color: #f9a8d4;
        border-title-style: bold;
        padding: 1 2;
    }

    .section {
        color: #6b7280;
        margin: 1 0 0 0;
    }

    #ports Label {
        width: 10;
        color: #9ca3af;
    }

    #ports Horizontal {
        height: 3;
    }

    Select {
        width: 1fr;
    }

    #knobs {
        height: auto;
        max-height: 16;
        margin: 0 0 1 0;
    }

    .knob-row {
        height: 3;
    }

    .row-num {
        width: 4;
        color: #6b7280;
        content-align: right middle;
        padding: 1 1 0 0;
    }

    .name-input { width: 1fr; }
    .cc-input   { width: 8; }
    .drop       { width: 5; min-width: 5; }

    #error {
        color: #f87171;
        height: auto;
    }

    #buttons {
        height: 3;
        align: right middle;
    }

    #buttons Button {
        margin: 0 0 0 1;
    }
    """

    def __init__(self, config: Config, in_port: str, out_port: str) -> None:
        super().__init__()
        self.config = config
        self.start_in = in_port
        self.start_out = out_port
        self.specs = [KnobSpec(k.name, k.cc) for k in config.knobs]

    def compose(self) -> ComposeResult:
        with Vertical(id="panel"):
            yield Label("MIDI ports", classes="section")
            with Vertical(id="ports"):
                with Horizontal():
                    yield Label("Output")
                    yield Select(
                        port_options(mido.get_output_names(), self.start_out),
                        value=self.start_out,
                        allow_blank=False,
                        id="out-port",
                    )
                with Horizontal():
                    yield Label("Input")
                    yield Select(
                        port_options(mido.get_input_names(), self.start_in),
                        value=self.start_in,
                        allow_blank=False,
                        id="in-port",
                    )

            yield Label("Knobs", classes="section")
            yield VerticalScroll(id="knobs")
            with Horizontal(id="buttons"):
                yield Button("Add knob", id="add")
                yield Button("Cancel", id="cancel")
                yield Button("Save", id="save", variant="primary")
            yield Static("", id="error")

    def on_mount(self) -> None:
        self.query_one("#panel").border_title = "Settings"
        self._rebuild_rows()

    def _rebuild_rows(self) -> None:
        rows = self.query_one("#knobs", VerticalScroll)
        rows.remove_children()
        rows.mount_all([KnobRow(i, spec) for i, spec in enumerate(self.specs)])

    def _collect(self) -> Settings | None:
        """Read the rows back, or report the first problem and return None."""
        specs: list[KnobSpec] = []
        used: set[int] = set()

        for row in self.query(KnobRow):
            cc = row.cc_value
            if cc is None:
                return self._fail(f"knob {row.index + 1}: CC must be 0–127")
            if cc in used:
                return self._fail(f"CC {cc} is assigned to more than one knob")
            used.add(cc)
            specs.append(KnobSpec(row.name_value or f"Knob {row.index + 1}", cc))

        if not specs:
            return self._fail("at least one knob is required")

        return Settings(
            knobs=specs,
            in_port=self.query_one("#in-port", Select).value,
            out_port=self.query_one("#out-port", Select).value,
        )

    def _fail(self, message: str) -> None:
        self.query_one("#error", Static).update(f"! {message}")
        return None

    # -- actions --------------------------------------------------------

    @on(Button.Pressed, "#add")
    def add_knob(self) -> None:
        if len(self.specs) >= MAX_KNOBS:
            self._fail(f"{MAX_KNOBS} knobs is the limit")
            return
        # Keep edits in flight rather than discarding them on a rebuild.
        current = self._collect()
        self.specs = list(current.knobs) if current else self.specs
        self.specs.append(
            KnobSpec(
                name=f"Knob {len(self.specs) + 1}",
                cc=next_free_cc({s.cc for s in self.specs}),
            )
        )
        self._rebuild_rows()

    @on(Button.Pressed, ".drop")
    def drop_knob(self, event: Button.Pressed) -> None:
        if len(self.specs) <= 1:
            self._fail("at least one knob is required")
            return
        row = event.button.ancestors_with_self[1]
        assert isinstance(row, KnobRow)
        current = self._collect()
        self.specs = list(current.knobs) if current else self.specs
        del self.specs[row.index]
        self._rebuild_rows()

    @on(Button.Pressed, "#save")
    def action_save(self) -> None:
        if (settings := self._collect()) is not None:
            self.dismiss(settings)

    @on(Button.Pressed, "#cancel")
    def action_cancel(self) -> None:
        self.dismiss(None)
