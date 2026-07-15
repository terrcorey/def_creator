"""
Renders an exomol.json-shaped merged dict into the flat ExoMol .def text format.

The rendering order follows def_structure.txt from def_updater, hardcoded here to
remove the runtime dependency on that file. Broadening fields are omitted (future template).
"""
from __future__ import annotations

from pathlib import Path
import logging

import config
import extractor


# ---------------------------------------------------------------------------
# ExoMol renderer
# ---------------------------------------------------------------------------

_COMMENT_COL = 80  # column at which '#' starts
_HEADER_COUNT = 4  # ID, E, gtot, and the 4th column (J / F / N) — not written as quantum labels
_NON_QUANTA_LABELS = {"unc", "tau", "gfactor"}  # boolean-flag columns, not quantum numbers


def _fmt_line(value: str, comment: str) -> str:
    """Formats one .def line: left-aligned value padded to _COMMENT_COL, then '# comment'."""
    value = config.to_ascii(str(value).strip())
    comment = config.to_ascii(str(comment).strip())
    padding = max(1, _COMMENT_COL - len(value))
    return value + " " * padding + "# " + comment + "\n"


def _bool_to_int(val) -> int:
    if isinstance(val, bool):
        return 1 if val else 0
    if isinstance(val, int):
        return val
    if isinstance(val, str):
        return 1 if val.lower() in ("true", "yes", "1") else 0
    return 0


def render(d: dict, output_path: Path) -> None:
    """Renders a fully-merged exomol.json-shaped dict to the ExoMol .def plain-text format."""
    logging.info(f"renderer: writing '{output_path}'")
    lines = _build_lines(d)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    logging.info(f"renderer: wrote {len(lines)} lines to '{output_path}'")


def _build_lines(d: dict) -> list[str]:
    out = []
    iso = d.get("isotopologue", {})
    atoms = d.get("atoms", {})
    irreps = d.get("irreducible_representations", {}) or {}
    dataset = d.get("dataset", {})
    states = dataset.get("states", {})
    trans = dataset.get("transitions", {})
    pf = d.get("partition_function", {})

    # ID
    out.append(_fmt_line("EXOMOL.def", "ID"))

    # Isotopologue identity
    out.append(_fmt_line(iso.get("iso_formula", ""), "IsoFormula"))
    out.append(_fmt_line(iso.get("iso_slug", ""), "Iso-slug"))
    out.append(_fmt_line(dataset.get("name", ""), "Isotopologue dataset name"))
    out.append(_fmt_line(dataset.get("version", ""), "Version number with format YYYYMMDD"))

    # CAS (optional — only written if present)
    cas = iso.get("cas_registry_number")
    if cas:
        out.append(_fmt_line(cas, "CAS Registry Number"))

    # InChI
    out.append(_fmt_line(iso.get("inchi") or "", "In-ChI of molecule"))
    out.append(_fmt_line(iso.get("inchikey") or "", "In-ChI key of molecule"))

    # Atom counts and isotope list (reconstructed from slug to avoid storing in JSON)
    iso_slug = iso.get("iso_slug", "")
    atom_list, _ = extractor.expand_slug_atoms(iso_slug) if iso_slug else ([], 0)
    n_atoms = atoms.get("number_of_atoms", 0)
    out.append(_fmt_line(n_atoms, "Number of atoms"))
    for i, (mass_num, symbol) in enumerate(atom_list, start=1):
        out.append(_fmt_line(mass_num, f"Isotope number {i}"))
        out.append(_fmt_line(symbol, f"Element symbol {i}"))

    # Mass
    mass_da = iso.get("mass_in_Da", 0.0)
    mass_kg = mass_da * 1.66053907e-27
    out.append(_fmt_line(f"{mass_da:.8f} {mass_kg:.8e}", "Isotopologue mass (Da) and (kg)"))

    # Symmetry
    out.append(_fmt_line(iso.get("point_group", ""), "Symmetry group"))

    # Irreducible representations
    n_irreps = len(irreps)
    out.append(_fmt_line(n_irreps, "Number of irreducible representations"))
    for i, (label, deg) in enumerate(irreps.items(), start=1):
        out.append(_fmt_line(label, f"Irreducible representation label {i}"))
        out.append(_fmt_line(deg, f"Nuclear spin degeneracy {i}"))

    # Dataset flags
    out.append(_fmt_line(f"{float(dataset.get('max_temperature', 0)):.2f}", "Maximum temperature of linelist"))
    out.append(_fmt_line(dataset.get("num_pressure_broadeners", 0), "No. of pressure broadeners available"))
    out.append(_fmt_line(_bool_to_int(dataset.get("cooling_function_available")), "Cooling function availability (1=yes, 0=no)"))
    out.append(_fmt_line(_bool_to_int(dataset.get("specific_heat_available")), "Specific heat availability (1=yes, 0=no)"))
    out.append(_fmt_line(_bool_to_int(dataset.get("continuum")), "Photo-absorption continuum cross-sections availability (1=yes, 0=no)"))

    # States
    out.append(_fmt_line(states.get("number_of_states", ""), "No. of states in .states file"))

    # Boolean state flags
    out.append(_fmt_line(_bool_to_int(states.get("hyperfine_resolved_dataset")), "Hyperfine resolved dataset (1=yes, 0=no)"))
    out.append(_fmt_line(_bool_to_int(states.get("uncertainties_available")), "Uncertainty availability (1=yes, 0=no)"))
    out.append(_fmt_line(_bool_to_int(states.get("lifetime_available")), "Lifetime availability (1=yes, 0=no)"))
    out.append(_fmt_line(_bool_to_int(states.get("lande_g_available")), "Lande g-factor availability (1=yes, 0=no)"))

    # Quantum numbers
    out.append(_fmt_line(states.get("quantum_case_label", ""), "Quantum case label"))
    out.append(_fmt_line(states.get("num_quantum_types", 0), "No. of quantum number types"))
    out.append(_fmt_line(states.get("num_quanta", 0), "No. of quanta defined"))

    # Quantum labels and auxiliary labels
    fields = states.get("states_file_fields") or []
    qn_labels = [
        f for f in fields[_HEADER_COUNT:]
        if f["name"] not in _NON_QUANTA_LABELS
        and not f["name"].startswith("Auxiliary:")
    ]
    aux_labels = [f for f in fields if f["name"].startswith("Auxiliary:")]

    for i, lbl in enumerate(qn_labels, start=1):
        out.append(_fmt_line(lbl["name"], f"Quantum label {i}"))
        fmt_str = f"{lbl['ffmt']} {lbl['cfmt']}".strip()
        out.append(_fmt_line(fmt_str, f"Format quantum label {i}"))
        out.append(_fmt_line(lbl.get("desc", ""), f"Description quantum label {i}"))

    for i, aux in enumerate(aux_labels, start=1):
        label = aux["name"].split(":", 1)[1] if ":" in aux["name"] else aux["name"]
        out.append(_fmt_line(label, f"Auxiliary title {i}"))
        fmt_str = f"{aux['ffmt']} {aux['cfmt']}".strip()
        out.append(_fmt_line(fmt_str, f"Format title {i}"))
        out.append(_fmt_line(aux.get("desc", ""), f"Description title {i}"))

    # Transitions
    out.append(_fmt_line(trans.get("number_of_transitions", ""), "Total number of transitions"))
    out.append(_fmt_line(trans.get("number_of_transition_files", ""), "No. of transition files"))
    out.append(_fmt_line(trans.get("max_wavenumber", ""), "Maximum wavenumber (in cm-1)"))
    out.append(_fmt_line(states.get("max_energy", ""), "Higher energy with complete set of transitions (in cm-1)"))

    # Partition function
    pf_max = pf.get("max_partition_function_temperature", "")
    pf_step = pf.get("partition_function_step_size", "")
    out.append(_fmt_line(f"{float(pf_max):.2f}" if pf_max != "" else "", "Maximum temperature of partition function"))
    out.append(_fmt_line(f"{float(pf_step):.2f}" if pf_step != "" else "", "Step size of temperature"))

    return out
