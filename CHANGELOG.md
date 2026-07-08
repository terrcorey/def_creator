# Changelog

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
