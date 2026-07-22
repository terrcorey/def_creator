"""ponytail: assert-based self-check for --force's raw-value-preservation behavior --
no real dataset needed, just a hand-written .inp fragment."""
from __future__ import annotations

import tempfile
from pathlib import Path

from inp_handler import parse_inp
from renderer import _fmt_line, _fmt_temperature

_INP = """\
[options]
shared_quantum_labels = false

[dataset]
version_date = not-a-date
doi =
max_temperature = not-a-number

[isotopologue.27Al-1H]
point_group = C
irreps = Sigma+:12
quantum_case_label = dos
cooling_function_available = maybe
specific_heat_available = true
continuum = false
"""


def _demo():
    with tempfile.TemporaryDirectory() as tmp:
        inp_path = Path(tmp) / "Test.inp"
        inp_path.write_text(_INP, encoding="utf-8")
        parsed = parse_inp(inp_path)

    # invalid-but-non-blank values are kept as raw strings, not dropped --
    # --force needs *something* to write through instead of a missing key
    assert parsed["dataset"]["version"] == "not-a-date"
    assert parsed["dataset"]["max_temperature"] == "not-a-number"
    assert parsed["per_isotopologue"]["27Al-1H"]["cooling_function_available"] == "maybe"

    # a value that did parse cleanly is untouched
    assert parsed["per_isotopologue"]["27Al-1H"]["specific_heat_available"] is True

    # renderer's temperature formatter falls back to the raw string instead of crashing
    assert _fmt_temperature("not-a-number") == "not-a-number"
    assert _fmt_temperature(5000) == "5000.00"
    assert _fmt_temperature("5000") == "5000.00"

    # a required field left None (blank in .inp, --force skipped merger.validate_complete)
    # renders blank, not the literal text "None"
    assert _fmt_line(None, "Symmetry group").startswith(" "), "None should render as blank, not 'None'"
    assert "None" not in _fmt_line(None, "Symmetry group")

    print("test_force_override: self-check passed")


if __name__ == "__main__":
    _demo()
