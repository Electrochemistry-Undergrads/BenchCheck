"""Parse potentiostat CSV/TXT exports into a numeric table.

Handles comma, semicolon, tab, pipe and whitespace delimiters, decimal commas,
instrument preambles before the header row, and a units row under the header.
The original bytes are never modified; a SHA-256 of the upload is recorded so
reports can be traced back to the exact file analyzed.
"""

from __future__ import annotations

import csv
import hashlib
import re
from dataclasses import dataclass, field

import numpy as np

from .segmentation import count_reversals
from .units import UnitError, normalize_unit

MAX_BYTES = 25 * 1024 * 1024
MAX_PREAMBLE_LINES_KEPT = 40
_DETECTION_SAMPLE_LINES = 3000

# (delimiter key, decimal) candidates; explicit delimiters before whitespace so ties
# resolve to the more specific choice.
_CANDIDATES = [
    (",", "."), (";", "."), (";", ","), ("\t", "."), ("\t", ","),
    ("|", "."), ("whitespace", "."), ("whitespace", ","),
]
_DELIMITER_NAMES = {",": "comma", ";": "semicolon", "\t": "tab", "|": "pipe", "whitespace": "whitespace"}

_NUM_DOT = re.compile(r"^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$")
_NUM_COMMA = re.compile(r"^[+-]?(?:\d+,?\d*|,\d+)(?:[eE][+-]?\d+)?$")


class ParseError(ValueError):
    pass


@dataclass
class ParsedTable:
    filename: str
    sha256: str
    size_bytes: int
    encoding: str
    delimiter: str
    decimal: str
    header_line: int | None
    first_data_line: int
    n_lines: int
    columns: list[str]
    data: np.ndarray
    preamble: list[str]
    malformed_rows: int
    notes: list[str] = field(default_factory=list)

    @property
    def n_rows(self) -> int:
        return int(self.data.shape[0])

    def column(self, name: str) -> np.ndarray:
        try:
            idx = self.columns.index(name)
        except ValueError as exc:
            raise ParseError(f"Column {name!r} not found. Available: {self.columns}") from exc
        return self.data[:, idx]

    def summary(self) -> dict:
        return {
            "filename": self.filename,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "encoding": self.encoding,
            "delimiter": _DELIMITER_NAMES.get(self.delimiter, self.delimiter),
            "decimal": self.decimal,
            "header_line": None if self.header_line is None else self.header_line + 1,
            "first_data_line": self.first_data_line + 1,
            "n_lines": self.n_lines,
            "n_rows": self.n_rows,
            "malformed_rows": self.malformed_rows,
            "columns": self.columns,
            "preamble_lines": len(self.preamble),
            "notes": self.notes,
        }


def decode_bytes(raw: bytes) -> tuple[str, str]:
    if raw.startswith((b"\x1f\x8b", b"PK\x03\x04")):
        raise ParseError("Compressed file: unzip first, then upload the text data.")
    for bom, enc in ((b"\xff\xfe\x00\x00", "utf-32"), (b"\x00\x00\xfe\xff", "utf-32"),
                     (b"\xff\xfe", "utf-16"), (b"\xfe\xff", "utf-16")):
        if raw.startswith(bom):
            try:
                return raw.decode(enc).lstrip("\x00"), enc
            except UnicodeDecodeError as exc:
                raise ParseError("The Unicode text file is incomplete or damaged.") from exc
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc).lstrip("\x00"), enc
        except UnicodeDecodeError:
            continue
    raise ParseError("Could not decode the file as text.")


def _split(line: str, delim: str) -> list[str]:
    if delim == "whitespace":
        return line.split()
    try:
        return [p.strip() for p in next(csv.reader([line], delimiter=delim, skipinitialspace=True))]
    except csv.Error:
        return []


def _numeric_token(token: str, decimal: str) -> str:
    token = token.strip().translate(str.maketrans({"−": "-", "–": "-", "﹣": "-", "D": "e", "d": "e"}))
    if decimal == ",":
        token = token.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"[+-]?\d{1,3}(?:,\d{3})+(?:\.\d*)?(?:[eE][+-]?\d+)?", token):
        token = token.replace(",", "")
    return token


def _is_number(token: str, decimal: str) -> bool:
    return bool(_NUM_DOT.fullmatch(_numeric_token(token, decimal)))


def _to_float(token: str, decimal: str) -> float:
    if not _is_number(token, decimal):
        return float("nan")
    try:
        value = float(_numeric_token(token, decimal))
        return value if np.isfinite(value) else float("nan")
    except ValueError:
        return float("nan")


def _detect_format(lines: list[str]) -> tuple[str, str, int, tuple]:
    # Score the whole sample, so one damaged cell never moves the data start.
    sample = lines[:_DETECTION_SAMPLE_LINES]
    best = None
    for delim, decimal in _CANDIDATES + [(",", ",")]:
        groups = {}
        for idx, line in enumerate(sample):
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            fields = _split(line, delim)
            flags = tuple(_is_number(f, decimal) for f in fields)
            if sum(flags) >= 2:
                groups.setdefault(len(fields), []).append((idx, flags, fields))
        for width, rows in groups.items():
            if len(rows) < 3:
                continue
            score = sum(sum(flags) / max(1, sum(bool(f) for f in fs)) for _, flags, fs in rows)
            # A decimal-comma candidate must actually contain decimal commas.
            if decimal == "," and not any("," in f for _, _, fs in rows for f in fs):
                continue
            # Prefer a matching textual header and consistent field counts.
            start = rows[0][0]
            header, _ = _header_for(lines, start, delim, width, decimal)
            if header is not None:
                score *= 1.01
            if decimal == "," and any("," in f for _, _, fs in rows for f in fs) and not any("." in f for _, _, fs in rows for f in fs):
                score *= 1.005
            rank = (score, int(header is not None), sum(rows[0][1]))
            if best is None or rank > best[0]:
                best = (rank, delim, decimal, start, (width, rows[0][1]))
    if best is None:
        if len(lines) > 1500:
            raise ParseError("No numeric data found in the first 3000 lines; shorten the instrument preamble (over 1500 lines).")
        raise ParseError("Could not find at least 3 numeric rows with 2 or more columns. Export CSV/TXT with one row per data point.")
    return best[1:]


def _looks_like_units_row(fields: list[str]) -> bool:
    ok = 0
    for f in fields:
        token = f.strip("()[] ")
        if not token:
            continue
        try:
            normalize_unit(token.split()[0])
            ok += 1
        except (UnitError, IndexError):
            pass
    return ok >= max(1, len(fields) // 2)


def _header_for(lines: list[str], start: int, delim: str, n_fields: int, decimal: str):
    """Find header (and optional units row) directly above the data block."""
    candidates = []
    idx = start - 1
    while idx >= 0 and len(candidates) < 2:
        line = lines[idx]
        if not line.strip():
            idx -= 1
            continue
        fields = _split(line, delim)
        if len(fields) != n_fields or sum(_is_number(f, decimal) for f in fields) > 0:
            break
        candidates.append((idx, fields))
        idx -= 1
    if not candidates:
        return None, None
    if len(candidates) == 2 and _looks_like_units_row(candidates[0][1]):
        units_idx, units = candidates[0]
        names_idx, names = candidates[1]
        combined = [f"{n} ({u})" if u else n for n, u in zip(names, units)]
        return names_idx, combined
    return candidates[0]


def _dedupe(names: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    out = []
    for i, name in enumerate(names):
        name = name or f"Column {i + 1}"
        if name in seen:
            seen[name] += 1
            name = f"{name} ({seen[name]})"
        else:
            seen[name] = 1
        out.append(name)
    return out


def parse_table(raw: bytes, filename: str = "upload.csv") -> ParsedTable:
    if len(raw) > MAX_BYTES:
        raise ParseError(f"File is larger than {MAX_BYTES // (1024 * 1024)} MB.")
    if not raw.strip():
        raise ParseError("The file is empty.")
    sha = hashlib.sha256(raw).hexdigest()
    text, encoding = decode_bytes(raw)
    lines = text.splitlines()
    delim, decimal, start, (n_fields, _flags) = _detect_format(lines)

    header_line, names = _header_for(lines, start, delim, n_fields, decimal)
    notes = []
    if names is None:
        names = [f"Column {i + 1}" for i in range(n_fields)]
        notes.append("No header row found; columns were named by position.")
    names = _dedupe([n.strip() for n in names])

    rows = []
    malformed = 0
    expected_numeric = np.array(_flags, dtype=bool)
    for line in lines[start:]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        fields = _split(line, delim)
        if len(fields) != n_fields:
            malformed += 1
            rows.append([float("nan")] * n_fields)
            continue
        converted = [_to_float(f, decimal) for f in fields]
        if any(expected_numeric[j] and fields[j] and not np.isfinite(v) for j, v in enumerate(converted)):
            malformed += 1
        rows.append(converted)
    data = np.array(rows, dtype=float) if rows else np.empty((0, n_fields))

    preamble_end = header_line if header_line is not None else start
    preamble = [ln for ln in lines[:preamble_end] if ln.strip()]
    if preamble:
        notes.append(f"Skipped {len(preamble)} preamble line(s) before the data.")
    if decimal == ",":
        notes.append("Decimal commas detected and converted.")
    if malformed:
        notes.append(f"{malformed} row(s) contain malformed numeric cells or unexpected field counts; only rows with invalid mapped values are excluded during analysis.")
    return ParsedTable(
        filename=filename[:240],
        sha256=sha,
        size_bytes=len(raw),
        encoding=encoding,
        delimiter=delim,
        decimal=decimal,
        header_line=header_line,
        first_data_line=start,
        n_lines=len(lines),
        columns=names,
        data=data,
        preamble=preamble[:MAX_PREAMBLE_LINES_KEPT],
        malformed_rows=malformed,
        notes=notes,
    )


# --------------------------------------------------------------------------------------
# Column-role suggestions
# --------------------------------------------------------------------------------------

_UNIT_TAIL = re.compile(r"(?:\(([^()]*)\)|\[([^\[\]]*)\]|/\s*([^/()\[\]]+))\s*$")


def unit_from_header(name: str) -> str | None:
    """Extract a unit from headers like 'Ewe/V', '<I>/mA', 'Current (A)', 'I [µA]'."""
    match = _UNIT_TAIL.search(name.strip())
    if not match:
        return None
    token = next(g for g in match.groups() if g is not None).strip()
    for candidate in (token, token.split(" vs")[0].strip(), token.split()[0] if token.split() else ""):
        try:
            return normalize_unit(candidate)
        except UnitError:
            continue
    return None


def _base_name(name: str) -> str:
    return _UNIT_TAIL.sub("", name).strip().lower()


_POTENTIAL_HINTS = [
    (r"\bewe\b", 10), (r"we\(\d\)\.potential", 9), (r"^vf$", 9), (r"potential(?! applied)", 8),
    (r"^e$|^e\s*we$|^e_we$", 8), (r"voltage", 7), (r"potential applied", 5),
    (r"^control$", 4), (r"^v$|^u$|^pot$", 5),
]
_CURRENT_HINTS = [
    (r"<i>", 10), (r"\bcurrent\b", 9), (r"^im$", 9), (r"^i$|^i_we$|^iwe$", 8), (r"\bamp", 6),
    (r"^j$|current density", 8),
]
_TIME_HINTS = [(r"\btime\b", 9), (r"^t$|^t_s$", 7), (r"elapsed", 8)]
_EXCLUDE = re.compile(r"cycle|scan\s*(no|number|#)|loop|segment|charge|capacity|step|index|point|^pt$|^ns$|^q$|^z|freq|phase")


def _score(name: str, hints) -> int:
    base = _base_name(name)
    if _EXCLUDE.search(base):
        return 0
    return max((w for pattern, w in hints if re.search(pattern, base)), default=0)


def _step_regularity(values: np.ndarray) -> float:
    """Coefficient of variation of non-zero |steps|; low for a linear potential sweep."""
    v = values[np.isfinite(values)]
    if v.size < 5:
        return float("inf")
    steps = np.abs(np.diff(v))
    steps = steps[steps > 0]
    if steps.size < 3:
        return float("inf")
    return float(np.std(steps) / np.mean(steps))


def suggest_mapping(table: ParsedTable) -> dict:
    """Suggest which columns hold potential, current and time. The user must confirm."""
    cols = table.columns
    result: dict[str, dict | None] = {"potential": None, "current": None, "time": None}
    used: set[str] = set()
    def index_column(j, c):
        values = table.data[:, j]
        values = values[np.isfinite(values)]
        return c.startswith("Column ") and values.size > 10 and np.all(values == np.floor(values)) and np.mean(np.diff(values) == 1) > .9
    eligible = [c for j, c in enumerate(cols) if table.n_rows and np.isfinite(table.data[:, j]).mean() >= .5
                and not _EXCLUDE.search(_base_name(c)) and not index_column(j, c)]
    for c in cols:
        if c not in eligible and not np.isfinite(table.column(c)).any():
            table.notes.append(f"Column {c!r} has no numeric data and cannot be mapped.")

    def pick(role: str, hints) -> None:
        scored = sorted(((_score(c, hints), c) for c in eligible if c not in used), reverse=True)
        if scored and scored[0][0] > 0:
            name = scored[0][1]
            used.add(name)
            result[role] = {"column": name, "unit": unit_from_header(name), "basis": "header name"}

    pick("potential", _POTENTIAL_HINTS)
    pick("current", _CURRENT_HINTS)
    pick("time", _TIME_HINTS)

    # Data-pattern fallbacks for unlabeled columns.
    stats = {}
    for idx, name in enumerate(cols):
        v = table.data[:, idx]
        finite = v[np.isfinite(v)]
        monotonic = finite.size > 2 and bool(np.all(np.diff(finite) >= 0))
        stats[name] = {
            "monotonic": monotonic,
            "reversals": count_reversals(v),
            "regularity": _step_regularity(v),
        }
    if result["time"] is None:
        for name in eligible:
            v = table.column(name)
            finite = v[np.isfinite(v)]
            is_index = finite.size > 2 and np.all(finite == np.floor(finite)) and np.all(np.diff(finite) == 1)
            if not is_index and name not in used and stats[name]["monotonic"] and stats[name]["regularity"] < 0.5:
                used.add(name)
                result["time"] = {"column": name, "unit": unit_from_header(name), "basis": "monotonic column"}
                break
    if result["potential"] is None:
        options = [n for n in eligible if n not in used and not stats[n]["monotonic"] and stats[n]["reversals"] >= 1]
        options.sort(key=lambda n: stats[n]["regularity"])
        if options:
            used.add(options[0])
            result["potential"] = {
                "column": options[0], "unit": unit_from_header(options[0]),
                "basis": "triangular sweep pattern",
            }
    if result["current"] is None:
        options = [n for n in eligible if n not in used and not stats[n]["monotonic"]]
        if options:
            used.add(options[0])
            result["current"] = {"column": options[0], "unit": unit_from_header(options[0]), "basis": "remaining column"}

    preview = []
    for row in table.data[:8]:
        preview.append([None if not np.isfinite(x) else float(x) for x in row])
    return {
        "suggested": result,
        "columns": cols,
        "preview_rows": preview,
        "column_stats": {
            name: {
                "min": _finite_or_none(np.nanmin(table.data[:, i])) if np.isfinite(table.data[:, i]).any() else None,
                "max": _finite_or_none(np.nanmax(table.data[:, i])) if np.isfinite(table.data[:, i]).any() else None,
                "n_numeric": int(np.isfinite(table.data[:, i]).sum()),
                "monotonic": stats[name]["monotonic"],
            }
            for i, name in enumerate(cols)
        },
    }


def _finite_or_none(x) -> float | None:
    x = float(x)
    return x if np.isfinite(x) else None
