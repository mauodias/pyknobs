# Specification: Python Virtual MIDI Controller Simulator

## Goal
Build a lightweight Python application on macOS to simulate a physical MIDI knob controller. This tool validates bidirectional MIDI communication, state sync, and parameter mappings in host applications (like Kushview Element or Reaper) via the macOS IAC Driver before building hardware.

## Architecture & Requirements

### 1. Environment & I/O
* **Dependencies:** `mido` using the `python-rtmidi` backend.
* **MIDI Port Configuration:** Connect to the native macOS `IAC Driver Bus 1` for both input and output streams.

### 2. Controller Output (Simulating Physical Knobs)
* **Control Count:** 8 virtual rotary controls mapped to MIDI CC #10 through #17 on MIDI Channel 1 (0-indexed: Channel 0 in raw bytes).
* **Data Range:** Strictly standard 7-bit unsigned integers ($0$ to $127$).
* **Transmission Logic:** Emit real-time `control_change` messages to the IAC output stream upon value changes.

### 3. Controller Input (Simulating Hardware Feedback Displays)
* **Feedback Listener:** Asynchronously process incoming `control_change` messages from the IAC input stream (emulating host parameter updates).
* **State Logging:** Print received parameter updates to `stdout` (displaying Timestamp, CC Number, and Value).
* **Feedback Loop Protection:** Suppress outbound echo for incoming messages to prevent infinite processing loops between host and simulator.

### 4. Terminal User Interface (TUI) & Navigation
* **Visuals:** Render 8 vertical progress/level bars representing the $0$ to $127$ value range of each knob.
* **Navigation:**
  * Use horizontal movement (`Left`/`Right` or `h`/`l`) to move focus between knobs.
  * Use vertical movement (`Up`/`Down` or `k`/`j`) to increment or decrement the active knob's value.
  * Highlight the currently active/selected knob visually.
  * Make it a nice and beautiful TUI application. Use libraries if needed
