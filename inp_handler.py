"""
Handles generation and parsing of .inp input files.

The .inp format is an INI-style plain text file with [section] headers and key = value lines.
= signs are column-aligned within each section. Quantum label sections use a special format:
  label_name
  label_name = ffmt cfmt | description
"""
import json
import logging
import unicodedata
from datetime import date
from pathlib import Path

import config


# ---------------------------------------------------------------------------
# Standard label lookup
# ---------------------------------------------------------------------------

_standard_labels: dict[str, dict] | None = None


def _get_standard_labels() -> dict[str, dict]:
    """Returns a dict mapping label name → {Format quantum label, Description quantum label}."""
    global _standard_labels
    if _standard_labels is not None:
        return _standard_labels
    def _ascii(s: str) -> str:
        return unicodedata.normalize("NFKD", s).encode("ascii", errors="ignore").decode("ascii")

    try:
        path = config.standard_labels_path()
        with open(path, "r", encoding="utf-8") as f:
            raw: list[dict] = json.load(f)
        _standard_labels = {
            entry["Quantum label"]: {k: _ascii(v) if isinstance(v, str) else v for k, v in entry.items()}
            for entry in raw
        }
        logging.debug(f"inp_handler: loaded {len(_standard_labels)} standard labels")
    except Exception as e:
        logging.warning(f"inp_handler: could not load standard labels: {e}")
        _standard_labels = {}
    return _standard_labels


# ---------------------------------------------------------------------------
# User-facing comment text — edit here to change .inp instructions
# ---------------------------------------------------------------------------

_INP_COMMENTS: dict = {
    "options": {
        "shared_quantum_labels": "Set to true if all isotopologues share the same quantum label list",
    },
    "dataset": {
        "version_date": "Version date YYYYMMDD (auto-filled to today — edit to override)",
        "smiles": [
            "Base molecule SMILES, no isotope mass numbers (e.g. [Al][H] for AlH, C=O for H2CO).",
            "Auto-derived for diatomics and all-distinct-element molecules — verify topology.",
            "Leave blank and fill 'inchi' below if you prefer to provide InChI directly.",
        ],
        "inchi": [
            "Base molecule InChI — auto-derived from smiles when smiles is filled.",
            "Fill manually only if smiles is blank, e.g.: InChI=1S/AlH/h1H",
        ],
        "doi": "Publication DOI, e.g.: 10.1093/mnras/stad3802  (leave blank if not yet published)",
        "max_temperature": "Maximum temperature (K) this line list is valid for (author-stated)",
        "cooling_function_available": "true if a cooling function file is included",
        "specific_heat_available": "true if a specific heat file is included",
        "continuum": "true if photo-absorption continuum cross-sections are included",
    },
    "isotopologue": {
        "cas_registry_number": "CAS number (optional) — lookup: https://commonchemistry.cas.org",
        "point_group": "Symmetry group (e.g. C, Cs, C2v, Dinfh) — lookup: https://www.exomol.com",
        "irreps": "Irreducible representations as label:degeneracy pairs (e.g. Sigma+:12, Sigma-:12)",
        "quantum_case_label": "Quantum coupling case — lookup: https://www.exomol.com/data/quantum-cases/",
    },
    "quantum_labels": [
        "One label per line:  name  or  name = ffmt cfmt | description",
        "Standard library labels auto-fill format and description.",
        "First 4 columns are always: ID  E  gtot  J",
        "  (change J → F for hyperfine datasets; J → N for symmetric tops)",
        "Auto-detected from label names:",
        "  4th col = F   → hyperfine_resolved = true",
        "  unc           → uncertainties_available = true",
        "  tau           → lifetime_available = true",
        "  gfactor       → lande_g_available = true",
        "  namespaces (e.g. hunda:, hundb:) count toward num_quantum_types",
    ],
}


def _comment_lines(key: str, text: str | list[str], key_width: int) -> list[str]:
    """Formats '# key<pad> text' with consistent key-column alignment. Handles multi-line."""
    lines = [text] if isinstance(text, str) else list(text)
    result = [f"# {key:<{key_width}} {lines[0]}"]
    for continuation in lines[1:]:
        result.append(f"# {' ' * key_width} {continuation}")
    return result


# ---------------------------------------------------------------------------
# .inp generation
# ---------------------------------------------------------------------------

def _align_section(pairs: list[tuple[str, str]]) -> list[str]:
    """Returns key = value lines with = signs aligned to the longest key."""
    if not pairs:
        return []
    max_key = max(len(k) for k, _ in pairs)
    lines = []
    for key, val in pairs:
        padding = max_key - len(key)
        lines.append(f"{key}{' ' * padding} = {val}")
    return lines


def _format_col_summary(summary: dict) -> str:
    """Formats a single column summary entry for the states preview comment block."""
    col = summary["col"]
    ctype = summary["type"]
    if ctype in ("integer", "float", "half-integer"):
        mn = summary["min"]
        mx = summary["max"]
        if ctype == "integer":
            return f"  col {col:>2}  {ctype:<12}  range  {int(mn)} - {int(mx)}"
        elif ctype == "half-integer":
            def _fmt_half(v: float) -> str:
                return str(int(v)) if v == int(v) else f"{v:.1f}"
            return f"  col {col:>2}  {ctype:<12}  range  {_fmt_half(mn)} - {_fmt_half(mx)}"
        else:
            return f"  col {col:>2}  {ctype:<12}  range  {mn} - {mx}"
    else:
        vals = ", ".join(f"'{v}'" for v in summary["values"])
        if summary.get("more"):
            vals += ", ..."
        return f"  col {col:>2}  {ctype:<12}  values {vals}"


def _states_preview_block(iso_slug: str, states_summary: dict) -> list[str]:
    """Builds the commented first-rows block for the .inp file. Column summary is shown inline."""
    first_rows = states_summary.get("first_rows", [])
    if not first_rows:
        return [f"# (States file first rows not available for {iso_slug})"]

    lines = [f"# ---- States file preview ({iso_slug}) " + "-" * 40]
    lines.append("#  First 5 rows:")
    lines.append("#")
    for row_str in first_rows.split("\n"):
        lines.append("#  " + row_str)
    lines.append("#")
    lines.append("# " + "-" * 76)
    return lines


def generate_blank_inp(
    ds_name: str,
    iso_slugs: list[str],
    states_summaries: dict[str, dict],
    shared_quantum_labels: bool = False,
    extracted_data: dict[str, dict] | None = None,
    verbose: bool = True,
    base_smiles: str = "",
    base_inchi: str = "",
) -> str:
    """
    Generates the blank .inp file content for a dataset.

    Parameters
    ----------
    ds_name : str
    iso_slugs : list of isotopologue slug names
    states_summaries : mapping of iso_slug → result of extractor.summarise_states_columns()
    shared_quantum_labels : if True, generates one [quantum_labels] section for all isotopologues
    extracted_data : mapping of iso_slug → result of extractor.extract_all() for the auto-info header
    base_smiles : pre-filled base SMILES for the [dataset] section (auto-derived at --init time)
    base_inchi : pre-filled base InChI for the [dataset] section (auto-derived from base_smiles)
    """
    out = []
    input_separator = "#" + "-" * 30 + "input" + "-" * 30
    section_separator = "#" + "=" * 62
    today = date.today().isoformat()

    if verbose:
        out += [
            section_separator,
            f"#  {ds_name}.inp  —  generated by def_creator --init  {today}",
            "#  Fill all blank values, then run: python create_def.py <work_dir>",
            section_separator,
            "",
        ]

    # [options]
    out.append("[options]")
    if verbose:
        out += _comment_lines("shared_quantum_labels", _INP_COMMENTS["options"]["shared_quantum_labels"], 22)
        out.append(input_separator)
    out += _align_section([
        ("shared_quantum_labels", "true" if shared_quantum_labels else "false"),
    ])
    out.append("")
    out.append("")

    # [dataset]
    if verbose:
        out += [
            section_separator,
            "#  DATASET  (applies to all isotopologues)",
            section_separator,
        ]
    out.append("[dataset]")
    if verbose:
        for field, text in _INP_COMMENTS["dataset"].items():
            out += _comment_lines(field, text, 28)
        out.append(input_separator)
    pre_smiles = base_smiles
    pre_inchi = base_inchi

    out += _align_section([
        ("version_date",               date.today().strftime("%Y%m%d")),
        ("smiles",                     pre_smiles),
        ("inchi",                      pre_inchi),
        ("doi",                        ""),
        ("max_temperature",            ""),
        ("cooling_function_available", "false"),
        ("specific_heat_available",    "false"),
        ("continuum",                  "false"),
    ])
    out.append("")
    out.append("")

    for iso_slug in iso_slugs:
        if verbose:
            auto_parts = []
            if extracted_data and iso_slug in extracted_data:
                d = extracted_data[iso_slug]
                iso = d.get("isotopologue", {})
                atoms = d.get("atoms", {})
                states = d.get("dataset", {}).get("states", {})
                trans = d.get("dataset", {}).get("transitions", {})
                pf = d.get("partition_function", {})

                auto_parts.append(
                    f"iso_formula={iso.get('iso_formula', '?')}  "
                    f"mass={iso.get('mass_in_Da', '?')} Da  "
                    f"atoms={atoms.get('number_of_atoms', '?')}"
                )
                auto_parts.append(
                    f"states={states.get('number_of_states', '?')}  "
                    f"transitions={trans.get('number_of_transitions', '?')}  "
                    f"max_energy={states.get('max_energy', '?')} cm-1"
                )
                auto_parts.append(
                    f"pf_max_temp={pf.get('max_partition_function_temperature', '?')} K  "
                    f"pf_step={pf.get('partition_function_step_size', '?')} K"
                )

            try:
                import extractor as _ext
                nsd = _ext.nuclear_spin_degeneracy(iso_slug)
                if nsd is not None:
                    g_ns, has_equiv = nsd
                    if has_equiv:
                        auto_parts.append(f"g_ns = {g_ns}  (equivalent nuclei — ortho/para split; irrep degeneracies must be ≤ {g_ns})")
                    else:
                        auto_parts.append(f"g_ns = {g_ns}  (no equivalent nuclei — each irrep degeneracy must equal {g_ns})")
            except Exception:
                pass

            out += [section_separator, f"#  ISOTOPOLOGUE: {iso_slug}"]
            for part in auto_parts:
                out.append(f"#  Auto-derived: {part}")
            out.append(section_separator)
            out.append("")

        out.append(f"[isotopologue.{iso_slug}]")
        if verbose:
            for field, text in _INP_COMMENTS["isotopologue"].items():
                out += _comment_lines(field, text, 21)
            out.append(input_separator)
        out += _align_section([
            ("cas_registry_number", ""),
            ("point_group",         ""),
            ("irreps",              ""),
            ("quantum_case_label",  ""),
        ])
        out.append("")

        # [quantum_labels] — generated once per iso (or once total if shared)
        if not shared_quantum_labels or iso_slug == iso_slugs[0]:
            section = "[quantum_labels]" if shared_quantum_labels else f"[quantum_labels.{iso_slug}]"

            # States preview always included
            summary = states_summaries.get(iso_slug, {})
            out += _states_preview_block(iso_slug, summary)
            out.append("")

            out.append(section)
            if verbose:
                for line in _INP_COMMENTS["quantum_labels"]:
                    out.append(f"# {line}" if line else "#")
                out.append("#")
                out.append(input_separator)
            _HEADER_LABELS = ["ID", "E", "gtot", "J"]
            _LABEL_WIDTH = 20
            columns = summary.get("columns", [])
            if columns:
                for i, col_info in enumerate(columns):
                    label = _HEADER_LABELS[i] if i < len(_HEADER_LABELS) else ""
                    col_comment = _format_col_summary(col_info).strip()
                    out.append(f"{label:<{_LABEL_WIDTH}}# {col_comment}")
            else:
                out += _HEADER_LABELS
            out.append("")
            out.append("")

    return "\n".join(out)


def write_inp(content: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    logging.info(f"inp_handler: wrote '{path}'")


# ---------------------------------------------------------------------------
# .inp parsing
# ---------------------------------------------------------------------------

_BOOL_MAP = {
    "true": True, "yes": True, "1": True,
    "false": False, "no": False, "0": False,
}

_VALID_4TH_HEADERS = {"J", "F", "N"}


def _read_sections(inp_path: Path) -> dict[str, list[str]]:
    """Reads a .inp file and returns a dict mapping section name → list of raw lines."""
    sections: dict[str, list[str]] = {}
    current: str | None = None
    with open(inp_path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.rstrip("\n")
            stripped = line.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                current = stripped[1:-1]
                sections.setdefault(current, [])
            elif current is not None:
                sections[current].append(line)
    return sections


def _kv_pairs(section_lines: list[str]) -> dict[str, str]:
    """Parses key = value lines from a section (ignoring comments and blanks)."""
    result = {}
    for line in section_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" in stripped:
            key, _, val = stripped.partition("=")
            result[key.strip()] = val.strip()
    return result

_NON_QUANTA_LABELS = {"unc", "tau", "gfactor"}  # boolean-flag columns, not quantum numbers
_HEADER_COUNT = 4  # ID, E, gtot, and the 4th column (J / F / N)

# Fallback formats for the 4 standard header columns and common 4th-column variants
_HEADER_DEFAULTS: dict[str, dict] = {
    "ID":   {"ffmt": "I12",   "cfmt": "%12d",   "desc": "Unique integer identifier for the energy level"},
    "E":    {"ffmt": "F12.6", "cfmt": "%12.6f", "desc": "State energy in cm-1"},
    "gtot": {"ffmt": "I6",    "cfmt": "%6d",    "desc": "Total energy level degeneracy"},
    "J":    {"ffmt": "I7",    "cfmt": "%7d",    "desc": "Total rotational quantum number, excluding nuclear spin"},
    "F":    {"ffmt": "F7.1",  "cfmt": "%7.1f",  "desc": "Total angular momentum quantum number, including nuclear spin"},
    "N":    {"ffmt": "I7",    "cfmt": "%7d",    "desc": "Rotational quantum number"},
}


def _parse_bool(val: str, key: str) -> bool:
    v = val.strip().lower()
    if v not in _BOOL_MAP:
        raise ValueError(f"Invalid boolean value '{val}' for key '{key}'")
    return _BOOL_MAP[v]


def _parse_irreps(val: str) -> dict[str, int]:
    """Parses 'Sigma+:12, Sigma-:12' → {'Sigma+': 12, 'Sigma-': 12}."""
    result = {}
    for part in val.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" not in part:
            raise ValueError(f"Cannot parse irrep '{part}' — expected 'label:degeneracy'")
        label, deg = part.rsplit(":", 1)
        result[label.strip()] = int(deg.strip())
    return result


def _parse_quantum_label_line(line: str, standard_labels: dict) -> dict | None:
    """
    Parses one quantum label line from a [quantum_labels.*] section.
    Returns a states_file_fields dict or None if the line is empty/comment.
    Format: name  or  name = ffmt cfmt | description
    """
    line = line.strip()
    if not line or line.startswith("#"):
        return None

    # Strip inline comment (e.g. "ID                  # col  1  integer ...")
    if "#" in line:
        line = line[:line.index("#")].strip()
        if not line:
            return None

    if "=" in line:
        name, rest = line.split("=", 1)
        name = name.strip()
        rest = rest.strip()
        if "|" in rest:
            fmt_part, desc = rest.split("|", 1)
            fmt_tokens = fmt_part.strip().split()
            ffmt = fmt_tokens[0] if len(fmt_tokens) > 0 else ""
            cfmt = fmt_tokens[1] if len(fmt_tokens) > 1 else ""
            desc = desc.strip()
        else:
            fmt_tokens = rest.strip().split()
            ffmt = fmt_tokens[0] if len(fmt_tokens) > 0 else ""
            cfmt = fmt_tokens[1] if len(fmt_tokens) > 1 else ""
            desc = ""
    else:
        name = line
        ffmt = cfmt = desc = ""

    # Auto-fill from standard labels if not provided
    if not ffmt or not desc:
        bare = name.split(":", 1)[1].strip() if ":" in name else name
        std = standard_labels.get(name) or standard_labels.get(bare)
        if std:
            fmt_str = std.get("Format quantum label", "")
            if fmt_str and not ffmt:
                parts = fmt_str.split()
                ffmt = parts[0] if parts else ""
                cfmt = parts[1] if len(parts) > 1 else ""
            if not desc:
                desc = std.get("Description quantum label", "")

    # Fallback defaults for standard header columns (ID, E, gtot, J, F, N)
    if not ffmt or not desc:
        hdr = _HEADER_DEFAULTS.get(name)
        if hdr:
            if not ffmt:
                ffmt, cfmt = hdr["ffmt"], hdr["cfmt"]
            if not desc:
                desc = hdr["desc"]

    return {"name": name, "ffmt": ffmt, "cfmt": cfmt, "desc": desc}


def _auto_detect_flags(labels: list[dict]) -> dict:
    """
    Derives boolean availability flags and num_quantum_types from the full label list,
    which includes the 4 standard header columns at positions 0–3.
    Hyperfine is detected from the 4th label (index 3) being 'F'.
    """
    names = [lbl["name"] for lbl in labels]

    # Hyperfine: 4th column specifically named F
    fourth = names[_HEADER_COUNT - 1] if len(names) >= _HEADER_COUNT else ""
    hyperfine = (fourth == "F")

    # Flags and counts from non-header labels only
    non_header = names[_HEADER_COUNT:]
    uncertainties = "unc" in non_header
    lifetime = "tau" in non_header
    lande_g = "gfactor" in non_header

    namespaces: set[str] = set()
    for name in non_header:
        if ":" in name:
            ns, _ = name.split(":", 1)
            ns = ns.strip()
            if ns and ns.lower() != "auxiliary":
                namespaces.add(ns)

    non_aux = [n for n in non_header if not n.startswith("Auxiliary:") and n not in _NON_QUANTA_LABELS]
    num_quanta = len(non_aux)

    return {
        "uncertainties_available": uncertainties,
        "lifetime_available": lifetime,
        "lande_g_available": lande_g,
        "hyperfine_resolved_dataset": hyperfine,
        "num_quantum_types": len(namespaces),
        "num_quanta": num_quanta,
    }



def parse_inp(inp_path: Path) -> dict:
    """
    Parses a filled .inp file and returns a nested dict in exomol.json key structure,
    populated with user-supplied values. Auto-derives boolean flags from quantum labels.

    Returns a dict with top-level keys: 'dataset', 'per_isotopologue', 'options'.
    'per_isotopologue' maps iso_slug → dict of user-supplied isotopologue fields.
    """
    logging.info(f"inp_handler: parsing '{inp_path}'")
    standard_labels = _get_standard_labels()
    sections = _read_sections(inp_path)

    # Parse [options]
    options_kv = _kv_pairs(sections.get("options", []))
    try:
        shared_qn = _parse_bool(options_kv.get("shared_quantum_labels", "false"), "shared_quantum_labels")
    except ValueError:
        shared_qn = False  # validate_inp will report the invalid value

    # Parse [dataset]
    dataset_kv = _kv_pairs(sections.get("dataset", []))
    dataset_out: dict = {}
    if "version_date" in dataset_kv and dataset_kv["version_date"]:
        try:
            dataset_out["version"] = int(dataset_kv["version_date"])
        except ValueError:
            pass  # validate_inp will report the invalid value
    if "doi" in dataset_kv:
        dataset_out["doi"] = dataset_kv["doi"] or None
    if "max_temperature" in dataset_kv and dataset_kv["max_temperature"]:
        try:
            dataset_out["max_temperature"] = float(dataset_kv["max_temperature"])
        except ValueError:
            pass  # validate_inp will report the invalid value
    if "smiles" in dataset_kv and dataset_kv["smiles"].strip():
        dataset_out["smiles"] = dataset_kv["smiles"].strip()
    if "inchi" in dataset_kv and dataset_kv["inchi"].strip():
        dataset_out["base_inchi"] = dataset_kv["inchi"].strip()

    bool_flags = ("cooling_function_available", "specific_heat_available", "continuum")
    for flag in bool_flags:
        if flag in dataset_kv and dataset_kv[flag]:
            try:
                dataset_out[flag] = _parse_bool(dataset_kv[flag], flag)
            except ValueError:
                pass  # validate_inp will report the invalid value

    # Parse shared quantum labels — accept [quantum_labels] or first [quantum_labels.*] found
    shared_labels: list[dict] | None = None
    if shared_qn:
        qn_key = "quantum_labels" if "quantum_labels" in sections else next(
            (k for k in sections if k.startswith("quantum_labels.")), None
        )
        if qn_key:
            raw_labels = []
            for line in sections[qn_key]:
                parsed = _parse_quantum_label_line(line, standard_labels)
                if parsed:
                    raw_labels.append(parsed)
            if raw_labels:
                shared_labels = raw_labels

    # Collect all isotopologue sections
    iso_sections = {
        k: v for k, v in sections.items()
        if k.startswith("isotopologue.")
    }

    per_isotopologue: dict[str, dict] = {}
    for section_name, section_lines in iso_sections.items():
        iso_slug = section_name[len("isotopologue."):]
        kv = _kv_pairs(section_lines)
        iso_out: dict = {}

        if "cas_registry_number" in kv and kv["cas_registry_number"].strip():
            iso_out["cas_registry_number"] = kv["cas_registry_number"].strip()
        if "point_group" in kv and kv["point_group"]:
            iso_out["point_group"] = kv["point_group"].strip()
        if "irreps" in kv and kv["irreps"]:
            try:
                iso_out["irreducible_representations"] = _parse_irreps(kv["irreps"])
            except ValueError:
                pass  # validate_inp will report the invalid value
        if "quantum_case_label" in kv and kv["quantum_case_label"]:
            iso_out["quantum_case_label"] = kv["quantum_case_label"].strip()

        # Parse quantum labels
        if shared_qn and shared_labels is not None:
            raw_labels = shared_labels
        else:
            qn_section_key = f"quantum_labels.{iso_slug}"
            raw_labels = []
            if qn_section_key in sections:
                for line in sections[qn_section_key]:
                    parsed = _parse_quantum_label_line(line, standard_labels)
                    if parsed:
                        raw_labels.append(parsed)

        if raw_labels:
            flags = _auto_detect_flags(raw_labels)
            iso_out.update(flags)
            iso_out["states_file_fields"] = raw_labels
            logging.debug(
                f"inp_handler: '{iso_slug}' — {len(raw_labels)} user labels, "
                f"num_quantum_types={flags['num_quantum_types']}, "
                f"num_quanta={flags['num_quanta']}"
            )

        per_isotopologue[iso_slug] = iso_out

    result = {
        "options": {"shared_quantum_labels": shared_qn},
        "dataset": dataset_out,
        "per_isotopologue": per_isotopologue,
    }
    logging.info(
        f"inp_handler: parsed {len(per_isotopologue)} isotopologue(s): "
        f"{list(per_isotopologue)}"
    )
    return result


# ---------------------------------------------------------------------------
# .inp validation
# ---------------------------------------------------------------------------

def validate_inp(inp_path: Path, known_iso_slugs: list[str]) -> tuple[list[str], list[str]]:
    """
    Validates a filled .inp file for completeness and correctness.
    Collects ALL errors and soft warnings in one pass.
    Returns (errors, warnings); errors block the build, warnings are informational only.
    """
    errors: list[str] = []
    warnings: list[str] = []
    standard_labels = _get_standard_labels()
    sections = _read_sections(inp_path)

    # ------------------------------------------------------------------
    # [options]
    # ------------------------------------------------------------------
    options_kv = _kv_pairs(sections.get("options", []))
    sqn_raw = options_kv.get("shared_quantum_labels", "false")
    try:
        shared_qn = _parse_bool(sqn_raw, "shared_quantum_labels")
    except ValueError:
        errors.append(
            f"[options] shared_quantum_labels = \"{sqn_raw}\" is not valid.\n"
            f"  → Use true or false."
        )
        shared_qn = False

    # ------------------------------------------------------------------
    # [dataset]
    # ------------------------------------------------------------------
    if "dataset" not in sections:
        errors.append(
            "[dataset] section is missing.\n"
            "  → Add a [dataset] section with: doi, max_temperature,\n"
            "    cooling_function_available, specific_heat_available, continuum."
        )
        dataset_kv: dict[str, str] = {}
    else:
        dataset_kv = _kv_pairs(sections["dataset"])

        vd_val = dataset_kv.get("version_date", "").strip()
        if not vd_val:
            errors.append(
                "[dataset] version_date is blank.\n"
                "  → Enter the version date, e.g.:  version_date = 20240307"
            )
        else:
            try:
                vd_int = int(vd_val)
                if len(vd_val) != 8 or not (19000101 <= vd_int <= 99991231):
                    raise ValueError
            except ValueError:
                errors.append(
                    f"[dataset] version_date = \"{vd_val}\" is not a valid date.\n"
                    f"  → Use YYYYMMDD format, e.g.:  version_date = 20240307"
                )

        doi_val = dataset_kv.get("doi", "").strip()
        if doi_val and doi_val.lower() != "none" and not (doi_val.startswith("10.") and "/" in doi_val):
            errors.append(
                f"[dataset] doi = \"{doi_val}\" does not look like a valid DOI.\n"
                f"  → DOIs start with '10.' and contain a '/', e.g.:  doi = 10.1093/mnras/stad3802\n"
                f"  → Leave blank if not yet published."
            )

        mt_val = dataset_kv.get("max_temperature", "").strip()
        if not mt_val:
            errors.append(
                "[dataset] max_temperature is blank.\n"
                "  → Enter the maximum temperature in K (author-stated),\n"
                "    e.g.:  max_temperature = 5000"
            )
        else:
            try:
                mt_float = float(mt_val)
                if mt_float <= 0:
                    errors.append(
                        f"[dataset] max_temperature = {mt_val} is not a positive number.\n"
                        f"  → Temperature must be greater than 0 K, e.g.:  max_temperature = 5000"
                    )
            except ValueError:
                errors.append(
                    f"[dataset] max_temperature = \"{mt_val}\" is not a number.\n"
                    f"  → Enter a numeric value in K, e.g.:  max_temperature = 5000"
                )

        for flag in ("cooling_function_available", "specific_heat_available", "continuum"):
            val = dataset_kv.get(flag, "").strip()
            if not val:
                errors.append(
                    f"[dataset] {flag} is blank.\n"
                    f"  → Use true or false."
                )
            else:
                try:
                    _parse_bool(val, flag)
                except ValueError:
                    errors.append(
                        f"[dataset] {flag} = \"{val}\" is not valid.\n"
                        f"  → Use true or false."
                    )

    # Dataset-level SMILES / InChI validation
    smiles_ds = dataset_kv.get("smiles", "").strip()
    if smiles_ds:
        import inchi as _inchi_mod
        _test_mol = None
        try:
            from rdkit import Chem as _Chem
            _test_mol = _Chem.MolFromSmiles(smiles_ds) or _Chem.MolFromSmiles(smiles_ds, sanitize=False)
        except ImportError:
            pass  # RDKit absent — skip validation
        if _test_mol is None and _inchi_mod is not None:
            errors.append(
                f"[dataset] smiles = \"{smiles_ds}\" could not be parsed by RDKit.\n"
                f"  → Verify the SMILES is valid. Common issues:\n"
                f"    - Radicals need bracket atoms: [Al][H] not AlH\n"
                f"    - Charges go inside brackets: [NH4+], [O-]\n"
                f"    - Ring closures require matching digits: C1CCCCC1"
            )

    # ------------------------------------------------------------------
    # Per-isotopologue sections
    # ------------------------------------------------------------------
    for iso_slug in known_iso_slugs:

        # [isotopologue.slug]
        iso_section = f"isotopologue.{iso_slug}"
        if iso_section not in sections:
            errors.append(
                f"[isotopologue.{iso_slug}] section is missing.\n"
                f"  → Add a section [isotopologue.{iso_slug}] with:\n"
                f"    point_group, irreps, quantum_case_label (and optionally inchi, inchikey, cas_registry_number)."
            )
        else:
            iso_kv = _kv_pairs(sections[iso_section])

            if not iso_kv.get("point_group", "").strip():
                errors.append(
                    f"[isotopologue.{iso_slug}] point_group is blank.\n"
                    f"  → Enter the symmetry group, e.g.:  point_group = C\n"
                    f"    (common values: C, Cs, C2v, C3v, Td, D2h, Dinfh, Kh)"
                )

            irreps_val = iso_kv.get("irreps", "").strip()
            if not irreps_val:
                errors.append(
                    f"[isotopologue.{iso_slug}] irreps is blank.\n"
                    f"  → Enter irreducible representations as label:degeneracy pairs,\n"
                    f"    e.g.:  irreps = Sigma+:12, Sigma-:12"
                )
            else:
                try:
                    parsed_irreps = _parse_irreps(irreps_val)
                    bad_degs = [(lbl, deg) for lbl, deg in parsed_irreps.items() if deg < 0]
                    if bad_degs:
                        for lbl, deg in bad_degs:
                            errors.append(
                                f"[isotopologue.{iso_slug}] irreps '{lbl}' has degeneracy {deg} — must be a non-negative integer.\n"
                                f"  → e.g.:  irreps = Sigma+:12, Sigma-:12"
                            )

                    # Nuclear spin degeneracy check
                    try:
                        import extractor as _ext
                        nsd = _ext.nuclear_spin_degeneracy(iso_slug)
                        if nsd is not None:
                            g_ns, has_equiv = nsd
                            for lbl, deg in parsed_irreps.items():
                                if deg > g_ns:
                                    errors.append(
                                        f"[isotopologue.{iso_slug}] irreps '{lbl}:{deg}' exceeds g_ns = {g_ns}.\n"
                                        f"  g_ns = Π(2Iᵢ+1) = {g_ns} is the maximum possible nuclear spin degeneracy for {iso_slug}.\n"
                                        f"  No individual irrep degeneracy can exceed this."
                                    )
                            if not has_equiv:
                                wrong = [(lbl, deg) for lbl, deg in parsed_irreps.items() if deg != g_ns]
                                for lbl, deg in wrong:
                                    errors.append(
                                        f"[isotopologue.{iso_slug}] irreps '{lbl}:{deg}' — expected {g_ns}.\n"
                                        f"  {iso_slug} has no equivalent nuclei, so g_ns = Π(2Iᵢ+1) = {g_ns} for every irrep."
                                    )
                    except Exception:
                        pass  # don't let the check block the build if extractor is unavailable

                except ValueError as exc:
                    errors.append(
                        f"[isotopologue.{iso_slug}] irreps = \"{irreps_val}\" could not be parsed: {exc}\n"
                        f"  → Use colon-separated label:degeneracy pairs,\n"
                        f"    e.g.:  irreps = Sigma+:12, Sigma-:12"
                    )

            _VALID_CASE_LABELS = {
                "dcs", "dos", "lpcs", "lpos", "asymcs", "asymos",
                "stos", "stcs", "sphcs", "sphos",
            }
            qcl_val = iso_kv.get("quantum_case_label", "").strip()
            if not qcl_val:
                errors.append(
                    f"[isotopologue.{iso_slug}] quantum_case_label is blank.\n"
                    f"  → Enter the quantum coupling case label,\n"
                    f"    e.g.:  quantum_case_label = dos\n"
                    f"    (valid values: {', '.join(sorted(_VALID_CASE_LABELS))})"
                )
            elif qcl_val not in _VALID_CASE_LABELS:
                errors.append(
                    f"[isotopologue.{iso_slug}] quantum_case_label = \"{qcl_val}\" is not a recognised case label.\n"
                    f"  → Valid values: {', '.join(sorted(_VALID_CASE_LABELS))}"
                )

        # [quantum_labels.slug] (or shared [quantum_labels])
        if shared_qn:
            qn_section = "quantum_labels" if "quantum_labels" in sections else next(
                (k for k in sections if k.startswith("quantum_labels.")), "quantum_labels"
            )
        else:
            qn_section = f"quantum_labels.{iso_slug}"
        if qn_section not in sections:
            errors.append(
                f"[{qn_section}] section is missing.\n"
                f"  → Add a section [{qn_section}] listing states file columns one per line.\n"
                f"  → The first four lines must be the header columns:\n"
                f"    ID\n"
                f"    E\n"
                f"    gtot\n"
                f"    J   ← or F for hyperfine datasets, N for symmetric tops"
            )
        else:
            labels = [
                lbl for line in sections[qn_section]
                if (lbl := _parse_quantum_label_line(line, standard_labels)) is not None
            ]

            if len(labels) < _HEADER_COUNT:
                errors.append(
                    f"[{qn_section}] has {len(labels)} label(s) — at least {_HEADER_COUNT} required.\n"
                    f"  → The first four lines must be the header columns:\n"
                    f"    ID\n"
                    f"    E\n"
                    f"    gtot\n"
                    f"    J   ← or F for hyperfine datasets, N for symmetric tops"
                )
            else:
                for i, expected in enumerate(("ID", "E", "gtot")):
                    if labels[i]["name"] != expected:
                        errors.append(
                            f"[{qn_section}] position {i + 1} is '{labels[i]['name']}' but expected '{expected}'.\n"
                            f"  → Header order must be: ID, E, gtot, then J / F / N."
                        )

                fourth = labels[3]["name"]
                if fourth not in _VALID_4TH_HEADERS:
                    errors.append(
                        f"[{qn_section}] 4th column is '{fourth}' — expected J, F, or N.\n"
                        f"  → Use J (standard), F (hyperfine datasets), or N (symmetric tops)."
                    )

                for lbl in labels:
                    name = lbl["name"]
                    if name.startswith("Auxiliary:"):
                        if not lbl.get("ffmt") or not lbl.get("cfmt"):
                            bare = name.split(":", 1)[1]
                            errors.append(
                                f"[{qn_section}] Auxiliary column '{name}' is not in the standard library and has no format string.\n"
                                f"  → Specify Fortran and C formats (and optionally a description) inline:\n"
                                f"  →   {name} = A2 %2s | Description here\n"
                                f"    (replace A2 / %2s with the actual formats for '{bare}')"
                            )
                    elif name not in {"ID", "E", "gtot"} and name not in _VALID_4TH_HEADERS:
                        if not lbl.get("ffmt") or not lbl.get("cfmt"):
                            errors.append(
                                f"[{qn_section}] label '{name}' has no format string and is not in the standard library.\n"
                                f"  → Specify Fortran and C formats inline, e.g.:\n"
                                f"  →   {name} = I5 %5d | Description here"
                            )

                # Soft warning: no namespaced quantum number types detected
                flags = _auto_detect_flags(labels)
                if flags["num_quantum_types"] == 0:
                    warnings.append(
                        f"[{qn_section}] No quantum number type namespaces detected (num_quantum_types = 0).\n"
                        f"  This is valid if all labels are generally well-defined, but if your labels belong to a coupling\n"
                        f"  scheme (e.g. Hund's case a), prefix them with the case name:\n"
                        f"    hunda:Lambda\n"
                        f"    hunda:Sigma\n"
                        f"  If num_quantum_types = 0 is intentional, you can ignore this and continue building."
                        f"  For more information on quantum number types, read the documentation at https://www.exomol.com/data/quantum-cases/"
                    )

        # Only validate shared quantum_labels once (for the first iso_slug)
        if shared_qn:
            break

    # ------------------------------------------------------------------
    # Warn about .inp isotopologue sections with no matching directory
    # ------------------------------------------------------------------
    for section_name in sections:
        if section_name.startswith("isotopologue."):
            slug = section_name[len("isotopologue."):]
            if slug not in known_iso_slugs:
                errors.append(
                    f"[isotopologue.{slug}] in the .inp file has no matching directory.\n"
                    f"  → Check for typos — isotopologue directories found: {', '.join(known_iso_slugs) or 'none'}"
                )

    return errors, warnings
