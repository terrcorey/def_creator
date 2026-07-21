"""
Standalone fetcher for ExoMol sample data: downloads a dataset/isotopologue's
.states/.trans/.pf files plus its published reference .def/.def.json from
ExoMol's public API (https://www.exomol.com/db/...) into a local directory.

Kept separate from create_def.py -- end users of the main tool never need
this; it exists to stock CI/dev fixtures without committing large data files
to git. Files already present (non-empty) in dest_dir are left alone, so
re-running only fetches what's missing.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import urllib.error
import urllib.request
from pathlib import Path

from extractor import slug_to_hill_formula_and_charge

_BASE_URL = "https://www.exomol.com/db"


def _trans_filenames(dataset_stem: str, def_json: dict | None, trans_files: int | None) -> list[str]:
    """
    Returns the .trans.bz2 filename(s) to fetch, given the dataset's parsed
    .def.json (or None if that fetch failed -- falls back to guessing a
    single unranged file, since most datasets aren't split).
    """
    n_files = (def_json or {}).get("dataset", {}).get("transitions", {}).get("number_of_transition_files", 1)
    if n_files <= 1:
        return [f"{dataset_stem}.trans.bz2"]

    if trans_files is None:
        raise ValueError(
            f"dataset has {n_files} split .trans files -- pass --trans-files N to pick how many to fetch"
        )

    max_wn = def_json["dataset"]["transitions"]["max_wavenumber"]
    step = max_wn / n_files
    bounds = [round(i * step) for i in range(n_files + 1)]
    return [
        f"{dataset_stem}__{bounds[i]:05d}-{bounds[i + 1]:05d}.trans.bz2"
        for i in range(min(trans_files, n_files))
    ]


def _fetch(url: str, dest: Path) -> bool:
    """Downloads url to dest unless dest already exists and is non-empty. Returns True on success."""
    if dest.exists() and dest.stat().st_size > 0:
        logging.info(f"fetch_exomol_sample: '{dest.name}' already cached, skipping")
        return True
    logging.info(f"fetch_exomol_sample: fetching '{url}'...")
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            dest.write_bytes(response.read())
        return True
    except urllib.error.URLError as e:
        logging.error(f"fetch_exomol_sample: FAILED '{url}': {e}")
        return False


def fetch_sample(iso_slug: str, dataset: str, dest_dir: Path, trans_files: int | None = None) -> bool:
    """
    Fetches .states/.trans/.pf plus ref/.def/.def.json for one dataset/
    isotopologue into dest_dir. A failed download is logged and skipped
    rather than stopping the rest; returns True only if every file needed
    was fetched (or already cached) successfully.
    """
    molecule, _ = slug_to_hill_formula_and_charge(iso_slug)
    base = f"{_BASE_URL}/{molecule}/{iso_slug}/{dataset}"
    stem = f"{iso_slug}__{dataset}"

    dest_dir.mkdir(parents=True, exist_ok=True)
    ref_dir = dest_dir / "ref"
    ref_dir.mkdir(exist_ok=True)

    ok = _fetch(f"{base}/{stem}.def", ref_dir / f"{stem}.def")

    def_json = None
    def_json_path = ref_dir / f"{stem}.def.json"
    if _fetch(f"{base}/{stem}.def.json", def_json_path):
        try:
            def_json = json.loads(def_json_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logging.error(f"fetch_exomol_sample: could not parse '{def_json_path}': {e}")
            ok = False
    else:
        ok = False
        logging.warning("fetch_exomol_sample: def.json unavailable -- guessing single-file .trans")

    ok &= _fetch(f"{base}/{stem}.states.bz2", dest_dir / f"{stem}.states.bz2")
    ok &= _fetch(f"{base}/{stem}.pf", dest_dir / f"{stem}.pf")

    try:
        for name in _trans_filenames(stem, def_json, trans_files):
            ok &= _fetch(f"{base}/{name}", dest_dir / name)
    except ValueError as e:
        logging.error(f"fetch_exomol_sample: {e}")
        ok = False

    return ok


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch an ExoMol dataset/isotopologue's sample data files for local use or CI fixtures.",
    )
    parser.add_argument("iso_slug", help="Isotopologue slug, e.g. 27Al-1H")
    parser.add_argument("dataset", help="Dataset name, e.g. AloHa")
    parser.add_argument("dest_dir", type=Path, help="Directory to fetch files into")
    parser.add_argument(
        "--trans-files", type=int, default=None,
        help="Number of split .trans range files to fetch, ascending from 0 cm^-1 "
             "(required if the dataset has more than one)",
    )
    parser.add_argument(
        "--log-level", default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: INFO)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level), format="%(levelname)s - %(message)s")

    ok = fetch_sample(args.iso_slug, args.dataset, args.dest_dir, args.trans_files)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
