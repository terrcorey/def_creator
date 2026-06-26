"""
DefContext: the shared state object that replaces all global variables.
Also provides the top-level run_init() and run_build() orchestration functions.
"""
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

import extractor
import inp_handler
import merger
import renderer
import validator
from validator import ValidationError


@dataclass
class DefContext:
    work_dir: Path

    @property
    def ds_name(self) -> str:
        return self.work_dir.name

    def isotopologue_dirs(self) -> list[tuple[str, Path]]:
        """Returns list of (iso_slug, iso_dir) for each isotopologue subdirectory."""
        result = []
        for d in sorted(self.work_dir.iterdir()):
            if d.is_dir() and d.name[0].isdigit():
                result.append((d.name, d))
        return result

    def def_json_path(self, iso_slug: str) -> Path:
        return self.work_dir / iso_slug / f"{iso_slug}__{self.ds_name}.def.json"

    def def_json_temp_path(self, iso_slug: str) -> Path:
        return self.work_dir / iso_slug / f"{iso_slug}__{self.ds_name}__temp.def.json"

    def inp_path(self) -> Path:
        return self.work_dir / f"{self.ds_name}.inp"

    def def_output_path(self, iso_slug: str) -> Path:
        return self.work_dir / iso_slug / f"{iso_slug}__{self.ds_name}.def"


def run_init(ctx: DefContext, format_name: str = "exomol") -> None:
    """
    --init workflow:
      1. Validate work directory and all isotopologue directories
      2. Extract auto-derivable fields for each isotopologue
      3. Write .def.json cache for each isotopologue
      4. Summarise .states columns for each isotopologue
      5. Generate and write the blank .inp template
    """
    logging.info(f"context: run_init for '{ctx.work_dir}' (ds_name='{ctx.ds_name}')")

    # Step 1: validate
    try:
        iso_slugs_list = validator.validate_work_dir(ctx.work_dir)
    except ValidationError as e:
        logging.error(f"context: validation failed: {e}")
        sys.exit(1)

    for iso_slug, iso_dir in ctx.isotopologue_dirs():
        try:
            validator.validate_iso_dir(iso_dir, iso_slug)
        except ValidationError as e:
            logging.error(f"context: validation failed for '{iso_slug}': {e}")
            sys.exit(1)

    # Step 2 & 3: extract and cache
    extracted: dict[str, dict] = {}
    states_summaries: dict[str, dict] = {}

    for iso_slug, iso_dir in ctx.isotopologue_dirs():
        logging.info(f"context: extracting data for '{iso_slug}'")
        data = extractor.extract_all(iso_slug, iso_dir, ctx.ds_name)
        extracted[iso_slug] = data

        temp_path = ctx.def_json_temp_path(iso_slug)
        temp_path.parent.mkdir(parents=True, exist_ok=True)
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        logging.info(f"context: wrote temp cache '{temp_path}'")

        # Step 4: states column summary
        logging.info(f"context: summarising states columns for '{iso_slug}'")
        states_summaries[iso_slug] = extractor.summarise_states_columns(iso_dir)

    # Step 5: generate .inp
    iso_slugs = [slug for slug, _ in ctx.isotopologue_dirs()]
    content = inp_handler.generate_blank_inp(
        ds_name=ctx.ds_name,
        iso_slugs=iso_slugs,
        states_summaries=states_summaries,
        extracted_data=extracted,
    )
    inp_path = ctx.inp_path()
    if inp_path.exists():
        logging.warning(
            f"context: '{inp_path}' already exists — not overwriting. "
            f"Delete it manually to regenerate."
        )
        print(f"\n  (Skipped writing '{inp_path}' — file already exists.)")
    else:
        inp_handler.write_inp(content, inp_path)

    print(f"\n--init complete.")
    print(f"  Temp cache: {[str(ctx.def_json_temp_path(s)) for s, _ in ctx.isotopologue_dirs()]}")
    print(f"  Input template: {ctx.inp_path()}")
    print(f"\nFill in '{ctx.inp_path()}' and run again without --init to generate .def files.")


def run_build(ctx: DefContext, format_name: str = "exomol") -> None:
    """
    Standard (no --init) workflow:
      1. Validate work directory
      2. Parse .inp file
      3. For each isotopologue: load .def.json cache, merge with user input, validate completeness
      4. Optionally derive InChI/InChIKey from SMILES
      5. Render .def file
    """
    logging.info(f"context: run_build for '{ctx.work_dir}' (ds_name='{ctx.ds_name}')")

    # Step 1: validate work dir
    try:
        validator.validate_work_dir(ctx.work_dir)
    except ValidationError as e:
        logging.error(f"context: {e}")
        sys.exit(1)

    # Check .inp exists
    inp_path = ctx.inp_path()
    if not inp_path.exists():
        logging.error(
            f"context: input file '{inp_path}' not found. "
            f"Run with --init first to generate it."
        )
        sys.exit(1)

    # Step 2: parse .inp
    parsed = inp_handler.parse_inp(inp_path)
    dataset_user = parsed["dataset"]
    per_iso_user = parsed["per_isotopologue"]

    # Step 3–5: merge, validate, render per isotopologue
    rend = renderer.get_renderer(format_name)
    any_missing = False

    for iso_slug, iso_dir in ctx.isotopologue_dirs():
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
        output_path.parent.mkdir(parents=True, exist_ok=True)
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
