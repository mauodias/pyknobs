"""MIDI transport for pyknobs.

Talks to the macOS IAC Driver over ``mido``'s ``python-rtmidi`` backend. Output
is a plain blocking send; input is delivered on rtmidi's own thread via a
callback, so the consumer is responsible for hopping back to its UI thread.

Every inbound message is handed upstream unfiltered — deciding what is
interesting is the app's job, so nothing is ever dropped silently.
"""

from __future__ import annotations

from collections.abc import Callable

import mido

from .config import CHANNEL

mido.set_backend("mido.backends.rtmidi")

# The IAC bus as macOS names it. rtmidi decorates port names with a numeric
# suffix ("IAC Driver Bus 1 0"), so ports are matched by prefix, not equality.
PORT_NAME = "IAC Driver Bus 1"


def find_port(names: list[str], port_name: str = PORT_NAME) -> str | None:
    for name in names:
        if name.startswith(port_name):
            return name
    return None


class MidiIO:
    """Bidirectional link to a single MIDI port.

    Opens lazily and degrades to an offline no-op when the port is missing, so
    the TUI still runs when the user has not enabled the IAC Driver yet.
    """

    def __init__(
        self,
        on_message: Callable[[mido.Message], None],
        port_name: str = PORT_NAME,
    ) -> None:
        self._on_message = on_message
        self.port_name = port_name
        self._inport: mido.ports.BaseInput | None = None
        self._outport: mido.ports.BaseOutput | None = None
        self.error: str | None = None

    @property
    def connected(self) -> bool:
        return self._outport is not None or self._inport is not None

    @property
    def status(self) -> str:
        if self._inport and self._outport:
            return f"{self.port_name} — in/out"
        if self._outport:
            return f"{self.port_name} — out only"
        if self._inport:
            return f"{self.port_name} — in only"
        return "offline"

    def port_present(self) -> bool:
        """Whether the port is currently advertised by CoreMIDI."""
        return (
            find_port(mido.get_output_names(), self.port_name) is not None
            or find_port(mido.get_input_names(), self.port_name) is not None
        )

    def open(self) -> None:
        self.error = None
        out_name = find_port(mido.get_output_names(), self.port_name)
        in_name = find_port(mido.get_input_names(), self.port_name)

        if out_name is None and in_name is None:
            self.error = (
                f"{self.port_name!r} not found — enable it in "
                "Audio MIDI Setup ▸ Window ▸ Show MIDI Studio ▸ IAC Driver"
            )
            return

        try:
            if out_name is not None:
                self._outport = mido.open_output(out_name)
            if in_name is not None:
                self._inport = mido.open_input(in_name, callback=self._on_message)
        except OSError as exc:  # port exists but is unavailable
            self.error = f"could not open {self.port_name!r}: {exc}"
            self.close()

    def send(self, control: int, value: int) -> None:
        if self._outport is None:
            return
        self._outport.send(
            mido.Message(
                "control_change",
                channel=CHANNEL,
                control=control,
                value=value,
            )
        )

    def close(self) -> None:
        for port in (self._inport, self._outport):
            if port is not None:
                port.close()
        self._inport = None
        self._outport = None
