import bz2
import logging
import tempfile
from pathlib import Path

import pandas as pd


class ValidationError(Exception):
    pass


def _open_for_check(path: Path, tmpdir: str) -> Path:
    """Decompress .bz2 to tmpdir if needed; return a readable path."""
    if path.suffix == ".bz2":
        dest = Path(tmpdir) / path.stem
        with open(path, "rb") as f_in:
            data = bz2.decompress(f_in.read())
        dest.write_bytes(data)
        return dest
    return path


def _spot_check_states(path: Path) -> None:
    df = pd.read_csv(path, sep=r"\s+", header=None, nrows=5)
    if len(df.columns) < 4:
        raise ValidationError(
            f"'{path.name}' has {len(df.columns)} columns, expected ≥ 4 "
            "(ID, E, gtot, J(F if hyperfine) are required)"
        )
    logging.debug(f"validator: '{path.name}' spot-check OK ({len(df.columns)} columns)")


def _spot_check_trans(path: Path) -> None:
    df = pd.read_csv(path, sep=r"\s+", header=None, nrows=5)
    if len(df.columns) < 3:
        raise ValidationError(
            f"'{path.name}' has {len(df.columns)} columns, expected ≥ 3 "
            "(upper state ID, lower state ID, Einstein A are required)"
        )
    logging.debug(f"validator: '{path.name}' spot-check OK ({len(df.columns)} columns)")


def _data_files(work_dir: Path, iso_slug: str, ds_name: str, ext: str) -> list[Path]:
    """
    Returns files in work_dir whose names start with '{iso_slug}__{ds_name}' and end
    with '{ext}'. Plain files take precedence; a .bz2 file is only included when no
    plain counterpart exists for that stem.
    """
    prefix = f"{iso_slug}__{ds_name}"
    plain = sorted(
        f for f in work_dir.iterdir()
        if f.is_file() and f.name.startswith(prefix) and f.name.endswith(ext)
    )
    plain_set = set(plain)
    compressed = sorted(
        f for f in work_dir.iterdir()
        if f.is_file()
        and f.name.startswith(prefix)
        and f.name.endswith(f"{ext}.bz2")
        and f.with_suffix("") not in plain_set
    )
    return plain + compressed


def discover_dataset(work_dir: Path) -> tuple[str, list[str]]:
    """
    Scans work_dir for files named '{iso_slug}__{ds_name}.states[.bz2]'.
    Returns (ds_name, sorted list of iso_slugs).
    Raises ValidationError if the directory doesn't exist, no qualifying files are
    found, or files from multiple dataset names are detected.
    """
    if not work_dir.is_dir():
        raise ValidationError(f"Work directory '{work_dir}' does not exist")

    ds_names: set[str] = set()
    iso_slugs: set[str] = set()

    for f in work_dir.iterdir():
        if not f.is_file():
            continue
        name = f.name
        if name.endswith(".bz2"):
            name = name[:-4]
        if not name.endswith(".states"):
            continue
        stem = name[:-7]  # strip '.states'
        if "__" not in stem:
            continue
        iso_slug, ds_name = stem.split("__", 1)
        if iso_slug and iso_slug[0].isdigit():
            ds_names.add(ds_name)
            iso_slugs.add(iso_slug)

    if not iso_slugs:
        raise ValidationError(
            f"No isotopologue data files found in '{work_dir}'. "
            "Expected files named '<iso_slug>__<ds_name>.states' "
            "(e.g. '27Al-1H__AloHa.states')."
        )
    if len(ds_names) > 1:
        raise ValidationError(
            f"Multiple dataset names detected in '{work_dir}': {sorted(ds_names)}. "
            "All files in a working directory must belong to the same dataset."
        )

    ds_name = ds_names.pop()
    logging.debug(f"validator: discovered ds_name='{ds_name}', iso_slugs={sorted(iso_slugs)}")
    return ds_name, sorted(iso_slugs)


def validate_work_dir(work_dir: Path) -> None:
    """Confirms work_dir exists and is a directory."""
    if not work_dir.is_dir():
        raise ValidationError(f"Work directory '{work_dir}' does not exist")


def validate_iso_files(work_dir: Path, iso_slug: str, ds_name: str) -> None:
    """
    Validates that work_dir contains exactly one .states file, exactly one .pf file,
    and at least one .trans file for the given iso_slug/ds_name. Spot-checks each file.
    """
    logging.info(f"validator: checking files for '{iso_slug}' in '{work_dir}'")

    states_all = _data_files(work_dir, iso_slug, ds_name, ".states")
    trans_all = _data_files(work_dir, iso_slug, ds_name, ".trans")
    pf_all = _data_files(work_dir, iso_slug, ds_name, ".pf")

    logging.debug(
        f"validator: '{iso_slug}' — "
        f"states={len(states_all)}, trans={len(trans_all)}, pf={len(pf_all)}"
    )

    if len(states_all) != 1:
        raise ValidationError(
            f"Expected exactly 1 .states file for '{iso_slug}', "
            f"found {len(states_all)}: {[p.name for p in states_all]}"
        )
    if len(pf_all) != 1:
        raise ValidationError(
            f"Expected exactly 1 .pf file for '{iso_slug}', "
            f"found {len(pf_all)}: {[p.name for p in pf_all]}. "
            f"Expected name: '{iso_slug}__{ds_name}.pf'"
        )
    if len(trans_all) < 1:
        raise ValidationError(
            f"Expected at least 1 .trans file for '{iso_slug}', found 0. "
            f"Expected naming: '{iso_slug}__{ds_name}[__<range>].trans[.bz2]'"
        )

    with tempfile.TemporaryDirectory() as tmpdir:
        _spot_check_states(_open_for_check(states_all[0], tmpdir))
        for raw in trans_all:
            _spot_check_trans(_open_for_check(raw, tmpdir))

    logging.info(f"validator: '{iso_slug}' passed")
