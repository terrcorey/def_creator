"""
DefContext: the shared state object that replaces all global variables.
Also provides the top-level run_init() and run_build() orchestration functions.
"""
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

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
        inp_path = ctx.inp_path()
        if inp_path.exists():
            inp_path.unlink()
            logging.info(f"context: --force: removed '{inp_path}'")
            print(f"  Removed existing: {inp_path}")
        for iso_slug in ctx.isotopologue_slugs():
            temp_path = ctx.def_json_temp_path(iso_slug)
            if temp_path.exists():
                temp_path.unlink()
                logging.info(f"context: --force: removed '{temp_path}'")
                print(f"  Removed existing: {temp_path}")

    # Step 1: validate files for each isotopologue
    for iso_slug in ctx.isotopologue_slugs():
        try:
            validator.validate_iso_files(ctx.work_dir, iso_slug, ctx.ds_name)
        except ValidationError as e:
            logging.error(f"context: validation failed for '{iso_slug}': {e}")
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

    for iso_slug in ctx.isotopologue_slugs():
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

    # Step 5: generate .inp
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
        print(f"\n  (Skipped writing '{inp_path}' — already exists; use --init --force to overwrite.)")
    else:
        inp_handler.write_inp(content, inp_path)

    print(f"\n--init complete.")
    print(f"  Temp cache: {[str(ctx.def_json_temp_path(s)) for s in ctx.isotopologue_slugs()]}")
    print(f"  Input template: {ctx.inp_path()}")
    print(f"\nFill in '{ctx.inp_path()}' and run again without --init to generate .def files.")


def run_build(ctx: DefContext, format_name: str = "exomol") -> None:
    """
    Standard (no --init) workflow:
      1. Parse .inp file
      2. Validate .inp content
      3. For each isotopologue: load .def.json temp cache, merge with user input, validate completeness
      4. Optionally derive InChI/InChIKey from SMILES
      5. Render .def file
    """
    logging.info(f"context: run_build for '{ctx.work_dir}' (ds_name='{ctx.ds_name}')")

    # Check .inp exists
    inp_path = ctx.inp_path()
    if not inp_path.exists():
        logging.error(
            f"context: input file '{inp_path}' not found. "
            f"Run with --init first to generate it."
        )
        sys.exit(1)

    # Step 1: parse .inp
    parsed = inp_handler.parse_inp(inp_path)
    dataset_user = parsed["dataset"]
    per_iso_user = parsed["per_isotopologue"]

    # Step 1b: validate .inp content (collect all errors before proceeding)
    known_iso_slugs = ctx.isotopologue_slugs()
    inp_errors, inp_warnings = inp_handler.validate_inp(inp_path, known_iso_slugs)

    if inp_warnings:
        print(f"\nNote — {len(inp_warnings)} thing(s) to verify in {inp_path.name}:\n")
        for i, warn in enumerate(inp_warnings, 1):
            lines = warn.split("\n")
            print(f"  {i}. {lines[0]}")
            for line in lines[1:]:
                print(f"     {line}")
            print()
        answer = input("Continue with build? [y/N] ").strip().lower()
        if answer != "y":
            print("Build cancelled.")
            sys.exit(0)

    if inp_errors:
        count = len(inp_errors)
        print(f"\nErrors in {inp_path.name} — {count} problem(s) found:\n")
        for i, err in enumerate(inp_errors, 1):
            lines = err.split("\n")
            print(f"  {i}. {lines[0]}")
            for line in lines[1:]:
                print(f"     {line}")
            print()
        print("Fix the above and re-run.")
        sys.exit(1)

    # Step 2–5: merge, validate, render per isotopologue
    rend = renderer.get_renderer(format_name)
    any_missing = False

    for iso_slug in ctx.isotopologue_slugs():
        logging.info(f"context: building '{iso_slug}'")

        # Load temp cache written by --init
        temp_path = ctx.def_json_temp_path(iso_slug)
        if not temp_path.exists():
            logging.error(
                f"context: temp cache '{temp_path}' not found. "
                f"Run with --init first."
            )
            sys.exit(1)
        with open(temp_path, "r", encoding="utf-8") as f:
            auto_data = json.load(f)

        # Build per-isotopologue user dict (merge dataset-level fields in)
        iso_user = dict(dataset_user)
        iso_user.update(per_iso_user.get(iso_slug, {}))

        # Derive per-isotopologue InChI/InChIKey from the dataset-level SMILES.
        base_smiles = dataset_user.get("smiles", "").strip()
        if not base_smiles:
            base_inchi = dataset_user.get("base_inchi", "").strip()
            if base_inchi:
                base_smiles = inchi_mod.smiles_from_inchi(base_inchi) or ""
                if base_smiles:
                    logging.info(f"context: derived base SMILES from InChI for '{iso_slug}'")
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
            any_missing = True
            continue

        # Render
        output_path = ctx.def_output_path(iso_slug)
        try:
            rend.render(merged, output_path)
            logging.info(f"context: wrote '{output_path}'")
            print(f"  Wrote: {output_path}")
        except Exception as e:
            logging.error(f"context: render failed for '{iso_slug}': {e}")
            any_missing = True
            continue

        # Write completed .def.json and remove temp file
        final_json_path = ctx.def_json_path(iso_slug)
        with open(final_json_path, "w", encoding="utf-8") as f:
            json.dump(merged, f, indent=4)
        temp_path.unlink()
        logging.info(f"context: wrote '{final_json_path}', removed temp '{temp_path}'")
        print(f"  Wrote: {final_json_path}")

    if any_missing:
        logging.error("context: build completed with errors — see log for details")
        sys.exit(1)
    else:
        print(f"\nBuild complete.")
