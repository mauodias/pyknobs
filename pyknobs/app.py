"""pyknobs — a virtual MIDI knob controller for the macOS IAC Driver."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from time import monotonic

import mido
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import HorizontalScroll
from textual.widgets import Footer, Header, RichLog

from . import config as config_module
from .config import CHANNEL, MAX_KNOBS, Config
from .knob import Knob
from .midi import PORT_NAME, MidiIO

# Knob values are edited and displayed on a 0–100 scale; the wire stays strictly
# 7-bit, so every value is scaled on the way in and out.
DISPLAY_MAX = 100
MIDI_MAX = 127

NAME_MAX = 12

# How long after sending a value an identical inbound one counts as our own
# loopback echo rather than a genuine host update.
ECHO_WINDOW = 0.5


def to_midi(value: int) -> int:
    return round(value * MIDI_MAX / DISPLAY_MAX)


def to_display(value: int) -> int:
    return round(value * DISPLAY_MAX / MIDI_MAX)


def describe(message: mido.Message) -> str:
    """Compact one-line rendering of any MIDI message, for the raw log."""
    parts = [message.type]
    if hasattr(message, "channel"):
        parts.append(f"ch{message.channel + 1}")
    for field in ("control", "note", "program", "value", "velocity", "pitch"):
        if hasattr(message, field):
            parts.append(f"{field}={getattr(message, field)}")
    return " ".join(parts)


class PyKnobs(App[None]):
    TITLE = "pyknobs"
    SUB_TITLE = "virtual MIDI knob controller"

    CSS = """
    Screen {
        background: #12121a;
    }

    #rack {
        height: 20;
        align: center middle;
        padding: 1 0;
        scrollbar-size: 1 1;
        scrollbar-color: #3f3f52;
        scrollbar-color-hover: #6b7280;
    }

    /* Fixed width: knobs stay readable and the rack scrolls when there are
       more of them than fit, rather than shrinking into illegibility. */
    Knob {
        width: 10;
        height: 17;
        margin: 0 1;
        content-align: center middle;
        border: round #3f3f52;
        border-title-align: center;
        border-subtitle-align: center;
        border-title-color: #9ca3af;
        border-subtitle-color: #6b7280;
    }

    Knob.-active {
        border: round #f472b6;
        border-title-color: #f9a8d4;
        border-title-style: bold;
        border-subtitle-color: #f9a8d4;
        background: #1c1c28;
    }

    Knob.-editing {
        border: round #facc15;
        border-title-color: #fde047;
        border-title-style: bold;
    }

    #log {
        height: 1fr;
        min-height: 6;
        margin: 0 2 1 2;
        padding: 0 1;
        background: #16161f;
        border: round #3f3f52;
        border-title-color: #6b7280;
        border-subtitle-color: #4b5563;
        scrollbar-size: 1 1;
    }
    """

    # priority=True so the arrow keys reach the knobs instead of Textual's
    # default focus/scroll navigation.
    BINDINGS = [
        Binding("left,h", "select(-1)", "prev knob", priority=True),
        Binding("right,l", "select(1)", "next knob", priority=True),
        Binding("up,k", "nudge(1)", "+1", priority=True),
        Binding("down,j", "nudge(-1)", "-1", priority=True),
        Binding("shift+up,K", "nudge(10)", "+10", priority=True),
        Binding("shift+down,J", "nudge(-10)", "-10", priority=True),
        Binding("home", "set_value(0)", "min", priority=True),
        Binding("end", "set_value(100)", "max", priority=True),
        Binding("n", "rename", "rename", priority=True),
        Binding("plus,equals_sign,=,+", "add_knob", "add knob", priority=True),
        Binding("minus,-", "remove_knob", "drop knob", priority=True),
        Binding("r", "reset", "reset all", priority=True),
        Binding("m", "toggle_raw", "raw monitor", priority=True),
        Binding("i", "toggle_scroll", "invert scroll", priority=True),
        Binding("q", "quit", "quit", priority=True),
    ]

    def __init__(self, config: Config | None = None, raw: bool = False) -> None:
        super().__init__()
        self.config = config or config_module.load()
        self.values = [0] * len(self.config.knobs)
        self.cursor = 0
        self._knobs: list[Knob] = []
        self.raw = raw
        self.renaming: int | None = None
        self._rename_fresh = False
        # IAC Bus 1 is a loopback: everything we send arrives back on our own
        # input. Remember what we just sent so the echo isn't mistaken for the
        # host talking to us.
        self._sent: dict[int, tuple[int, float]] = {}
        self.midi = MidiIO(self._on_midi_thread)

    @property
    def knob_count(self) -> int:
        return len(self.config.knobs)

    # -- layout ---------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header()
        self._knobs = [Knob(spec.cc, spec.name) for spec in self.config.knobs]
        with HorizontalScroll(id="rack"):
            yield from self._knobs
        yield RichLog(id="log", markup=True, max_lines=1000)
        yield Footer()

    def on_mount(self) -> None:
        log = self.query_one("#log", RichLog)
        log.border_title = "feedback"
        # Nothing on screen should take focus; the app owns every key.
        log.can_focus = False
        self._refresh_raw_hint()
        for index in range(self.knob_count):
            self._knob(index).value = self.values[index]
        self._refresh_cursor()

        self._connect(announce_failure=True)
        # The IAC bus can be enabled (or switched off) in Audio MIDI Setup while
        # the app is running, so keep watching for it either way.
        self.set_interval(2.0, self._poll_port)

    def on_unmount(self) -> None:
        self.midi.close()

    def _knob(self, index: int) -> Knob:
        return self._knobs[index]

    def _refresh_cursor(self, *, scroll: bool = True) -> None:
        for index in range(self.knob_count):
            self._knob(index).active = index == self.cursor
        if scroll:
            # Keep the selection on screen when the rack is wider than the
            # terminal. Skipped for pointer selection: the knob is already under
            # the pointer, and snapping would fight a horizontal pan.
            self._knob(self.cursor).scroll_visible(animate=False)

    def _refresh_raw_hint(self) -> None:
        state = "on" if self.raw else "off"
        self.query_one("#log", RichLog).border_subtitle = f"raw monitor: {state} (m)"

    def _log(self, markup: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.query_one("#log", RichLog).write(f"[#4b5563]{stamp}[/] {markup}")

    # -- connection -----------------------------------------------------

    def _connect(self, *, announce_failure: bool) -> None:
        self.midi.open()
        if self.midi.error:
            self.sub_title = "offline — waiting for IAC port"
            if announce_failure:
                self._log(f"[#f87171]![/] {self.midi.error}")
                self._log("[#4b5563]  watching for it — no need to restart[/]")
        else:
            self.sub_title = self.midi.status
            self._log(f"[#34d399]●[/] connected to [b]{self.midi.status}[/]")

    def _poll_port(self) -> None:
        present = self.midi.port_present()
        if self.midi.connected and not present:
            self.midi.close()
            self.sub_title = "offline — waiting for IAC port"
            self._log("[#f87171]○[/] IAC port went away")
        elif not self.midi.connected and present:
            self._connect(announce_failure=False)

    # -- actions --------------------------------------------------------

    def check_action(self, action: str, parameters) -> bool:
        # While renaming, every keystroke belongs to the text field — including
        # "q" and "n". Escape is the way out.
        return self.renaming is None

    def action_select(self, delta: int) -> None:
        self.cursor = (self.cursor + delta) % self.knob_count
        self._refresh_cursor()

    def action_nudge(self, delta: int) -> None:
        self.action_set_value(self.values[self.cursor] + delta)

    def action_set_value(self, value: int) -> None:
        self._apply(self.cursor, value, transmit=True)

    async def action_add_knob(self) -> None:
        if self.knob_count >= MAX_KNOBS:
            self._log(f"[#f87171]![/] {MAX_KNOBS} knobs is the limit")
            return
        spec = config_module.KnobSpec(
            name=f"Knob {self.knob_count + 1}",
            cc=config_module.next_free_cc(set(self.config.cc_numbers)),
        )
        self.config.knobs.append(spec)
        self.values.append(0)
        knob = Knob(spec.cc, spec.name)
        self._knobs.append(knob)
        await self.query_one("#rack", HorizontalScroll).mount(knob)
        self.cursor = self.knob_count - 1
        self._refresh_cursor()
        self.config.save()
        self._log(f"[#34d399]+[/] added [b]{spec.name}[/] on CC[b]{spec.cc}[/]")

    async def action_remove_knob(self) -> None:
        if self.knob_count <= 1:
            self._log("[#f87171]![/] one knob has to stay")
            return
        index = self.cursor
        spec = self.config.knobs.pop(index)
        self.values.pop(index)
        knob = self._knobs.pop(index)
        await knob.remove()
        self._sent.pop(spec.cc, None)
        self.cursor = min(index, self.knob_count - 1)
        self._refresh_cursor()
        self.config.save()
        self._log(f"[#f87171]−[/] removed [b]{spec.name}[/] (CC{spec.cc})")

    def action_reset(self) -> None:
        for index in range(self.knob_count):
            self._apply(index, 0, transmit=True)

    def action_toggle_raw(self) -> None:
        self.raw = not self.raw
        self._refresh_raw_hint()
        self._log(
            "[#facc15]~[/] raw monitor [b]on[/] — logging every inbound message"
            if self.raw
            else "[#4b5563]~ raw monitor off[/]"
        )

    def action_toggle_scroll(self) -> None:
        self.config.invert_scroll = not self.config.invert_scroll
        self.config.save()
        which = "trackpad" if self.config.invert_scroll else "wheel mouse"
        self._log(f"[#facc15]⇅[/] scroll direction: [b]{which}[/]")

    def action_rename(self) -> None:
        self.renaming = self.cursor
        knob = self._knob(self.cursor)
        knob.editing = knob.knob_name
        # The current name starts out "selected": the first character typed
        # replaces it, but backspace drops into editing it instead.
        self._rename_fresh = True

    def _finish_rename(self, *, commit: bool) -> None:
        assert self.renaming is not None
        knob = self._knob(self.renaming)
        if commit:
            name = (knob.editing or "").strip() or f"Knob {self.renaming + 1}"
            self.config.knobs[self.renaming].name = name
            knob.knob_name = name
            self.config.save()
            self._log(f"[#facc15]✎[/] CC[b]{knob.cc}[/] renamed to [b]{name}[/]")
        knob.editing = None
        self.renaming = None

    def on_key(self, event) -> None:
        if self.renaming is not None:
            self._rename_key(event)
            return
        if event.key.isdigit():
            index = (int(event.key) - 1) % 10
            if index < self.knob_count:
                self.cursor = index
                self._refresh_cursor()
                event.stop()

    def _rename_key(self, event) -> None:
        event.stop()
        event.prevent_default()
        knob = self._knob(self.renaming)
        if event.key == "enter":
            self._finish_rename(commit=True)
        elif event.key == "escape":
            self._finish_rename(commit=False)
        elif event.key == "backspace":
            self._rename_fresh = False
            knob.editing = (knob.editing or "")[:-1]
        elif event.is_printable:
            current = "" if self._rename_fresh else (knob.editing or "")
            self._rename_fresh = False
            if len(current) < NAME_MAX:
                knob.editing = current + event.character

    # -- mouse ----------------------------------------------------------

    def _point_at(self, knob: Knob) -> int | None:
        """Move the cursor to `knob`, unless a rename is in progress."""
        if self.renaming is not None:
            return None
        index = self._knobs.index(knob)
        if index != self.cursor:
            self.cursor = index
            self._refresh_cursor(scroll=False)
        return index

    def on_knob_selected(self, message: Knob.Selected) -> None:
        self._point_at(message.knob)

    def on_knob_nudged(self, message: Knob.Nudged) -> None:
        index = self._point_at(message.knob)
        if index is not None:
            delta = -message.delta if self.config.invert_scroll else message.delta
            self._apply(index, self.values[index] + delta, transmit=True)

    def on_knob_rename_requested(self, message: Knob.RenameRequested) -> None:
        if self._point_at(message.knob) is not None:
            self.action_rename()

    # -- state ----------------------------------------------------------

    def _apply(self, index: int, value: int, *, transmit: bool) -> None:
        value = max(0, min(DISPLAY_MAX, value))
        if value == self.values[index]:
            return
        self.values[index] = value
        self._knob(index).value = value
        if transmit:
            midi_value = to_midi(value)
            cc = self.config.knobs[index].cc
            self._sent[cc] = (midi_value, monotonic())
            self.midi.send(cc, midi_value)
            self._log(
                f"[#22d3ee]→[/] CC[b]{cc}[/]"
                f" [#e5e7eb]{value:>3}[/] [#4b5563]({midi_value})[/]"
            )

    def _on_midi_thread(self, message: mido.Message) -> None:
        """Called on rtmidi's thread; hand off to the UI thread."""
        self.call_from_thread(self._on_incoming, message)

    def _on_incoming(self, message: mido.Message) -> None:
        index = None
        reason = None

        if message.type != "control_change":
            reason = "not a control_change"
        elif message.channel != CHANNEL:
            reason = f"channel {message.channel + 1}, expected {CHANNEL + 1}"
        else:
            index = self.config.index_for_cc(message.control)
            if index is None:
                reason = f"CC{message.control} is not mapped to a knob"

        if index is None:
            # Nothing is dropped silently: unmapped traffic is still evidence
            # that the host is talking to us at all.
            if self.raw:
                self._log(f"[#4b5563]·[/] [#6b7280]{describe(message)} — {reason}[/]")
            return

        sent = self._sent.get(message.control)
        if sent and sent[0] == message.value and monotonic() - sent[1] < ECHO_WINDOW:
            del self._sent[message.control]
            if self.raw:
                self._log(f"[#4b5563]·[/] [#6b7280]{describe(message)} — our own echo[/]")
            return

        display = to_display(message.value)
        # transmit=False is the feedback-loop guard: host updates change local
        # state and the display, but are never echoed back out.
        self._apply(index, display, transmit=False)
        self._log(
            f"[#f472b6]←[/] CC[b]{message.control}[/]"
            f" [#e5e7eb]{display:>3}[/] [#4b5563]({message.value}) host[/]"
        )


def monitor(port_name: str = PORT_NAME) -> None:
    """Print every message arriving on the port. No filtering, no TUI."""
    print(f"inputs:  {mido.get_input_names()}")
    print(f"outputs: {mido.get_output_names()}\n")

    from .midi import find_port

    name = find_port(mido.get_input_names(), port_name)
    if name is None:
        print(f"No input matching {port_name!r}. Nothing to listen to.")
        return

    print(f"Listening on {name!r}. Move a control in the host. Ctrl-C to stop.\n")
    with mido.open_input(name) as port:
        try:
            for message in port:
                stamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                print(f"{stamp}  {describe(message)}")
        except KeyboardInterrupt:
            print("\nstopped")


def main() -> None:
    parser = argparse.ArgumentParser(prog="pyknobs", description=__doc__)
    parser.add_argument(
        "-k", "--knobs", type=int, help=f"number of knobs (1–{MAX_KNOBS})"
    )
    parser.add_argument(
        "-c", "--config", type=Path, default=config_module.DEFAULT_PATH,
        help="path to the knob layout file",
    )
    parser.add_argument(
        "-m", "--monitor", action="store_true",
        help="dump every inbound MIDI message to stdout instead of running the TUI",
    )
    parser.add_argument(
        "--raw", action="store_true", help="start with the raw monitor pane enabled"
    )
    args = parser.parse_args()

    if args.monitor:
        monitor()
        return

    if args.knobs is not None and not 1 <= args.knobs <= MAX_KNOBS:
        parser.error(f"--knobs must be between 1 and {MAX_KNOBS}")

    config = config_module.load(args.config, args.knobs)
    PyKnobs(config, raw=args.raw).run()


if __name__ == "__main__":
    main()
