import numpy as np
import pytest

from benchcheck.cv.parsing import ParseError, parse_table, suggest_mapping, unit_from_header
from tests.conftest import table_from_text


def triangle(n=200):
    e = np.concatenate([np.linspace(0, 1, n), np.linspace(1, 0, n)])
    i = np.sin(np.linspace(0, 6, 2 * n)) * 1e-3
    return e, i


def test_comma_csv_with_preamble_and_header():
    text = "Instrument: X\nOperator: Y\n\nPotential (V),Current (A)\n" + "\n".join(
        f"{e:.4f},{i:.6e}" for e, i in zip(*triangle())
    )
    t = table_from_text(text)
    assert t.delimiter == "," and t.decimal == "."
    assert t.columns == ["Potential (V)", "Current (A)"]
    assert t.n_rows == 400
    assert len(t.preamble) == 2
    assert t.sha256 and len(t.sha256) == 64


def test_semicolon_decimal_comma():
    e, i = triangle()
    text = "Potential (V);Current (µA)\n" + "\n".join(
        f"{a:.4f};{b * 1e6:.3f}".replace(".", ",") for a, b in zip(e, i)
    )
    t = table_from_text(text)
    assert t.delimiter == ";" and t.decimal == ","
    np.testing.assert_allclose(t.column("Potential (V)"), np.round(e, 4))
    assert unit_from_header("Current (µA)") == "uA"


def test_tab_delimited_eclab_headers_and_mapping():
    e, i = triangle()
    rows = "\n".join(f"{k * 0.1:.2f}\t{a:.4f}\t{b * 1e3:.5f}\t1" for k, (a, b) in enumerate(zip(e, i)))
    text = "EC-Lab ASCII FILE\nNb header lines : 3\n\ntime/s\tEwe/V\t<I>/mA\tcycle number\n" + rows
    t = table_from_text(text)
    assert t.delimiter == "\t"
    s = suggest_mapping(t)["suggested"]
    assert s["potential"]["column"] == "Ewe/V" and s["potential"]["unit"] == "V"
    assert s["current"]["column"] == "<I>/mA" and s["current"]["unit"] == "mA"
    assert s["time"]["column"] == "time/s" and s["time"]["unit"] == "s"


def test_autolab_prefers_measured_potential():
    e, i = triangle()
    rows = "\n".join(f"{a:.4f},{b:.6e},{a + 0.0001:.4f},{k * 0.01:.3f}" for k, (a, b) in enumerate(zip(e, i)))
    text = "Potential applied (V),WE(1).Current (A),WE(1).Potential (V),Time (s)\n" + rows
    s = suggest_mapping(table_from_text(text))["suggested"]
    assert s["potential"]["column"] == "WE(1).Potential (V)"
    assert s["current"]["column"] == "WE(1).Current (A)" and s["current"]["unit"] == "A"


def test_units_row_under_header_is_combined():
    e, i = triangle()
    text = "Vf\tIm\nV vs. Ref.\tA\n" + "\n".join(f"{a:.4f}\t{b:.6e}" for a, b in zip(e, i))
    t = table_from_text(text)
    assert t.columns[0].startswith("Vf") and t.columns[1].startswith("Im")
    s = suggest_mapping(t)["suggested"]
    assert s["potential"]["unit"] == "V" and s["current"]["unit"] == "A"


def test_headerless_whitespace_uses_data_patterns():
    e, i = triangle()
    e = np.concatenate([e, e])
    i = np.concatenate([i, i])
    text = "\n".join(f"{b:.6e}   {a:.4f}" for a, b in zip(e, i))
    t = table_from_text(text)
    assert t.columns == ["Column 1", "Column 2"]
    s = suggest_mapping(t)["suggested"]
    assert s["potential"]["column"] == "Column 2"
    assert s["potential"]["basis"] == "triangular sweep pattern"


def test_malformed_rows_counted():
    text = "E,I\n" + "\n".join(f"{k / 100},{k / 1e5}" for k in range(50)) + "\n1,2,3\n0.6,0.0001\n"
    t = table_from_text(text)
    assert t.malformed_rows == 1
    assert np.isnan(t.data[-2]).all()


def test_non_numeric_file_rejected():
    with pytest.raises(ParseError):
        parse_table(b"hello\nworld\nthis is not data\n", "x.txt")


def test_empty_file_rejected():
    with pytest.raises(ParseError):
        parse_table(b"   \n", "x.csv")
