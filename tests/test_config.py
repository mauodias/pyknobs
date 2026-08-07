"""Persistence: the TOML layout survives a round trip and stays hand-editable."""

from __future__ import annotations

import pytest

from pyknobs import config as config_module
from pyknobs.config import MAX_KNOBS, KnobSpec, next_free_cc


def test_defaults_when_no_file(config_path):
    cfg = config_module.load(config_path)
    assert len(cfg.knobs) == config_module.DEFAULT_KNOB_COUNT
    assert cfg.cc_numbers == tuple(range(10, 18))
    assert cfg.invert_scroll is True, "macOS trackpad is the default"


def test_round_trip(config_path):
    cfg = config_module.load(config_path, 3)
    cfg.knobs[0].name = "Cutoff"
    cfg.knobs[1].cc = 42
    cfg.invert_scroll = False
    cfg.in_port = "IAC Driver Bus 2"
    cfg.out_port = "IAC Driver Bus 1"
    cfg.save()

    again = config_module.load(config_path)
    assert [(k.name, k.cc) for k in again.knobs] == [("Cutoff", 10), ("Knob 2", 42), ("Knob 3", 12)]
    assert again.invert_scroll is False
    assert again.in_port == "IAC Driver Bus 2"
    assert again.out_port == "IAC Driver Bus 1"


def test_bare_keys_precede_tables(config_path):
    """A bare key after a [[table]] would be parsed as part of it."""
    cfg = config_module.load(config_path, 2)
    cfg.save()
    text = config_path.read_text()
    assert text.index("invert_scroll") < text.index("[[knobs]]")
    assert text.index("in_port") < text.index("[[knobs]]")


def test_names_with_quotes_survive(config_path):
    cfg = config_module.load(config_path, 1)
    cfg.knobs[0].name = 'a "quoted" \\ name'
    cfg.save()
    assert config_module.load(config_path).knobs[0].name == 'a "quoted" \\ name'


def test_count_override_grows_with_free_ccs(config_path):
    cfg = config_module.load(config_path, 2)
    cfg.knobs[1].cc = 12
    cfg.save()
    grown = config_module.load(config_path, 4)
    assert len(grown.knobs) == 4
    assert len(set(grown.cc_numbers)) == 4, "no duplicate CCs"


def test_count_override_truncates(config_path):
    config_module.load(config_path, 8).save()
    assert len(config_module.load(config_path, 3).knobs) == 3


def test_count_is_capped(config_path):
    cfg = config_module.load(config_path, MAX_KNOBS)
    cfg.knobs.extend(KnobSpec(f"x{i}", 100 + i) for i in range(5))
    cfg.save()
    assert len(config_module.load(config_path).knobs) == MAX_KNOBS


def test_index_for_cc(config_path):
    cfg = config_module.load(config_path, 4)
    assert cfg.index_for_cc(12) == 2
    assert cfg.index_for_cc(99) is None


@pytest.mark.parametrize(
    "used, expected",
    [(set(), 10), ({10, 11}, 12), ({10, 12}, 11), (set(range(10, 30)), 30)],
)
def test_next_free_cc(used, expected):
    assert next_free_cc(used) == expected
