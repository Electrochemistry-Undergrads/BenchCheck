"""Regression cases from QA U1–U4, U8–U11."""
import numpy as np
import pytest
from benchcheck.cv.parsing import parse_table, suggest_mapping, ParseError


def rows():
    return [f'{k},{.3+abs((k%40)-20)/100},{np.sin(k)/1000}' for k in range(120)]


@pytest.mark.parametrize('position', [1, 20, 100])
def test_bad_cell_keeps_header_and_prefix(position):
    lines = rows()
    lines[position] = f'{position},.4,nan'
    table = parse_table(('time/s,E/V,I/mA\n'+'\n'.join(lines)).encode())
    assert table.columns == ['time/s', 'E/V', 'I/mA']
    assert table.n_rows == 120 and table.malformed_rows == 1


@pytest.mark.parametrize('decimal', ['.', ','])
def test_quoted_fields_and_thousands(decimal):
    lines = ['"time/s","E/V","I/mA"']
    for k in range(50):
        values = [str(k), f'{k/100:.3f}', f'{k/10:.3f}']
        if decimal == ',':
            values = [v.replace('.', ',') for v in values]
        lines.append(','.join(f'"{v}"' for v in values))
    table = parse_table('\n'.join(lines).encode())
    assert len(table.columns) == 3
    assert table.data[10, 1] == pytest.approx(.1)
    thousand = parse_table(('E,I\n'+'\n'.join(f'"1,{k:03d}.25",1.0D-03' for k in range(10))).encode())
    assert thousand.data[0, 0] == 1000.25
    assert thousand.data[0, 1] == .001


@pytest.mark.parametrize('encoding', ['utf-8', 'utf-16', 'utf-32'])
def test_unicode_minus_and_bom(encoding):
    table = parse_table(('E/V,I/A\n'+'\n'.join(f'{k/100},−0.001' for k in range(30))).encode(encoding))
    assert table.n_rows == 30 and np.isfinite(table.data).all()


def test_gamry_header_and_index():
    text = 'CURVE1\tTABLE\n\tPt\tT\tVf\tIm\n\t#\ts\tV vs. Ref.\tA\n'
    text += '\n'.join(f'\t{k}\t{k*.1}\t{.5+np.sin(k)/10}\t{np.cos(k)*1e-5}' for k in range(60))
    suggested = suggest_mapping(parse_table(text.encode()))['suggested']
    assert suggested['time']['column'].startswith('T ')
    assert suggested['potential']['column'].startswith('Vf ')
    assert suggested['current']['column'].startswith('Im ')


def test_decimal_comma_grouped_thousands():
    table = parse_table(('E/V;I/A\n'+'\n'.join(f'0,{k:03d};1.234,56' for k in range(30))).encode())
    assert table.delimiter == ';' and table.data[0, 1] == 1234.56


def test_nonnumeric_column_never_suggested():
    table = parse_table(('E/V,I/A,Other\n'+'\n'.join(f'{k},{k*k},bad' for k in range(30))).encode())
    assert all(not v or v['column'] != 'Other' for v in suggest_mapping(table)['suggested'].values())


@pytest.mark.parametrize('raw', [b'PK\x03\x04abc', b'\x1f\x8babc'])
def test_compressed_actionable(raw):
    with pytest.raises(ParseError, match='unzip first'):
        parse_table(raw)
