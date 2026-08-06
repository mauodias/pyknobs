"""The vertical bar widget for a single virtual knob."""

from __future__ import annotations

from rich.text import Text
from textual import events
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Static

BAR_ROWS = 14
BAR_WIDTH = 5

# Bottom-to-top colour ramp for the bar. Interpolated per row, so the number of
# rows can change without touching the palette.
GRADIENT = (
    "#22d3ee",  # cyan
    "#34d399",  # green
    "#facc15",  # yellow
    "#fb923c",  # orange
    "#f472b6",  # pink
)

TRACK_COLOR = "#2a2a3a"
EIGHTHS = " ▁▂▃▄▅▆▇"


def _lerp_hex(a: str, b: str, t: float) -> str:
    ar, ag, ab = (int(a[i : i + 2], 16) for i in (1, 3, 5))
    br, bg, bb = (int(b[i : i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % (
        round(ar + (br - ar) * t),
        round(ag + (bg - ag) * t),
        round(ab + (bb - ab) * t),
    )


def _row_color(row: int, rows: int) -> str:
    """Colour for `row`, counting 0 at the bottom of the bar."""
    span = (len(GRADIENT) - 1) * (row / max(rows - 1, 1))
    lo = min(int(span), len(GRADIENT) - 2)
    return _lerp_hex(GRADIENT[lo], GRADIENT[lo + 1], span - lo)


class Knob(Static):
    """One knob: its name, a gradient level bar, its 0–100 readout, its CC."""

    value: reactive[int] = reactive(0)
    active: reactive[bool] = reactive(False)
    knob_name: reactive[str] = reactive("")
    editing: reactive[str | None] = reactive(None)

    class Selected(Message):
        """The pointer moved over this knob."""

        def __init__(self, knob: Knob) -> None:
            self.knob = knob
            super().__init__()

    class Nudged(Message):
        """The wheel turned over this knob."""

        def __init__(self, knob: Knob, delta: int) -> None:
            self.knob = knob
            self.delta = delta
            super().__init__()

    class RenameRequested(Message):
        """The name in the top border was clicked."""

        def __init__(self, knob: Knob) -> None:
            self.knob = knob
            super().__init__()

    def __init__(self, cc: int, name: str) -> None:
        # No id: knobs are added and removed at runtime, so the app tracks them
        # by position in its own list rather than by a name baked into the DOM.
        super().__init__()
        self.cc = cc
        self.set_reactive(Knob.knob_name, name)

    def on_mount(self) -> None:
        self._sync_titles()

    def _sync_titles(self) -> None:
        if self.editing is None:
            self.border_title = self.knob_name
        else:
            # Block cursor makes it obvious the border has become a text field.
            self.border_title = f"{self.editing}█"
        self.border_subtitle = f"CC{self.cc}"

    def watch_knob_name(self) -> None:
        self._sync_titles()

    def watch_editing(self, editing: str | None) -> None:
        self.set_class(editing is not None, "-editing")
        self._sync_titles()

    def watch_value(self) -> None:
        self.refresh()

    def watch_active(self, active: bool) -> None:
        self.set_class(active, "-active")
        self.refresh()

    # -- mouse ----------------------------------------------------------

    def on_enter(self, event: events.Enter) -> None:
        self.post_message(self.Selected(self))

    def _scroll(self, event: events.MouseScrollDown | events.MouseScrollUp, sign: int) -> None:
        # Claim vertical wheel events so they adjust the value instead of
        # bubbling up to the rack and panning it sideways.
        event.stop()
        event.prevent_default()
        self.post_message(self.Nudged(self, sign * (10 if event.shift else 1)))

    def on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        self._scroll(event, 1)

    def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        self._scroll(event, -1)

    def on_click(self, event: events.Click) -> None:
        if event.y == 0:  # the top border row, where the name is drawn
            event.stop()
            self.post_message(self.RenameRequested(self))

    def render(self) -> Text:
        filled = self.value / 100 * BAR_ROWS
        whole = int(filled)
        remainder = filled - whole

        text = Text(no_wrap=True)
        for row in reversed(range(BAR_ROWS)):
            color = _row_color(row, BAR_ROWS)
            if row < whole:
                text.append("█" * BAR_WIDTH, style=color)
            elif row == whole and remainder > 0:
                partial = EIGHTHS[int(remainder * 8)]
                text.append(partial * BAR_WIDTH, style=f"{color} on {TRACK_COLOR}")
            else:
                text.append("░" * BAR_WIDTH, style=TRACK_COLOR)
            text.append("\n")

        style = _row_color(min(whole, BAR_ROWS - 1), BAR_ROWS) if self.value else "#6b7280"
        text.append(f" {self.value:>3} ", style=f"bold {style}")
        return text
