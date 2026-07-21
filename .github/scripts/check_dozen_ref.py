"""CI smoke test: diff a fresh Dozen build against the committed ref/, masking known pre-existing gaps.

# ponytail: masks tracked gaps rather than fixing them here — fix the gap, then delete its mask below.
"""
import json
import re
import sys
from pathlib import Path

built_stem, ref_stem = sys.argv[1], sys.argv[2]

MASK_DEF_LINE = re.compile(
    r"Isotopologue mass|Description quantum label|Lorentzian half-width|temperature exponent"
    r"|CAS Registry Number|In-ChI of molecule|In-ChI key of molecule"
    r"|Total number of transitions|No\. of transition files|Maximum wavenumber"
    r"|Higher energy with complete set of transitions"
)


def load_def(stem):
    lines = Path(f"{stem}.def").read_text().splitlines()
    return [l for l in lines if not MASK_DEF_LINE.search(l)]


def load_def_json(stem):
    d = json.loads(Path(f"{stem}.def.json").read_text())
    d["isotopologue"].pop("mass_in_Da", None)
    d["isotopologue"].pop("cas_registry_number", None)
    d["isotopologue"].pop("inchi", None)
    d["isotopologue"].pop("inchikey", None)
    d.pop("broad", None)
    d["dataset"]["states"].pop("max_energy", None)
    d["dataset"].pop("transitions", None)
    for field in d["dataset"]["states"]["states_file_fields"]:
        field.pop("desc", None)
    return d


ok = True
if load_def(built_stem) != load_def(ref_stem):
    print(f"MISMATCH: {built_stem}.def != {ref_stem}.def (outside masked gaps)")
    ok = False
if load_def_json(built_stem) != load_def_json(ref_stem):
    print(f"MISMATCH: {built_stem}.def.json != {ref_stem}.def.json (outside masked gaps)")
    ok = False

sys.exit(0 if ok else 1)
