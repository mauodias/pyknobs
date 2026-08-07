"""The Element Lua scripts, exercised with the `el.*` modules stubbed out.

These run the real `element/pyknobs.lua` through a Lua interpreter, so the emit
logic is tested rather than eyeballed. Skipped when no `lua` is installed.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

LUA = shutil.which("lua") or shutil.which("lua5.4") or shutil.which("luajit")
SCRIPT = Path(__file__).resolve().parents[1] / "element" / "pyknobs.lua"

pytestmark = pytest.mark.skipif(LUA is None, reason="no lua interpreter installed")

HARNESS = r"""
package.preload['el.MidiBuffer'] = function() return { new = function()
  local o = {msgs={}}
  o.reserve = function() end
  o.clear   = function(s) s.msgs = {} end
  o.insertPacked = function(s, m) s.msgs[#s.msgs+1] = m end
  o.swap    = function(s, x) s.msgs, x.msgs = x.msgs, s.msgs end
  return o end } end
package.preload['el.midi'] = function() return {
  controller = function(ch, cc, v) return ch .. ":" .. cc .. "=" .. v end } end
package.preload['el.round'] = function() return {
  integer = function(x) return math.floor(x + 0.5) end } end

local S = dofile(SCRIPT_PATH)
local sink = {msgs = {}}
sink.swap = function(s, x) s.msgs, x.msgs = x.msgs, s.msgs end
local m = { get = function() return sink end }
local c, p = {}, {}

S.prepare()
local out = {}
for _, block in ipairs(BLOCKS) do
    sink.msgs = {}
    for i = 1, #block.knobs do p[i] = block.knobs[i] end
    p[9]  = block.sync or 0
    p[10] = block.active or 8
    S.process(nil, m, p, c)
    -- leading "|" keeps empty blocks from vanishing when the
    -- output is split back into lines
    out[#out+1] = "|" .. table.concat(sink.msgs, ",")
end
print(table.concat(out, "\n"))
"""


def run_blocks(blocks: list[dict]) -> list[list[str]]:
    """Run the DSP script over a sequence of blocks; return messages per block."""
    lua_blocks = "{" + ",".join(
        "{knobs={%s}, sync=%s, active=%s}"
        % (
            ",".join(str(v) for v in b["knobs"]),
            b.get("sync", 0),
            b.get("active", 8),
        )
        for b in blocks
    ) + "}"
    program = (
        f'SCRIPT_PATH = {json.dumps(str(SCRIPT))}\nBLOCKS = {lua_blocks}\n' + HARNESS
    )
    result = subprocess.run(
        [LUA, "-"], input=program, capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr
    lines = result.stdout.rstrip("\n").split("\n")
    return [rest.split(",") if (rest := line[1:]) else [] for line in lines]


ZEROS = [0] * 8


def test_first_block_emits_everything():
    """Loading the session pushes current state -- the closest thing to
    asking the host for its values."""
    (first,) = run_blocks([{"knobs": ZEROS}])
    assert first == [f"1:{cc}=0" for cc in range(10, 18)]


def test_unchanged_blocks_emit_nothing():
    _, second = run_blocks([{"knobs": ZEROS}, {"knobs": ZEROS}])
    assert second == []


def test_only_changed_knobs_emit():
    moved = [0.5, 1.0, 0, 0, 0, 0, 0, 0.25]
    _, second = run_blocks([{"knobs": ZEROS}, {"knobs": moved}])
    assert second == ["1:10=64", "1:11=127", "1:17=32"]


def test_sync_resends_everything_at_true_values():
    moved = [0.5, 1.0, 0, 0, 0, 0, 0, 0.25]
    blocks = [{"knobs": ZEROS}, {"knobs": moved}, {"knobs": moved, "sync": 1}]
    *_, third = run_blocks(blocks)
    assert third == [
        "1:10=64", "1:11=127", "1:12=0", "1:13=0",
        "1:14=0", "1:15=0", "1:16=0", "1:17=32",
    ]


def test_sync_works_in_either_direction():
    """The button toggles, so a 1->0 transition must also re-send."""
    blocks = [
        {"knobs": ZEROS, "sync": 0},
        {"knobs": ZEROS, "sync": 1},
        {"knobs": ZEROS, "sync": 0},
    ]
    _, second, third = run_blocks(blocks)
    assert len(second) == 8
    assert len(third) == 8


def test_active_bounds_what_transmits():
    """An unconnected control input reads 0.0 forever; without Active it
    would broadcast a bogus 0 and flatten that knob."""
    (first,) = run_blocks([{"knobs": ZEROS, "active": 2}])
    assert first == ["1:10=0", "1:11=0"]


def test_active_truncates_rather_than_rounds():
    (first,) = run_blocks([{"knobs": ZEROS, "active": 2.97}])
    assert len(first) == 2


@pytest.mark.parametrize("active, expected", [(0, 1), (-5, 1), (99, 8)])
def test_active_is_clamped(active, expected):
    (first,) = run_blocks([{"knobs": ZEROS, "active": active}])
    assert len(first) == expected


def test_values_scale_to_the_full_7_bit_range():
    knobs = [0.0, 1.0, 0.5, 0.25, 0, 0, 0, 0]
    (first,) = run_blocks([{"knobs": knobs}])
    assert first[:4] == ["1:10=0", "1:11=127", "1:12=64", "1:13=32"]
