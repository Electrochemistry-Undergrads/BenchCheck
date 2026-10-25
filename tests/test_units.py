import numpy as np
import pytest

from benchcheck.cv import units


@pytest.mark.parametrize(
    "raw,expected",
    [("µA", "uA"), ("μA", "uA"), ("uA", "uA"), ("mA", "mA"), ("mV", "mV"), ("V", "V"), ("A", "A"),
     ("mA cm-2", "mA/cm2"), ("mA/cm²", "mA/cm2"), ("mv/s", "mV/s"), ("min", "min"), ("nA", "nA")],
)
def test_normalize_unit_spellings(raw, expected):
    assert units.normalize_unit(raw) == expected


def test_unknown_unit_rejected():
    with pytest.raises(units.UnitError):
        units.normalize_unit("furlongs")


def test_wrong_kind_rejected():
    with pytest.raises(units.UnitError):
        units.factor("mA", "potential")


def test_to_base_conversions():
    np.testing.assert_allclose(units.to_base(np.array([1500.0]), "mV", "potential"), [1.5])
    np.testing.assert_allclose(units.to_base(np.array([2.0]), "µA", "current"), [2e-6])
    np.testing.assert_allclose(units.to_base(np.array([3.0]), "min", "time"), [180.0])
    np.testing.assert_allclose(units.to_base(np.array([0.5]), "mA/cm2", "current"), [5e-4])


@pytest.mark.parametrize(
    "max_abs,density,unit",
    [(5e-4, False, "uA"), (1.5e-3, False, "mA"), (2e-9, False, "nA"), (3.0, False, "A"), (2e-4, True, "uA/cm2")],
)
def test_display_unit_choice(max_abs, density, unit):
    assert units.display_current_unit(max_abs, density)[0] == unit


def test_current_density_flag():
    assert units.is_current_density("mA/cm2")
    assert not units.is_current_density("mA")
