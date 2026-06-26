import bz2
import datetime
import logging
import re
import tempfile
from pathlib import Path

import pandas as pd
from mendeleev import isotope as md_isotope


def slug_to_formula(slug: str) -> str:
    """Converts an iso_slug (e.g. '27Al-1H') to a chemical formula (e.g. '(27Al)(1H)')."""
    logging.debug(f"slug_to_formula: '{slug}'")
    slug_clean = slug.replace("_p", "+")
    parts = slug_clean.split("-")
    formula = ""
    for part in parts:
        chars = list(part)
        chars.insert(0, "(")
        chars.reverse()
        first_alpha = 0
        for i, c in enumerate(chars):
            if c.isalpha():
                first_alpha = i
                break
        chars.insert(first_alpha, ")")
        chars.reverse()
        formula += "".join(chars)
    formula = formula.replace("(cis)", "cis-").replace("(trans)", "trans-")
    logging.debug(f"slug_to_formula: result '{formula}'")
    return formula


def _data_files(iso_dir: Path, ext: str) -> list[Path]:
    """Returns deduplicated list of data files: plain files first; .bz2 only when no plain exists."""
    plain = list(iso_dir.rglob(f"*{ext}"))
    plain_set = set(plain)
    bz2 = [p for p in iso_dir.rglob(f"*{ext}.bz2") if p.with_suffix("") not in plain_set]
    return plain + bz2


def _open_maybe_bz2(path: Path, tmpdir: str) -> Path:
    """Decompress .bz2 to tmpdir if needed; return a readable path."""
    if path.suffix == ".bz2":
        dest = Path(tmpdir) / path.stem
        with open(path, "rb") as f_in:
            dest.write_bytes(bz2.decompress(f_in.read()))
        return dest
    return path


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


def extract_states_info(iso_dir: Path) -> dict:
    """Counts states and finds the maximum energy from the .states file."""
    logging.info(f"extractor: extract_states_info in '{iso_dir}'")
    states_files = _data_files(iso_dir, ".states")
    if not states_files:
        raise FileNotFoundError(f"No .states file found in '{iso_dir}'")

    with tempfile.TemporaryDirectory() as tmpdir:
        path = _open_maybe_bz2(states_files[0], tmpdir)
        num_lines = 0
        max_energy = 0.0
        with open(path, "r") as f:
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


def _load_state_energies(iso_dir: Path) -> dict[int, float]:
    """Loads {state_id: energy_cm-1} from the .states file in iso_dir."""
    states_files = _data_files(iso_dir, ".states")
    if not states_files:
        return {}
    energies: dict[int, float] = {}
    with tempfile.TemporaryDirectory() as tmpdir:
        path = _open_maybe_bz2(states_files[0], tmpdir)
        with open(path, "r") as f:
            for line in f:
                stripped = line.strip()
                if stripped:
                    cols = stripped.split()
                    energies[int(cols[0])] = float(cols[1])
    return energies


def extract_transitions_info(iso_dir: Path) -> dict:
    """
    Counts transitions and finds the maximum wavenumber across all .trans files.
    If the trans file has only 3 columns (id_u id_l A), the wavenumber is computed
    as abs(E_upper - E_lower) using the .states file.
    """
    logging.info(f"extractor: extract_transitions_info in '{iso_dir}'")
    trans_files = _data_files(iso_dir, ".trans")
    if not trans_files:
        raise FileNotFoundError(f"No .trans file found in '{iso_dir}'")

    # Detect column count from first non-empty line
    has_wavenumber_col = False
    with tempfile.TemporaryDirectory() as tmpdir:
        first_path = _open_maybe_bz2(trans_files[0], tmpdir)
        with open(first_path) as f:
            for line in f:
                stripped = line.strip()
                if stripped:
                    has_wavenumber_col = len(stripped.split()) >= 4
                    break

    # 3-column format: load states energies to compute wavenumber
    state_energies: dict[int, float] = {}
    if not has_wavenumber_col:
        logging.debug("extractor: trans file has 3 columns — computing wavenumber from states")
        state_energies = _load_state_energies(iso_dir)

    total_lines = 0
    max_wavenumber = 0.0
    with tempfile.TemporaryDirectory() as tmpdir:
        for raw_path in trans_files:
            path = _open_maybe_bz2(raw_path, tmpdir)
            file_lines = 0
            with open(path, "r") as f:
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


def extract_pf_info(iso_dir: Path) -> dict:
    """Extracts max temperature and step size from the .pf file."""
    logging.info(f"extractor: extract_pf_info in '{iso_dir}'")
    pf_files = list(iso_dir.rglob("*.pf"))
    if not pf_files:
        raise FileNotFoundError(f"No .pf file found in '{iso_dir}'")

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


def summarise_states_columns(iso_dir: Path) -> dict:
    """
    Reads the full .states file and returns:
      - 'first_rows': list of the first 5 rows (each row is a list of string tokens)
      - 'columns': list of per-column summaries
          For numeric columns: {col, type ('integer'/'float'), min, max}
          For string columns:  {col, type 'string', values (up to 3), more (bool)}
    """
    logging.info(f"extractor: summarise_states_columns in '{iso_dir}'")
    states_files = _data_files(iso_dir, ".states")
    if not states_files:
        return {"first_rows": [], "columns": []}

    with tempfile.TemporaryDirectory() as tmpdir:
        path = _open_maybe_bz2(states_files[0], tmpdir)
        df = pd.read_csv(path, sep=r"\s+", header=None, dtype=str, low_memory=False)

    # First 5 rows as lists of string tokens
    first_rows = df.head(5).values.tolist()

    columns = []
    for col_idx in range(len(df.columns)):
        col = df.iloc[:, col_idx].dropna()
        numeric = pd.to_numeric(col, errors="coerce")
        if numeric.notna().all():
            # Determine integer vs float by checking for decimal points or scientific notation
            has_decimal = col.str.contains(r"[.eE]", regex=True, na=False).any()
            col_type = "float" if bool(has_decimal) else "integer"
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


def extract_all(iso_slug: str, iso_dir: Path, ds_name: str) -> dict:
    """
    Assembles a full exomol.json-shaped dict with all auto-derivable fields populated.
    User-supplied fields are set to None.
    """
    logging.info(f"extractor: extract_all for '{iso_slug}' in '{iso_dir}'")
    iso_info = extract_iso_info(iso_slug)
    states_info = extract_states_info(iso_dir)
    trans_info = extract_transitions_info(iso_dir)
    pf_info = extract_pf_info(iso_dir)

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
