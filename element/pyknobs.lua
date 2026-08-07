--- pyknobs feedback.
--
-- Eight normalized values (0.0 - 1.0) in, eight MIDI CC streams out on
-- CC 10-17, channel 1 -- the layout pyknobs expects by default. Connect a
-- plugin parameter to each "Knob N" input; a CC is emitted only when the
-- scaled 0-127 value changes.
--
-- Because every value starts at -1, the first processed block always emits
-- all eight, so loading the session pushes current state to the controller.
--
-- The "Sync" input re-sends everything on demand: any change to it forgets
-- the cached values, so the next block emits all eight at their true current
-- value. That is what the companion `pyknobsui` Sync button toggles -- MIDI
-- can't be emitted from a UI script, only from here.
--
-- Derived from Kushview's `midicc` script by Michael Fisher.
--
-- @script      pyknobs
-- @type        DSP
-- @license     GPL v3

local MidiBuffer = require ('el.MidiBuffer')
local midi       = require ('el.midi')
local round      = require ('el.round')

local COUNT    = 8
local FIRST_CC = 10
local CHANNEL  = 1
local SYNC     = COUNT + 1 -- the Sync input sits after the eight knobs
local ACTIVE   = COUNT + 2

local output    = MidiBuffer.new()
local lastValue = {}
local lastSync  = nil

local function forgetAll()
    -- -1 is unreachable for a 0-127 value, so every knob emits on the
    -- next block regardless of where it sits.
    for i = 1, COUNT do
        lastValue[i] = -1
    end
end

local function layout()
    local inputs, outputs = {}, {}

    for i = 1, COUNT do
        local cc = FIRST_CC + i - 1
        inputs[i] = {
            name    = string.format ("Knob %d", i),
            symbol  = string.format ("knob%d", i),
            min     = 0.0,
            max     = 1.0,
            default = 0.0
        }
        outputs[i] = {
            name    = string.format ("CC%d", cc),
            symbol  = string.format ("cc%d", cc),
            min     = 0,
            max     = 127,
            default = 0
        }
    end

    inputs[SYNC] = {
        name    = "Sync",
        symbol  = "sync",
        min     = 0.0,
        max     = 1.0,
        default = 0.0
    }

    -- Lua can't see whether a control port is connected, and an unconnected
    -- input reads 0.0 forever -- which would broadcast a bogus 0 and flatten
    -- that knob on the controller. Only knobs 1..Active are transmitted.
    inputs[ACTIVE] = {
        name    = "Active",
        symbol  = "active",
        min     = 1,
        max     = COUNT,
        default = COUNT
    }

    return {
        audio   = { 0, 0 },
        midi    = { 0, 1 },
        control = { inputs, outputs }
    }
end

local function prepare()
    output:reserve (COUNT * 8)
    output:clear()
    forgetAll()
    lastSync = nil
end

local function process (_, m, p, c)
    local out = m:get (1)
    output:clear()

    -- Any movement of the Sync input -- in either direction -- means
    -- "re-send everything", so a toggling button works without caring
    -- which way it flipped.
    local sync = p[SYNC]
    if lastSync ~= nil and sync ~= lastSync then
        forgetAll()
    end
    lastSync = sync

    -- Truncate rather than round: the editor's slider is a float, so 3.97
    -- means "3 knobs" until it actually reaches 4.
    local active = math.floor (p[ACTIVE])
    if active < 1 then active = 1 elseif active > COUNT then active = COUNT end

    for i = 1, COUNT do
        local value = round.integer (p[i] * 127)

        -- Expose the scaled value as a control output.
        c[i] = value

        -- Only emit a message when the scaled value changes.
        if i <= active and value ~= lastValue[i] then
            output:insertPacked (midi.controller (CHANNEL, FIRST_CC + i - 1, value), 0)
            lastValue[i] = value
        end
    end

    out:swap (output)
end

return {
    type    = 'DSP',
    layout  = layout,
    prepare = prepare,
    process = process
}

-- SPDX-License-Identifier: GPL-3.0-or-later
