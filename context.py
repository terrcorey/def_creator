"""
DefContext: the shared state object that replaces all global variables.
Also provides the top-level run_init() and run_build() orchestration functions.
"""
from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

import cas
import extractor
import inchi as inchi_mod
import inp_handler
import merger
import renderer
import validator
from validator import ValidationError


@dataclass
class DefContext:
    work_dir: Path
    ds_name: str = field(init=False)
    iso_slugs: list[str] = field(init=False)

    def __post_init__(self):
        self.ds_name, self.iso_slugs = validator.discover_dataset(self.work_dir)

    def isotopologue_slugs(self) -> list[str]:
        return list(self.iso_slugs)

    def def_json_path(self, iso_slug: str) -> Path:
        return self.work_dir / f"{iso_slug}__{self.ds_name}.def.json"

    def def_json_temp_path(self, iso_slug: str) -> Path:
        return self.work_dir / f"{iso_slug}__{self.ds_name}__temp.def.json"

    def inp_path(self) -> Path:
        return self.work_dir / f"{self.ds_name}.inp"

    def def_output_path(self, iso_slug: str) -> Path:
        return self.work_dir / f"{iso_slug}__{self.ds_name}.def"


def _print_errors(items: list[str], label: str) -> None:
    """Prints a numbered list of validation errors or warnings with consistent indentation."""
    for i, msg in enumerate(items, 1):
        lines = msg.split("\n")
        print(f"  {i}. {lines[0]}")
        for line in lines[1:]:
            print(f"     {line}")
        print()


def run_init(ctx: DefContext, verbose_input: bool = True, force: bool = False) -> None:
    """
    --init workflow:
      1. Validate required files exist for each isotopologue
      2. Extract auto-derivable fields for each isotopologue
      3. Write .def.json temp cache for each isotopologue
      4. Summarise .states columns for each isotopologue
      5. Generate and write the blank .inp template
    """
    logging.info(f"context: run_init for '{ctx.work_dir}' (ds_name='{ctx.ds_name}', force={force})")

    # If --force, remove existing .inp and temp caches before regenerating
    if force:
        removed = 0
        inp_path = ctx.inp_path()
        if inp_path.exists():
            inp_path.unlink()
            logging.info(f"context: --force: removed '{inp_path}'")
            print(f"  Removed: {inp_path}")
            removed += 1
        for iso_slug in ctx.isotopologue_slugs():
            temp_path = ctx.def_json_temp_path(iso_slug)
            if temp_path.exists():
                temp_path.unlink()
                logging.info(f"context: --force: removed '{temp_path}'")
                print(f"  Removed: {temp_path}")
                removed += 1
        if removed == 0:
            print("  (Nothing to remove — no existing .inp or temp cache files found.)")
        print()

    # Step 1: validate files for each isotopologue
    for iso_slug in ctx.isotopologue_slugs():
        try:
            validator.validate_iso_files(ctx.work_dir, iso_slug, ctx.ds_name)
        except ValidationError as e:
            logging.error(f"context: validation failed for '{iso_slug}': {e}")
            print(f"\nValidation error for '{iso_slug}':")
            for line in str(e).split("\n"):
                print(f"  {line}")
            sys.exit(1)

    # Step 2 & 3: extract and cache
    # Auto-derive base SMILES (and base InChI) for pre-filling [dataset] in the .inp.
    # All isotopologues in a dataset share the same molecule, so one derivation suffices.
    iso_slugs_all = ctx.isotopologue_slugs()
    base_smiles_prefill = ""
    base_inchi_prefill = ""
    if iso_slugs_all:
        atoms0, charge0 = extractor.expand_slug_atoms(iso_slugs_all[0])
        auto_smiles = inchi_mod.base_smiles_from_atoms(atoms0, charge0)
        if auto_smiles:
            base_smiles_prefill = auto_smiles
            result0 = inchi_mod.inchi_from_smiles(auto_smiles)
            if result0:
                base_inchi_prefill = result0[0]
            logging.info(f"context: auto-derived base SMILES '{base_smiles_prefill}'")
        else:
            logging.info("context: base SMILES could not be auto-derived (repeated elements) — user must supply")

    extracted: dict[str, dict] = {}
    states_summaries: dict[str, dict] = {}
    n = len(iso_slugs_all)

    print(f"Extracting data for {n} isotopologue(s)...")
    for iso_slug in ctx.isotopologue_slugs():
        print(f"  {iso_slug}...", end="", flush=True)
        logging.info(f"context: extracting data for '{iso_slug}'")
        data = extractor.extract_all(iso_slug, ctx.work_dir, ctx.ds_name)
        extracted[iso_slug] = data

        temp_path = ctx.def_json_temp_path(iso_slug)
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        logging.info(f"context: wrote temp cache '{temp_path}'")

        # Step 4: states column summary
        logging.info(f"context: summarising states columns for '{iso_slug}'")
        states_summaries[iso_slug] = extractor.summarise_states_columns(
            ctx.work_dir, iso_slug, ctx.ds_name
        )
        print(" done")

    # Step 5: generate .inp
    print()
    content = inp_handler.generate_blank_inp(
        ds_name=ctx.ds_name,
        iso_slugs=ctx.isotopologue_slugs(),
        states_summaries=states_summaries,
        extracted_data=extracted,
        verbose=verbose_input,
        base_smiles=base_smiles_prefill,
        base_inchi=base_inchi_prefill,
    )
    inp_path = ctx.inp_path()
    if inp_path.exists():
        logging.warning(f"context: '{inp_path}' already exists — skipping (use --force to overwrite)")
        print(f"  Skipped: '{inp_path.name}' already exists (use --init --force to overwrite)")
    else:
        inp_handler.write_inp(content, inp_path)
        print(f"  Written: {inp_path}")

    print()
    print("--init complete.")
    print()
    n_iso = len(ctx.isotopologue_slugs())
    print(f"  Dataset:  {ctx.ds_name}")
    print(f"  Isotopologues ({n_iso}): {', '.join(ctx.isotopologue_slugs())}")
    print()
    print("  Temp cache files written:")
    for s in ctx.isotopologue_slugs():
        print(f"    {ctx.def_json_temp_path(s)}")
    print()
    print("  Next steps:")
    print(f"  1. Fill in '{inp_path.name}'")
    print(f"  2. Run: python create_def.py {ctx.work_dir}")
    print()


def run_build(ctx: DefContext) -> None:
    """
    Standard (no --init) workflow:
      1. Parse and validate .inp file
      2. For each isotopologue: load .def.json temp cache, merge with user input, validate completeness
      3. Optionally derive InChI/InChIKey from SMILES
      4. Render .def file
    """
    logging.info(f"context: run_build for '{ctx.work_dir}' (ds_name='{ctx.ds_name}')")

    # Check .inp exists
    inp_path = ctx.inp_path()
    if not inp_path.exists():
        logging.error(
            f"context: input file '{inp_path}' not found. "
            f"Run with --init first to generate it."
        )
        print(f"\nInput file not found: {inp_path}")
        print(f"  → Run '--init' first to generate it.")
        sys.exit(1)

    # Check all temp caches exist before doing any work
    missing_caches = [
        iso_slug for iso_slug in ctx.isotopologue_slugs()
        if not ctx.def_json_temp_path(iso_slug).exists()
    ]
    if missing_caches:
        print(f"\n{len(missing_caches)} temp cache file(s) missing — run '--init' first:")
        for slug in missing_caches:
            print(f"  (missing) {ctx.def_json_temp_path(slug)}")
        sys.exit(1)

    # Parse .inp
    parsed = inp_handler.parse_inp(inp_path)
    dataset_user = parsed["dataset"]
    per_iso_user = parsed["per_isotopologue"]

    # Validate .inp content — collect all errors before proceeding
    known_iso_slugs = ctx.isotopologue_slugs()
    inp_errors, inp_warnings = inp_handler.validate_inp(inp_path, known_iso_slugs)

    if inp_warnings:
        print(f"\nNote — {len(inp_warnings)} thing(s) to verify in {inp_path.name}:\n")
        _print_errors(inp_warnings, "warning")
        answer = input("Continue with build? [y/N] ").strip().lower()
        if answer != "y":
            print("Build cancelled.")
            sys.exit(0)

    if inp_errors:
        print(f"\n{len(inp_errors)} error(s) in {inp_path.name}:\n")
        _print_errors(inp_errors, "error")
        print("Fix the above and re-run.")
        sys.exit(1)

    # Resolve dataset-level base SMILES once (shared across all isotopologues).
    base_smiles = dataset_user.get("smiles", "").strip()
    if not base_smiles:
        base_inchi = dataset_user.get("base_inchi", "").strip()
        if base_inchi:
            base_smiles = inchi_mod.smiles_from_inchi(base_inchi) or ""
            if base_smiles:
                logging.info("context: derived base SMILES from InChI")

    # Look up the dataset's CAS Registry Number once, by the base (non-isotopic)
    # InChIKey — Common Chemistry registers the un-isotope-labeled molecule, so a
    # per-isotopologue (isotope-labeled) InChIKey lookup would almost always miss.
    dataset_cas_rn = None
    if base_smiles:
        base_result = inchi_mod.inchi_from_smiles(base_smiles)
        if base_result:
            dataset_cas_rn = cas.cas_rn_from_inchikey(base_result[1])
            if dataset_cas_rn:
                logging.info(f"context: auto-derived CAS RN '{dataset_cas_rn}' for dataset")

    # The CAS RN above isn't isotope-specific, so it belongs on the main isotopologue's
    # .def file only; minor (isotopically substituted) isotopologues are left blank.
    main_slug = extractor.main_isotopologue_slug(ctx.isotopologue_slugs())

    # Merge, validate, render per isotopologue
    any_failed = False

    for iso_slug in ctx.isotopologue_slugs():
        logging.info(f"context: building '{iso_slug}'")

        temp_path = ctx.def_json_temp_path(iso_slug)
        with open(temp_path, "r", encoding="utf-8") as f:
            auto_data = json.load(f)

        # Build per-isotopologue user dict (merge dataset-level fields in)
        iso_user = dict(dataset_user)
        iso_user.update(per_iso_user.get(iso_slug, {}))

        if not iso_user.get("cas_registry_number") and dataset_cas_rn and iso_slug == main_slug:
            iso_user["cas_registry_number"] = dataset_cas_rn

        # Derive per-isotopologue InChI/InChIKey from the dataset-level SMILES.
        if base_smiles:
            atoms, _ = extractor.expand_slug_atoms(iso_slug)
            result = inchi_mod.derive_iso_inchi(base_smiles, atoms, iso_slug=iso_slug)
            if result:
                iso_user["inchi"], iso_user["inchikey"] = result
                logging.info(f"context: derived isotopologue InChI/InChIKey for '{iso_slug}'")

        # Merge auto + user
        merged = merger.merge_iso(auto_data, iso_user)

        # Validate completeness
        missing = merger.validate_complete(merged, iso_slug)
        if missing:
            logging.error(
                f"context: '{iso_slug}' is missing required fields:\n"
                + "\n".join(f"  - {m}" for m in missing)
            )
            any_failed = True
            continue

        # Render
        output_path = ctx.def_output_path(iso_slug)
        try:
            renderer.render(merged, output_path)
            logging.info(f"context: wrote '{output_path}'")
            print(f"  Wrote: {output_path}")
        except Exception as e:
            logging.error(f"context: render failed for '{iso_slug}': {e}")
            any_failed = True
            continue

        # Write completed .def.json and remove temp file
        final_json_path = ctx.def_json_path(iso_slug)
        with open(final_json_path, "w", encoding="utf-8") as f:
            json.dump(merger.strip_null_optional(merged), f, indent=4)
        temp_path.unlink()
        logging.info(f"context: wrote '{final_json_path}', removed temp '{temp_path}'")
        print(f"  Wrote: {final_json_path}")

    if any_failed:
        logging.error("context: build completed with errors — see log for details")
        sys.exit(1)
    else:
        print(f"\nBuild complete.")
