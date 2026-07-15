from __future__ import annotations

import datetime
import logging
import re
import tempfile
from pathlib import Path

import pandas as pd
from mendeleev import isotope as md_isotope

from validator import _data_files, _open_maybe_bz2


def slug_to_formula(slug: str) -> str:
    """Converts an iso_slug (e.g. '27Al-1H') to a chemical formula (e.g. '(27Al)(1H)')."""
    logging.debug(f"slug_to_formula: '{slug}'")

    def wrap(part: str) -> str:
        core = part.rstrip("0123456789+")
        return f"({core}){part[len(core):]}"

    formula = "".join(wrap(p) for p in slug.replace("_p", "+").split("-"))
    formula = formula.replace("(cis)", "cis-").replace("(trans)", "trans-")
    logging.debug(f"slug_to_formula: result '{formula}'")
    return formula


def expand_slug_atoms(iso_slug: str) -> tuple[list[tuple[int, str]], int]:
    """
    Expands an iso_slug into a list of (mass_number, element_symbol) tuples
    and returns the ionic charge (0 or 1).
    e.g. '27Al-1H' → [(27, 'Al'), (1, 'H')], 0
         '12C-16O2' → [(12, 'C'), (16, 'O'), (16, 'O')], 0
    """
    charge = 0
    parts = iso_slug.split("-")
    if parts[-1].endswith("_p"):
        parts[-1] = parts[-1][:-2]
        charge = 1

    expanded = []
    for part in parts:
        m = re.match(r"^(\d+)([A-Za-z]+)(\d*)$", part)
        if not m:
            raise ValueError(f"Cannot parse atom token '{part}' from slug '{iso_slug}'")
        mass_num = int(m.group(1))
        symbol = m.group(2)
        count = int(m.group(3)) if m.group(3) else 1
        expanded.extend([(mass_num, symbol)] * count)

    return expanded, charge


def nuclear_spin_degeneracy(iso_slug: str) -> tuple[int, bool] | None:
    """
    Returns (g_ns, has_equivalent_nuclei) where:
      g_ns = Π(2Iᵢ + 1) over all atoms in the slug (using mendeleev nuclear spins)
      has_equivalent_nuclei = True if any two atoms share the same isotope

    Returns None if any nuclear spin value is unavailable in mendeleev.
    """
    atoms, _ = expand_slug_atoms(iso_slug)
    g_ns = 1
    isotope_counts: dict[tuple[int, str], int] = {}
    for mass_num, symbol in atoms:
        iso = md_isotope(symbol, mass_num)
        spin = iso.spin
        if spin is None:
            logging.warning(f"extractor: nuclear spin unknown for {mass_num}{symbol} — g_ns check skipped")
            return None
        # mendeleev returns spin as a fraction string (e.g. "5/2") or a number
        if isinstance(spin, str) and "/" in spin:
            num, den = spin.split("/")
            spin_val = float(num) / float(den)
        else:
            spin_val = float(spin)
        g_ns *= int(round(2 * spin_val + 1))
        key = (mass_num, symbol)
        isotope_counts[key] = isotope_counts.get(key, 0) + 1
    has_equiv = any(v > 1 for v in isotope_counts.values())
    return g_ns, has_equiv


def main_isotopologue_slug(iso_slugs: list[str]) -> str:
    """
    Returns the iso_slug composed of the most naturally abundant isotope of each
    element — i.e. the "main" isotopologue of the dataset, as opposed to minor
    (isotopically substituted) ones. Used to decide which isotopologue's .def file
    receives dataset-level (non-isotope-specific) fields such as the CAS Registry
    Number, which CAS assigns to the parent molecule rather than per isotopologue.
    """
    def abundance_product(slug: str) -> float:
        atoms, _ = expand_slug_atoms(slug)
        product = 1.0
        for mass_num, symbol in atoms:
            product *= md_isotope(symbol, mass_num).abundance or 0.0
        return product

    return max(iso_slugs, key=abundance_product)


def extract_iso_info(iso_slug: str) -> dict:
    """Derives isotopologue identity and mass fields from the iso_slug (no file I/O)."""
    logging.info(f"extractor: extract_iso_info for '{iso_slug}'")
    electron_mass_Da = 0.000548579909

    atoms, charge = expand_slug_atoms(iso_slug)

    mass = 0.0
    element_dict: dict[str, int] = {}
    isotope_list = []
    for mass_num, symbol in atoms:
        iso = md_isotope(symbol, mass_num)
        mass += iso.mass
        element_dict[symbol] = mass_num
        isotope_list.append({"isotope_number": mass_num, "element_symbol": symbol})
        logging.debug(f"extractor: {symbol}-{mass_num}: {iso.mass:.8f} Da")

    mass -= charge * electron_mass_Da
    mass_kg = mass * 1.66053907e-27

    return {
        "iso_slug": iso_slug,
        "iso_formula": slug_to_formula(iso_slug),
        "mass_in_Da": round(mass, 8),
        "mass_in_kg": mass_kg,
        "number_of_atoms": len(atoms),
        "element": element_dict,
        "isotope_list": isotope_list,
        "charge": charge,
    }


def extract_states_info(work_dir: Path, iso_slug: str, ds_name: str) -> dict:
    """Counts states and finds the maximum energy from the .states file."""
    logging.info(f"extractor: extract_states_info for '{iso_slug}'")
    states_files = _data_files(work_dir, iso_slug, ds_name, ".states")
    if not states_files:
        raise FileNotFoundError(f"No .states file found for '{iso_slug}' in '{work_dir}'")

    with tempfile.TemporaryDirectory() as tmpdir:
        path = _open_maybe_bz2(states_files[0], tmpdir)
        num_lines = 0
        max_energy = 0.0
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                num_lines += 1
                val = float(stripped.split()[1])
                if val > max_energy:
                    max_energy = val

    logging.info(f"extractor: {num_lines} states, max_energy={max_energy} cm-1")
    return {"number_of_states": num_lines, "max_energy": max_energy}


def _load_state_energies(work_dir: Path, iso_slug: str, ds_name: str) -> dict[int, float]:
    """Loads {state_id: energy_cm-1} from the .states file."""
    states_files = _data_files(work_dir, iso_slug, ds_name, ".states")
    if not states_files:
        return {}
    energies: dict[int, float] = {}
    with tempfile.TemporaryDirectory() as tmpdir:
        path = _open_maybe_bz2(states_files[0], tmpdir)
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped:
                    cols = stripped.split()
                    energies[int(cols[0])] = float(cols[1])
    return energies


def extract_transitions_info(work_dir: Path, iso_slug: str, ds_name: str) -> dict:
    """
    Counts transitions and finds the maximum wavenumber across all .trans files.
    If the trans file has only 3 columns (id_u id_l A), the wavenumber is computed
    as abs(E_upper - E_lower) using the .states file.
    """
    logging.info(f"extractor: extract_transitions_info for '{iso_slug}'")
    trans_files = _data_files(work_dir, iso_slug, ds_name, ".trans")
    if not trans_files:
        raise FileNotFoundError(f"No .trans file found for '{iso_slug}' in '{work_dir}'")

    # Detect column count from first non-empty line
    has_wavenumber_col = False
    with tempfile.TemporaryDirectory() as tmpdir:
        first_path = _open_maybe_bz2(trans_files[0], tmpdir)
        with open(first_path, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped:
                    has_wavenumber_col = len(stripped.split()) >= 4
                    break

    # 3-column format: load state energies to compute wavenumber
    state_energies: dict[int, float] = {}
    if not has_wavenumber_col:
        logging.debug("extractor: trans file has 3 columns — computing wavenumber from states")
        state_energies = _load_state_energies(work_dir, iso_slug, ds_name)

    total_lines = 0
    max_wavenumber = 0.0
    with tempfile.TemporaryDirectory() as tmpdir:
        for raw_path in trans_files:
            path = _open_maybe_bz2(raw_path, tmpdir)
            file_lines = 0
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    total_lines += 1
                    file_lines += 1
                    cols = stripped.split()
                    if has_wavenumber_col:
                        nu = float(cols[3])
                    else:
                        id_u, id_l = int(cols[0]), int(cols[1])
                        nu = abs(state_energies.get(id_u, 0.0) - state_energies.get(id_l, 0.0))
                    if nu > max_wavenumber:
                        max_wavenumber = nu
            logging.debug(f"extractor: '{raw_path.name}' — {file_lines} transitions")

    logging.info(
        f"extractor: {total_lines} transitions across {len(trans_files)} file(s), "
        f"max_wavenumber={max_wavenumber} cm-1"
    )
    return {
        "number_of_transitions": total_lines,
        "number_of_transition_files": len(trans_files),
        "max_wavenumber": max_wavenumber,
    }


def extract_pf_info(work_dir: Path, iso_slug: str, ds_name: str) -> dict:
    """Extracts max temperature and step size from the .pf file."""
    logging.info(f"extractor: extract_pf_info for '{iso_slug}'")
    pf_files = _data_files(work_dir, iso_slug, ds_name, ".pf")
    if not pf_files:
        raise FileNotFoundError(f"No .pf file found for '{iso_slug}' in '{work_dir}'")

    temperatures = []
    with open(pf_files[0], "r", encoding="utf-8") as f:
        for line in f:
            parts = line.split()
            if parts:
                temperatures.append(float(parts[0]))

    if not temperatures:
        raise ValueError(f"No data in '{pf_files[0]}'")

    max_temp = max(temperatures)
    step = min(t2 - t1 for t1, t2 in zip(temperatures[:-1], temperatures[1:]))
    logging.info(f"extractor: pf max_temp={max_temp} K, step={step} K")
    return {
        "max_partition_function_temperature": max_temp,
        "partition_function_step_size": step,
    }


def summarise_states_columns(work_dir: Path, iso_slug: str, ds_name: str) -> dict:
    """
    Reads the full .states file and returns:
      - 'first_rows': aligned string table of the first 5 rows (from df.to_string)
      - 'columns': list of per-column summaries
          For numeric columns: {col, type ('integer'/'float'/'half-integer'), min, max}
          For string columns:  {col, type 'string', values (up to 3), more (bool)}
    """
    logging.info(f"extractor: summarise_states_columns for '{iso_slug}'")
    states_files = _data_files(work_dir, iso_slug, ds_name, ".states")
    if not states_files:
        return {"first_rows": [], "columns": []}

    with tempfile.TemporaryDirectory() as tmpdir:
        path = _open_maybe_bz2(states_files[0], tmpdir)
        df = pd.read_csv(path, sep=r"\s+", header=None, dtype=str, low_memory=False)

    # First 5 rows as an aligned string table (no index, no header)
    first_rows = df.head(5).to_string(index=False, header=False)

    columns = []
    for col_idx in range(len(df.columns)):
        col = df.iloc[:, col_idx].dropna()
        numeric = pd.to_numeric(col, errors="coerce")
        if numeric.notna().all():
            has_decimal = col.str.contains(r"[.eE]", regex=True, na=False).any()
            if not has_decimal:
                col_type = "integer"
            else:
                # Half-integer: all values are multiples of 0.5 (i.e. 2*val is a whole number)
                doubled = numeric * 2
                is_half_int = bool((doubled.round() == doubled).all() and (numeric % 1 != 0).any())
                col_type = "half-integer" if is_half_int else "float"
            columns.append({
                "col": col_idx + 1,
                "type": col_type,
                "min": float(numeric.min()),
                "max": float(numeric.max()),
            })
        else:
            unique_vals = col.unique().tolist()
            columns.append({
                "col": col_idx + 1,
                "type": "string",
                "values": unique_vals[:3],
                "more": len(unique_vals) > 3,
            })
        logging.debug(f"extractor: col {col_idx + 1}: {columns[-1]}")

    return {"first_rows": first_rows, "columns": columns}


def slug_to_hill_formula_and_charge(iso_slug: str) -> tuple[str, int]:
    """
    Returns the plain Hill formula and ionic charge for the molecule described by iso_slug.
    Hill order: C first (if present), H second, then alphabetical; no C → all alphabetical.
    e.g. '27Al-1H' → ('AlH', 0),  '12C-16O2' → ('CO2', 0)
    """
    from collections import Counter

    atoms, charge = expand_slug_atoms(iso_slug)
    counts = Counter(sym for _, sym in atoms)
    if "C" in counts:
        order = ["C"] + (["H"] if "H" in counts else []) + sorted(k for k in counts if k not in ("C", "H"))
    else:
        order = sorted(counts.keys())
    formula = "".join(f"{sym}{counts[sym] if counts[sym] > 1 else ''}" for sym in order)
    return formula, charge


def extract_all(iso_slug: str, work_dir: Path, ds_name: str) -> dict:
    """
    Assembles a full exomol.json-shaped dict with all auto-derivable fields populated.
    User-supplied fields (including inchi/inchikey) are set to None and filled at build time.
    """
    logging.info(f"extractor: extract_all for '{iso_slug}'")
    iso_info = extract_iso_info(iso_slug)
    states_info = extract_states_info(work_dir, iso_slug, ds_name)
    trans_info = extract_transitions_info(work_dir, iso_slug, ds_name)
    pf_info = extract_pf_info(work_dir, iso_slug, ds_name)

    return {
        "isotopologue": {
            "iso_formula": iso_info["iso_formula"],
            "iso_slug": iso_slug,
            "inchi": None,
            "inchikey": None,
            "cas_registry_number": None,
            "mass_in_Da": iso_info["mass_in_Da"],
            "point_group": None,
        },
        "atoms": {
            "number_of_atoms": iso_info["number_of_atoms"],
            "element": iso_info["element"],
        },
        "irreducible_representations": None,
        "dataset": {
            "name": ds_name,
            "version": int(datetime.datetime.now().strftime("%Y%m%d")),
            "doi": None,
            "max_temperature": None,
            "num_pressure_broadeners": 0,
            "cooling_function_available": None,
            "specific_heat_available": None,
            "continuum": None,
            "states": {
                "number_of_states": states_info["number_of_states"],
                "max_energy": states_info["max_energy"],
                "hyperfine_resolved_dataset": None,
                "uncertainty_description": None,
                "uncertainties_available": None,
                "lifetime_available": None,
                "lande_g_available": None,
                "quantum_case_label": None,
                "num_quanta": None,
                "num_quantum_types": None,
                "states_file_fields": None,
            },
            "transitions": {
                "number_of_transitions": trans_info["number_of_transitions"],
                "number_of_transition_files": trans_info["number_of_transition_files"],
                "max_wavenumber": trans_info["max_wavenumber"],
            },
        },
        "partition_function": {
            "max_partition_function_temperature": pf_info["max_partition_function_temperature"],
            "partition_function_step_size": pf_info["partition_function_step_size"],
        },
    }
