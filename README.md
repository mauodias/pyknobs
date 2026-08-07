# pyknobs

> [!IMPORTANT]
> **This project was written entirely by AI.** Every line of code, and this
> README, was produced by Anthropic's Claude (models **Sonnet 5** and
> **Opus 5**) running in **Claude Code**, from a written specification and
> follow-up conversation. No part of it was hand-written by a human. Review it
> accordingly before relying on it for anything that matters.

A virtual MIDI knob controller for macOS. Rotary controls sending **CC on MIDI
channel 1** over the native **IAC Driver Bus 1**, with a live feedback display
for values coming back from the host.

It exists to validate bidirectional MIDI communication, state sync and parameter
mappings in a host — Kushview Element, Reaper, or anything else that speaks
MIDI — *before* committing to building the physical hardware. Turn a virtual
knob, confirm the host receives it; change a parameter in the host, confirm it
comes back and lands on the right control.

## What it does

- 1–16 virtual rotary controls, each on its own MIDI CC, channel 1
- Values edited and displayed **0–100**; the wire stays strictly 7-bit (0–127)
- Live feedback log of everything sent and received, with timestamps
- A raw monitor that shows *why* an inbound message didn't match a knob
- Auto-connect: enable the IAC bus while it's running and it picks it up
- Knobs added, removed and renamed at runtime; layout persists to TOML
- Keyboard and mouse control

## Tech stack

| | |
| --- | --- |
| Language | Python 3.12+ |
| MIDI | [`mido`](https://mido.readthedocs.io) on the `python-rtmidi` backend |
| Transport | macOS IAC Driver (CoreMIDI loopback) |
| TUI | [Textual](https://textual.textualize.io) (Rich for bar rendering) |
| Packaging | [uv](https://docs.astral.sh/uv/), Hatchling |
| Config | TOML via `tomllib` |

## Setup

Enable the loopback bus once:

> Audio MIDI Setup ▸ Window ▸ Show MIDI Studio ▸ double-click **IAC Driver** ▸
> tick **Device is online**, and make sure **Bus 1** exists.

Then:

```sh
uv run pyknobs               # 8 knobs, or whatever your config says
uv run pyknobs --knobs 4     # change the count (1–16); saved on next rename
uv run pyknobs --monitor     # dump every inbound MIDI message, no TUI
```

You can also start the app first. If the bus isn't there it runs in offline
mode, keeps polling, and connects by itself the moment you enable the driver —
no restart. It handles the bus disappearing again the same way.

## Keys

| Key | Action |
| --- | --- |
| `←` `→` / `h` `l` | move between knobs |
| `↑` `↓` / `k` `j` | ±1 |
| `shift+↑` `shift+↓` | ±10 |
| `1`–`9` | jump to a knob |
| `home` / `end` | 0 / 100 |
| `n` | rename the selected knob |
| `+` | add a knob (on the next free CC) |
| `-` | remove the selected knob |
| `m` | toggle the raw MIDI monitor |
| `i` | flip scroll direction (trackpad ↔ wheel mouse) |
| `r` | reset all |
| `q` | quit |

## Mouse

| Gesture | Action |
| --- | --- |
| hover a knob | select it |
| wheel up / down | ±1 on the knob under the pointer |
| shift + wheel | ±10 |
| wheel left / right | pan the rack when it's wider than the terminal |
| click the name | rename that knob |

Scroll direction defaults to matching a macOS trackpad: swipe down, knob goes
down. macOS "natural scrolling" reports a swipe down as a wheel-*up* event, and
the terminal can't tell us which setting you're using — so if you're on a wheel
mouse it'll feel backwards. Press **`i`** to flip it; the choice is saved
(`invert_scroll` in the config).

Vertical wheel is claimed by the knob under the pointer, so it changes the value
rather than panning the rack. Hovering never moves the view — only keyboard
navigation scrolls the selection into sight — so pointing and panning don't
fight each other.

Renaming edits the name in the knob's top border. The existing name starts out
selected — typing replaces it, backspace edits it. `Enter` commits, `Esc`
cancels.

The border shows **6 characters**; longer names are stored in full and displayed
with an ellipsis, and the edit field scrolls to keep the cursor in view. Eight
knobs fit a 96-column terminal — beyond that the rack scrolls.

## Configuration

Knob count, names and CC assignments live in `~/.config/pyknobs/config.toml`,
written whenever you rename and safe to edit by hand:

```toml
[[knobs]]
name = "Cutoff"
cc = 10
```

`--knobs N` sets the starting count: extra knobs get default names and the next
free CC, surplus ones are dropped. `--config PATH` uses a different file, so you
can keep a layout per host project.

You don't have to decide up front, though — `+` and `-` add and remove knobs
while the app is running, and the layout is saved immediately. If there are more
knobs than fit the terminal, the rack scrolls and keeps the selected knob in
view.

## Values

Knobs read and are edited on a **0–100** scale. The wire stays strictly 7-bit:
values are scaled to 0–127 on send and back on receive. The feedback log shows
both — `→ CC10  64 (81)`.

## Feedback loop protection

Incoming control changes update local state and the display only; they are never
echoed back to the host, so host and simulator can't drive each other in a loop.

IAC Bus 1 is also a *loopback* — anything sent to it arrives back on our own
input. Values we just sent are recognised and ignored for half a second, so our
own echo isn't misreported as a host update.

## When the host's updates don't show up

Nothing inbound is dropped silently. Press `m` for the raw monitor and every
message that arrives is logged, including the ones that don't match a knob, with
the reason:

```
· control_change ch6 control=11 value=64 — channel 6, expected 1
· control_change ch1 control=99 value=64 — CC99 is not mapped to a knob
· note_on ch1 note=60 velocity=100 — not a control_change
· control_change ch1 control=10 value=1 — our own echo
```

That splits the problem in two:

- **Lines appear** → the host is talking; it's a channel or CC mismatch. Remap
  the knob's `cc` in the config, or point the host at channel 1.
- **Nothing at all** → nothing is reaching the IAC bus, so the problem is
  upstream in the host. `uv run pyknobs --monitor` confirms this independently
  of the TUI.

Note that hosts generally do not emit CC for parameter changes automatically —
they need to be explicitly routed to a MIDI output device (the IAC bus).
