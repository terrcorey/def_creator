# Changelog

## [0.5.2] — 2026-07-14 — Fixed bug that appeared in ExoTea

### Added
- **Installation instructions in README** — Quick start guide now includes venv setup and `pip install -r requirements.txt` steps for Linux, macOS, and Windows

### Fixed
- **`rdkit` missing from `requirements.txt`** — added; it's imported directly in `inchi.py` but was absent from the pinned dependency list

## [0.5.1] — 2026-07-09

### Added
- **Extraction progress output** — `--init` prints `Extracting data for N isotopologue(s)...` with a per-isotopologue `  <iso_slug>... done` line as each file is read, so the user can see progress during large file processing
- **"Next steps" footer in `.inp`** — generated `.inp` files end with a comment block reminding the user what command to run after filling in the file
- **Batch temp cache check in build** — `run_build` now checks that all temp `.def.json` cache files exist before starting any render work, listing every missing file at once rather than halting on the first one mid-loop
- **`--force` "nothing to remove" feedback** — if `--init --force` finds no existing `.inp` or temp cache files, it now prints a confirmation instead of silently continuing

### Changed
- **Centralized validation message strings** — all user-facing error and warning text is now collected in `_VALIDATION_ERRORS` and `_VALIDATION_WARNINGS` dicts at the top of `inp_handler.py`, and `_VALIDATOR_ERRORS` at the top of `validator.py`; logic in `validate_inp` and `validate_iso_files` calls `.format()` on these strings rather than embedding them inline — edit messages without touching validation logic
- **`--init` completion summary** rewritten to print dataset name, isotopologue list, temp cache paths one per line, and explicit numbered "Next steps" rather than a Python list repr
- **`quantum_case_label` validation errors** now include a link to `https://www.exomol.com/data/quantum-cases/`
- **`run_build` error/warning display** extracted into a shared `_print_errors()` helper in `context.py`

### Fixed
- **Error display double-indent** — validation error continuation lines (hints starting with `→`) were being indented twice; messages in `_VALIDATION_ERRORS` no longer carry leading whitespace, so the display loop's 5-space prefix produces consistent single-level indentation
- **Broken warning sentence** — the `num_quantum_types = 0` soft warning had two sentences concatenated without a newline separator, causing them to run together on one line

## [0.5.0] — 2026-07-09

### Changed
- **Flat working directory** — the required `{work_dir}/{iso_slug}/` subdirectory structure has been removed; all data files now live directly in the working directory alongside generated outputs. Users place files in any directory and the tool auto-detects everything from the file names.
- **File-name-based discovery** — `--init` and build scan the working directory for `*.states[.bz2]` files named `{iso_slug}__{ds_name}.states`; `ds_name` and the full isotopologue list are derived from these names. No manual configuration of dataset name or isotopologue list is required.
- **`DefContext`** — `ds_name` and `iso_slugs` are now discovered via `validator.discover_dataset()` at construction time rather than read from the directory name and subdirectory listing; `isotopologue_dirs()` replaced by `isotopologue_slugs()`.
- **Output paths are flat** — `.def`, `.def.json`, `__temp.def.json`, and `.inp` files are all written directly into the working directory (`{iso_slug}__{ds_name}.def` etc.).
- **`extractor` functions** — all functions that previously accepted `iso_dir: Path` now accept `(work_dir: Path, iso_slug: str, ds_name: str)` and search for files by name prefix rather than by directory.
- **`validator.validate_iso_files`** replaces `validate_iso_dir` — validates that the working directory contains exactly one `.states` file, exactly one `.pf` file, and at least one `.trans` file for each discovered iso_slug/ds_name combination; provides clear error messages including the expected filename pattern when files are missing.
- **`validator.discover_dataset`** — new function that scans `work_dir` for `*.states` files, parses `iso_slug`/`ds_name` from their stems, and raises `ValidationError` if no qualifying files are found or if multiple dataset names are detected.

## [0.4.0] — 2026-07-08

### Added
- **Nuclear spin degeneracy validation** — `extractor.nuclear_spin_degeneracy(iso_slug)` computes g_ns = Π(2Iᵢ+1) from mendeleev nuclear spin values (handles fraction strings such as `"5/2"`); used in `validate_inp`:
  - Error if any irrep degeneracy exceeds g_ns
  - Error if molecule has no equivalent nuclei and any irrep degeneracy ≠ g_ns (all irreps must share the same weight for heteronuclear molecules)
  - Equivalent-nuclei case (ortho/para split) is flagged informatively but not constrained beyond the g_ns ceiling
- **g_ns hint in `.inp` header** — `--init` auto-derives g_ns per isotopologue and adds it to the auto-derived header block with guidance on expected degeneracy values
- **Half-integer column type** — `summarise_states_columns` now detects columns where all values are multiples of 0.5 (e.g. half-integer J) and labels them `half-integer` rather than `float`

### Changed
- **SMILES and InChI promoted to `[dataset]` level** — base (non-isotopic) SMILES and InChI are now single fields in the `[dataset]` section, shared across all isotopologues; isotope mass numbers are assigned per-isotopologue automatically at build time via `inchi.derive_iso_inchi`; users no longer fill in per-isotopologue SMILES or InChI/InChIKey
- **Base SMILES and InChI auto-derived at `--init` time** — when SMILES can be auto-generated from the iso_slug, the corresponding base InChI is also computed; both are pre-filled in `[dataset]`
- **`generate_blank_inp`** accepts `base_smiles` and `base_inchi` as direct parameters; removes the previous stash that wrote `base_smiles` as a non-template field into `.def.json`
- **`run_init` signature** — removed unused `format_name` parameter
- **States column summary moved inline** — per-column type/range info is now shown as a trailing `# col N  type  range` comment on each quantum label line rather than in a separate block; unassigned columns appear as blank placeholder lines with the summary comment
- **Quantum label parser** strips inline `#` comments from label lines so the new inline column hints are ignored during parsing
- **Comment text centralised** — all user-facing instruction strings moved from `generate_blank_inp` into a module-level `_INP_COMMENTS` dict with a `_comment_lines` helper; edit comment text in one place without touching generation logic
- **Blank DOI now accepted** — `validate_inp` no longer errors on an empty `doi`; format is only validated when a non-empty value is provided

## [0.3.0] — 2026-07-07

### Added
- **`inchi.py`** — new module owning all InChI/SMILES logic (previously attempted via PubChem; now fully local):
  - `smiles_from_atoms(atoms, charge)` — auto-generates isotopologue SMILES from the iso_slug; chain `[massSymbol]...` notation for diatomics and all-distinct-element molecules; returns `None` for polyatomics with any repeated non-H element (user must supply)
  - `inchi_from_smiles(smiles)` — derives InChI + InChIKey via RDKit with `sanitize=False` fallback for radicals and non-octet molecules (e.g. AlH)
  - `inchikey_from_inchi(inchi)` — derives InChIKey from a manually-provided InChI string
- **`smiles` field** in `[isotopologue.*]` section of `.inp`: auto-filled where possible, with comment explaining whether it was derived or requires manual input
- **Three InChI/InChIKey workflows** at build time: (1) SMILES present → derive both; (2) InChI present, InChIKey blank → derive InChIKey; (3) all three provided manually → use as-is
- **SMILES validation** in `validate_inp`: if SMILES is provided and RDKit fails to produce InChI/InChIKey, a clear error is reported with instructions to correct the SMILES and clear/update the related fields
- **`--force` flag** for `--init`: deletes existing `.inp` and temp `.def.json` cache files before regenerating (without `--force`, existing `.inp` is never overwritten)
- **Soft warnings** in `validate_inp`: function now returns `(errors, warnings)` instead of a flat error list; warnings display before the build and require a `y/N` confirmation to proceed (errors still block immediately)
- Warning raised when `num_quantum_types = 0` — no quantum coupling-scheme namespace prefixes detected; non-blocking since some datasets legitimately have none

### Changed
- `extractor.py`: `extract_all` now accepts `smiles`, `inchi`, `inchikey` parameters (passed in from `context.py`; not re-derived internally)
- `extractor.py`: new public helper `slug_to_hill_formula_and_charge(iso_slug)` — builds Hill formula and extracts ionic charge from an iso_slug
- InChI/SMILES derivation moved entirely out of `extractor.py` into `inchi.py`; `context.py` orchestrates — SMILES generated once per isotopologue, PubChem removed

## [0.2.0] — 2026-06-30

### Added
- `--no-verbose-input` flag for `--init`: generates a comment-free `.inp` (states preview always retained)
- `quantum_case_label` validated against the exhaustive ExoMol list: `dcs`, `dos`, `lpcs`, `lpos`, `asymcs`, `asymos`, `stos`, `stcs`, `sphcs`, `sphos`
- `SourceType` and `Ecal` added to the standard Auxiliary label library — auto-fill on parse, no explicit format required
- States preview first-5-rows rendered via `df.to_string()` (column-aligned) instead of manual token join

### Fixed
- `shared_quantum_labels` bool parse now wrapped in try/except so `validate_inp` always runs even on invalid values
- `[quantum_labels*]` section lookup falls back to first matching section when `shared_quantum_labels = true`, so the section name doesn't need to be changed after toggling the flag
- States preview moved to just above the `[quantum_labels.*]` section (was above `[isotopologue.*]`)

### Validation
- DOI must start with `10.` and contain `/` (or be the literal `None`)
- `max_temperature` must be > 0
- Irrep degeneracy must be ≥ 0 (negative rejected; 0 accepted)
- `inchikey` must match the `XXXXXXXXXXXXXX-XXXXXXXXXX-X` regex pattern
- Unknown Auxiliary labels without explicit format strings now produce a clear error

## [0.1.0] — 2026-06-26

Initial structured release. Replaced the Excel-based `create_def_files.py` / `def_input.xlsm` workflow with a plain-text `.inp` pipeline.

### Added
- Two-step workflow: `--init` (extract + cache + generate template) and build (parse + merge + render)
- `create_def.py` — thin CLI with `--init`, `--format`, `--log-level` flags
- `context.py` — `DefContext` dataclass + `run_init` / `run_build` orchestration
- `extractor.py` — stateless extraction from `.states`, `.trans`, `.pf`; states column summary
- `inp_handler.py` — blank `.inp` generation (aligned columns, states preview, standard label lookup); `.inp` parsing with auto-detection of availability flags
- `merger.py` — deep merge of auto-derived and user fields; completeness validation
- `renderer.py` — `BaseRenderer` ABC + `ExoMolRenderer`
- `validator.py` — work-dir and iso-dir structure checks
- Standard label auto-fill from `standard_label_structure.json` (formats + descriptions)
- `shared_quantum_labels` option for datasets with multiple isotopologues sharing the same quantum label list
