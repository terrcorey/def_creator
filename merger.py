"""
Merges auto-derived fields (from .def.json cache) with user-supplied fields (from parsed .inp).
Also validates that all required fields are populated before rendering.
"""
from __future__ import annotations

import logging
from typing import Any


_REQUIRED_PATHS = [
    ("isotopologue", "iso_formula"),
    ("isotopologue", "iso_slug"),
    ("isotopologue", "mass_in_Da"),
    ("isotopologue", "point_group"),
    ("atoms", "number_of_atoms"),
    ("irreducible_representations",),
    ("dataset", "name"),
    ("dataset", "max_temperature"),
    ("dataset", "cooling_function_available"),
    ("dataset", "specific_heat_available"),
    ("dataset", "continuum"),
    ("dataset", "states", "number_of_states"),
    ("dataset", "states", "max_energy"),
    ("dataset", "states", "hyperfine_resolved_dataset"),
    ("dataset", "states", "uncertainties_available"),
    ("dataset", "states", "lifetime_available"),
    ("dataset", "states", "lande_g_available"),
    ("dataset", "states", "quantum_case_label"),
    ("dataset", "states", "num_quanta"),
    ("dataset", "states", "num_quantum_types"),
    ("dataset", "states", "states_file_fields"),
    ("dataset", "transitions", "number_of_transitions"),
    ("dataset", "transitions", "number_of_transition_files"),
    ("dataset", "transitions", "max_wavenumber"),
    ("partition_function", "max_partition_function_temperature"),
    ("partition_function", "partition_function_step_size"),
]

# Fields that are optional (omitted from output if None)
_OPTIONAL_PATHS = {
    ("isotopologue", "inchi"),
    ("isotopologue", "inchikey"),
    ("isotopologue", "cas_registry_number"),
    ("dataset", "states", "uncertainty_description"),
}


def _get_nested(d: dict, path: tuple) -> Any:
    obj = d
    for key in path:
        if not isinstance(obj, dict) or key not in obj:
            return None
        obj = obj[key]
    return obj


def deep_merge(base: dict, override: dict) -> dict:
    """
    Recursively merges override into base. Override values replace base values
    unless the override value is None (which means 'not provided — keep auto-derived').
    Returns a new dict.
    """
    result = dict(base)
    for key, val in override.items():
        if val is None:
            continue
        if isinstance(val, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], val)
        else:
            result[key] = val
    return result


def merge_iso(auto_dict: dict, user_dict: dict) -> dict:
    """
    Merges a single isotopologue's auto-derived dict with user-supplied fields from parse_inp.
    user_dict is the flat per-isotopologue dict from inp_handler.parse_inp().
    """
    merged = deep_merge(auto_dict, {})  # start with a copy of auto_dict

    # Map user fields into the exomol.json structure
    iso = merged.setdefault("isotopologue", {})
    if "point_group" in user_dict:
        iso["point_group"] = user_dict["point_group"]
    if "cas_registry_number" in user_dict:
        iso["cas_registry_number"] = user_dict["cas_registry_number"]
    if "inchi" in user_dict:
        iso["inchi"] = user_dict["inchi"]
    if "inchikey" in user_dict:
        iso["inchikey"] = user_dict["inchikey"]

    if "irreducible_representations" in user_dict:
        merged["irreducible_representations"] = user_dict["irreducible_representations"]

    dataset = merged.setdefault("dataset", {})
    for key in ("version", "doi", "max_temperature", "cooling_function_available",
                "specific_heat_available", "continuum"):
        if key in user_dict:
            dataset[key] = user_dict[key]

    states = dataset.setdefault("states", {})
    for key in ("quantum_case_label", "states_file_fields", "num_quanta",
                "num_quantum_types", "uncertainties_available", "lifetime_available",
                "lande_g_available", "hyperfine_resolved_dataset"):
        if key in user_dict:
            states[key] = user_dict[key]

    return merged


def validate_complete(merged: dict, iso_slug: str) -> list[str]:
    """
    Checks that all required fields are non-None in the merged dict.
    Returns a list of human-readable missing field descriptions (empty = all good).
    """
    missing = []
    for path in _REQUIRED_PATHS:
        if path in _OPTIONAL_PATHS:
            continue
        val = _get_nested(merged, path)
        if val is None:
            missing.append(" → ".join(str(p) for p in path))

    if missing:
        logging.warning(
            f"merger: '{iso_slug}' is missing {len(missing)} required field(s)"
        )
    else:
        logging.info(f"merger: '{iso_slug}' all required fields present")
    return missing
