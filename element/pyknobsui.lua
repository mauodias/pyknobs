--- Editor for the `pyknobs` DSP script.
--
-- A single Sync button. MIDI can only be emitted from the DSP script, so the
-- button doesn't send anything itself -- it toggles the DSP's "Sync" control
-- input, and the DSP responds by forgetting its cached values and re-sending
-- all eight CCs at their true current value on the next block.
--
-- Toggling in either direction triggers a re-send, so the button never needs
-- to be reset.
--
-- @script pyknobsui
-- @type   DSPUI pyknobs
-- @license GPL v3

local Widget     = require ('el.Widget')
local TextButton = require ('el.TextButton')
local object     = require ('el.object')

local COUNT   = 8
local SYNC    = COUNT + 1

local bgcolor = 0xff2a2a3a
local fgcolor = 0xffffffff
local dimcolor = 0xff9ca3af

local Editor = object (Widget)

function Editor:init (ctx)
    Widget.init (self)

    local sync = ctx.params [SYNC]

    self.button = self:add (object.new (TextButton))
    self.button.text = "Sync"
    self.button.clicked = function()
        -- Any change counts as a request, so just flip it.
        sync:set (sync:get() > 0.5 and 0.0 or 1.0, false)
    end

    self:resize (200, 120)
end

function Editor:paint (g)
    g:fillAll (bgcolor)

    g:setColor (fgcolor)
    g:drawText ("PYKNOBS", 0, 8, self.width, 24)

    g:setColor (dimcolor)
    g:drawText ("CC 10-17 . channel 1", 0, 32, self.width, 20)
    g:drawText ("re-send all values", 0, self.height - 26, self.width, 20)
end

function Editor:resized()
    local w = 100
    local h = 28
    self.button:setBounds ((self.width - w) / 2, 60, w, h)
end

local function instantiate (ctx)
    return object.new (Editor, ctx)
end

return {
    type        = 'DSPUI',
    instantiate = instantiate
}

-- SPDX-License-Identifier: GPL-3.0-or-later
