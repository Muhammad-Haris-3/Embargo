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


# What the document originally committed, for constants an amendment has since
# superseded. The point of an append-only preregistration is that the original
# number stays legible, so these assert the old value is still on the page --
# an amendment must ADD a row, never edit the one above the Amendments line.
ORIGINAL_COMMITMENTS = {"MATURITY_DAYS": "2555"}


def fixed_table() -> str:
    """The section between the 'Fixed before the fact' heading and the next one."""
    text = doc_text()
    start = text.index("## Fixed before the fact")
    end = text.index("## Universe", start)
    return text[start:end]


def amendments() -> str:
    text = doc_text()
    return text[text.index("## Amendments") :]


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


def rows_in(section: str) -> list[tuple[str, list[str], list[str]]]:
    """(label, backticked values, constant names) for each data row."""
    rows = []
    for line in section.splitlines():
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


def table_rows() -> list[tuple[str, list[str], list[str]]]:
    """Every constant row in the document, original table first, amendments after.

    Document order is authoritative. An amendment that restates a constant
    supersedes the row above it, and the later row is the effective one --
    which is how an append-only document changes its mind without anybody
    editing what it said before.
    """
    return rows_in(fixed_table()) + rows_in(amendments())


def test_the_table_was_found():
    rows = rows_in(fixed_table())
    assert len(rows) >= 15, f"only parsed {len(rows)} rows; the table format moved"


def test_the_original_commitment_is_still_on_the_page():
    """A superseded constant must still show what was promised first.

    If an amendment could quietly rewrite the row above the Amendments line,
    the document would record only its current opinion, and a preregistration
    that records only its current opinion is a README.
    """
    original = {
        consts[0]: values[0] for _, values, consts in rows_in(fixed_table()) if len(consts) == 1
    }
    for name, expected in ORIGINAL_COMMITMENTS.items():
        assert original.get(name) == expected, (
            f"{name} was committed as {expected} and the original table now says "
            f"{original.get(name)}; amendments append, they do not edit"
        )


def effective_rows() -> list[tuple[str, list[str], list[str]]]:
    """One row per constant: the last one the document states."""
    latest: dict[tuple[str, ...], tuple[str, list[str], list[str]]] = {}
    for label, values, consts in table_rows():
        latest[tuple(consts)] = (label, values, consts)
    return list(latest.values())


def test_an_amendment_supersedes_rather_than_merely_repeating():
    """Where a constant is stated twice, the code must follow the later value.

    This is the mechanism that lets an append-only document change its mind. If
    it broke, the most likely symptom would be silent: the code agreeing with a
    number the document has already superseded.
    """
    all_rows = table_rows()
    names = [tuple(c) for _, _, c in all_rows]
    restated = {n for n in names if names.count(n) > 1}
    assert restated, "no constant has been superseded yet; this test is inert"

    for key in restated:
        stated = [values for _, values, consts in all_rows if tuple(consts) == key]
        first, last = coerce(stated[0][0]), coerce(stated[-1][0])
        assert first != last, f"{key[0]} is restated with an unchanged value"
        actual = getattr(prereg, key[0])
        assert actual == last, f"{key[0]} is {actual!r}; the effective value is {last!r}"
        assert actual != first, f"{key[0]} still holds the superseded value {first!r}"


@pytest.mark.parametrize("label,values,consts", effective_rows(), ids=lambda x: None)
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


def test_maturity_horizon_clears_the_measured_p99():
    """The stated reason for MATURITY_DAYS has to survive contact with the code.

    Amendment 1 raised the horizon to 3285 days so that it clears the worst
    cohort p99 measured at M1 -- 2,963 days, the 2011 cohort -- with room to
    spare. The M0 probe put it at 2,075 and was wrong, which is why this now
    asserts against the measured figure rather than the probed one. If someone
    lowers the horizon, this fails and points at the amendment that has to be
    written.
    """
    assert prereg.MATURITY_DAYS > 2963
