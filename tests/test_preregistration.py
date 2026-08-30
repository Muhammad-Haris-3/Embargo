"""The preregistration binds the code, and the code binds the preregistration.

PREREGISTRATION.md states constants in a markdown table. embargo/preregistration.py
declares them in Python. Either one can be edited by hand, and a project whose
document says one threshold while its code uses another is worse than one with
no document at all.

So both directions are asserted here:

  doc -> code   every value in the table equals the constant it names
  code -> doc   every constant declared in the module appears in the table

The second direction is the one that matters. Adding a constant to the code
without writing it down is how a preregistration quietly stops describing the
thing it preregistered.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import pytest

from embargo import preregistration as prereg

DOC = Path(__file__).resolve().parents[1] / "PREREGISTRATION.md"

ROW = re.compile(r"^\|(?P<label>[^|]+)\|(?P<value>[^|]+)\|(?P<where>[^|]+)\|\s*$")
BACKTICKED = re.compile(r"`([^`]+)`")
CONST_REF = re.compile(r"`prereg\.([A-Z0-9_]+)`")


def doc_text() -> str:
    return DOC.read_text(encoding="utf-8")


def fixed_table() -> str:
    """The section between the 'Fixed before the fact' heading and the next one."""
    text = doc_text()
    start = text.index("## Fixed before the fact")
    end = text.index("## Universe", start)
    return text[start:end]


def coerce(raw: str):
    """Parse a table value into the type the constant should hold.

    Values may carry a unit -- '12 months', '2555 days', '0.10 relative' -- and
    the first backticked token is the value itself.
    """
    token = raw.strip()
    if token in ("True", "False"):
        return token == "True"
    # Hyphens required. date.fromisoformat accepts the basic format too, which
    # would silently read a seed of 20260830 as a date in August 2026.
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", token):
        return dt.date.fromisoformat(token)
    try:
        return int(token)
    except ValueError:
        pass
    try:
        return float(token)
    except ValueError:
        pass
    return token


def table_rows() -> list[tuple[str, list[str], list[str]]]:
    """(label, backticked values, constant names) for each data row."""
    rows = []
    for line in fixed_table().splitlines():
        m = ROW.match(line)
        if not m:
            continue
        label = m.group("label").strip()
        if label in ("Constant",) or set(label) <= set("-: "):
            continue
        consts = CONST_REF.findall(m.group("where"))
        if not consts:
            continue
        values = BACKTICKED.findall(m.group("value"))
        rows.append((label, values, consts))
    return rows


def test_the_table_was_found():
    rows = table_rows()
    assert len(rows) >= 15, f"only parsed {len(rows)} rows; the table format moved"


@pytest.mark.parametrize("label,values,consts", table_rows(), ids=lambda x: None)
def test_doc_value_matches_code(label, values, consts):
    assert values, f"row {label!r} states no value"

    if len(consts) == 2:
        # A range row: two backticked values, two constants, in order.
        assert len(values) == 2, f"row {label!r} names two constants but {len(values)} values"
        for name, raw in zip(consts, values):
            assert getattr(prereg, name) == coerce(raw), (
                f"{name} is {getattr(prereg, name)!r} in code, {raw!r} in the document"
            )
        return

    assert len(consts) == 1, f"row {label!r} names {len(consts)} constants"
    name = consts[0]
    expected = coerce(values[0])
    actual = getattr(prereg, name)
    assert actual == expected, f"{name} is {actual!r} in code, {values[0]!r} in the document"


def test_every_constant_in_code_is_written_down():
    """Drift in the direction that actually hides things."""
    declared = {name for name in dir(prereg) if name.isupper() and not name.startswith("_")}
    mentioned = set(CONST_REF.findall(doc_text()))
    missing = declared - mentioned
    assert not missing, f"declared in code but absent from PREREGISTRATION.md: {sorted(missing)}"


def test_every_constant_in_the_document_exists():
    for name in set(CONST_REF.findall(doc_text())):
        assert hasattr(prereg, name), f"PREREGISTRATION.md names {name}, code does not define it"


def test_amendments_section_is_present():
    """Amendments are appended below a line; nothing above it is ever edited.

    If the section disappears, the append-only discipline has no anchor.
    """
    assert "## Amendments" in doc_text()


def test_maturity_horizon_clears_the_probed_p99():
    """The stated reason for MATURITY_DAYS has to survive contact with the code.

    2555 days is chosen to sit beyond the probed 99th percentile of the wait
    (2,075 days) with room to spare. If someone lowers it, this fails and points
    at the paragraph that has to be amended.
    """
    assert prereg.MATURITY_DAYS > 2075
