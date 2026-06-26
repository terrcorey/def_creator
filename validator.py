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


def validate_work_dir(work_dir: Path) -> list[str]:
    """
    Validates that work_dir exists and contains at least one isotopologue directory
    (a directory whose name starts with a digit).
    Returns the list of iso_slug names found.
    """
    if not work_dir.is_dir():
        raise ValidationError(f"Work directory '{work_dir}' does not exist")
    iso_slugs = [
        d.name for d in sorted(work_dir.iterdir())
        if d.is_dir() and d.name[0].isdigit()
    ]
    if not iso_slugs:
        raise ValidationError(
            f"No isotopologue directories found in '{work_dir}'. "
            "Expected subdirectories whose names start with a digit (e.g. '27Al-1H')."
        )
    logging.debug(f"validator: found isotopologues: {iso_slugs}")
    return iso_slugs


def _data_files(iso_dir: Path, ext: str) -> list[Path]:
    """Plain files first; .bz2 only when no plain version exists for that stem."""
    plain = list(iso_dir.rglob(f"*{ext}"))
    plain_set = set(plain)
    bz2 = [p for p in iso_dir.rglob(f"*{ext}.bz2") if p.with_suffix("") not in plain_set]
    return plain + bz2


def validate_iso_dir(iso_dir: Path, iso_slug: str) -> None:
    """
    Validates that iso_dir contains exactly one .states file, exactly one .pf file,
    and at least one .trans file (compressed or uncompressed). Spot-checks each.
    Treats a file and its .bz2 counterpart as a single file.
    """
    logging.info(f"validator: checking '{iso_slug}' in '{iso_dir}'")

    states_all = _data_files(iso_dir, ".states")
    trans_all = _data_files(iso_dir, ".trans")
    pf_all = list(iso_dir.rglob("*.pf"))

    logging.debug(
        f"validator: '{iso_slug}' — "
        f"states={len(states_all)}, trans={len(trans_all)}, pf={len(pf_all)}"
    )

    if len(states_all) != 1:
        raise ValidationError(
            f"Expected exactly 1 .states/.states.bz2 for '{iso_slug}', "
            f"found {len(states_all)}: {[p.name for p in states_all]}"
        )
    if len(pf_all) != 1:
        raise ValidationError(
            f"Expected exactly 1 .pf for '{iso_slug}', found {len(pf_all)}"
        )
    if len(trans_all) < 1:
        raise ValidationError(
            f"Expected at least 1 .trans/.trans.bz2 for '{iso_slug}', found 0"
        )

    with tempfile.TemporaryDirectory() as tmpdir:
        _spot_check_states(_open_for_check(states_all[0], tmpdir))
        for raw in trans_all:
            _spot_check_trans(_open_for_check(raw, tmpdir))

    logging.info(f"validator: '{iso_slug}' passed")
