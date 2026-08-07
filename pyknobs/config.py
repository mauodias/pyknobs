"""Persisted knob layout: how many knobs, what they're called, which CC each sends."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PATH = Path.home() / ".config" / "pyknobs" / "config.toml"

DEFAULT_KNOB_COUNT = 8
FIRST_CC = 10
CHANNEL = 0  # MIDI channel 1, zero-indexed on the wire
MIDI_MAX = 127  # standard 7-bit unsigned range is 0..127

MAX_KNOBS = 16  # a full CC row; beyond this the bars stop being readable


@dataclass
class KnobSpec:
    name: str
    cc: int


@dataclass
class Config:
    knobs: list[KnobSpec]
    path: Path = DEFAULT_PATH
    # macOS "natural scrolling" (on by default for trackpads) sends a wheel-UP
    # event when you swipe down, which would raise the knob you just pushed
    # down. Inverting matches the trackpad; turn it off for a wheel mouse.
    invert_scroll: bool = True

    @property
    def cc_numbers(self) -> tuple[int, ...]:
        return tuple(knob.cc for knob in self.knobs)

    def index_for_cc(self, cc: int) -> int | None:
        for index, knob in enumerate(self.knobs):
            if knob.cc == cc:
                return index
        return None

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Bare keys must precede any [[table]], or they'd land inside it.
        lines = [
            "# pyknobs knob layout\n\n",
            "# true suits a macOS trackpad (natural scrolling); set false for a wheel mouse\n",
            f"invert_scroll = {str(self.invert_scroll).lower()}\n\n",
        ]
        for knob in self.knobs:
            lines.append("[[knobs]]\n")
            lines.append(f"name = {_toml_string(knob.name)}\n")
            lines.append(f"cc = {knob.cc}\n\n")
        self.path.write_text("".join(lines))


def _toml_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def next_free_cc(used: set[int]) -> int:
    return next(c for c in range(FIRST_CC, 128) if c not in used)


def default_knobs(count: int) -> list[KnobSpec]:
    return [KnobSpec(name=f"Knob {i + 1}", cc=FIRST_CC + i) for i in range(count)]


def load(path: Path = DEFAULT_PATH, count: int | None = None) -> Config:
    """Load the layout, falling back to defaults.

    `count` (from --knobs) wins over the file: extra knobs are appended with
    default names and the next free CC, surplus ones are dropped.
    """
    knobs: list[KnobSpec] = []
    invert_scroll = True
    if path.exists():
        data = tomllib.loads(path.read_text())
        invert_scroll = bool(data.get("invert_scroll", True))
        for entry in data.get("knobs", []):
            knobs.append(
                KnobSpec(
                    name=str(entry.get("name", "")) or f"Knob {len(knobs) + 1}",
                    cc=int(entry.get("cc", FIRST_CC + len(knobs))),
                )
            )

    if not knobs:
        knobs = default_knobs(count or DEFAULT_KNOB_COUNT)
    elif count is not None and count != len(knobs):
        if count < len(knobs):
            knobs = knobs[:count]
        else:
            used = {knob.cc for knob in knobs}
            while len(knobs) < count:
                cc = next_free_cc(used)
                used.add(cc)
                knobs.append(KnobSpec(name=f"Knob {len(knobs) + 1}", cc=cc))

    return Config(knobs=knobs[:MAX_KNOBS], path=path, invert_scroll=invert_scroll)
