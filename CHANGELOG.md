# Changelog

## Upcoming features/tests

v1 targets a polished tool for generating the base ExoMol template only. Broadening and photodissociation data will get their own def-template structures in a future v2, once the tool is generalized to support multiple template types.

1. **ExoMol sample downloader** — a general-purpose, standalone script (kept separate from `create_def.py`, which end users never need for this) that fetches a dataset/isotopologue's `.states`/`.trans`/`.pf` files, and its published reference `.def`/`.def.json`, from ExoMol's public API into a local cache directory — checking that directory first and only downloading what's missing. Nothing it fetches is committed to the repo; CI runs it as a setup step before `--init`/build for each fixture.
   - **`AloHa` migrates to this pattern** — its currently-committed `.states`/`.trans`/`ref/*.def*` are removed from git in favor of fetch-on-demand, so every CI fixture follows one consistent approach
   - **New fixture: `AloHa` isotopologue `27Al-2H`** (AlD) — added alongside the existing `27Al-1H` to exercise the multi-isotopologue-per-dataset build path, which nothing currently in CI covers
   - **New fixture: CO2 `Dozen`, isotopologue `12C-16O2`** — a recent (September 2025) 12-isotopologue CO2 line list; fetches the full `.states`/`.pf` plus 2 of its 20 wavenumber-range `.trans` files. Exercises both the repeated-element manual SMILES/InChI entry path (CO2 has two oxygens, same as the `SO2` example already in the README) and multi-`.trans`-file handling, neither of which any current fixture covers
   - Once this exists, `COmet` could rejoin the CI matrix the same way — fetched rather than committed — sidestepping its 589MB `.trans` file; not committed to for the next session, just noted as a natural follow-on

## [0.6.1] — 2026-07-16 — CI smoke test

### Added
- **GitHub Actions CI** (`.github/workflows/ci.yml`) — runs on every push/PR to `master`, across a `ubuntu-latest` / `windows-latest` / `macos-latest` × Python 3.12 matrix. Installs dependencies, runs the full `--init` → build pipeline against `samples/AloHa/27Al-1H`, and diffs the output against the committed `ref/*.def`/`*.def.json`. CAS registry number lookup uses a live API call, gated on a `CAS_API_KEY` secret stored in a GitHub Environment named `.env`
- **`.github/scripts/check_aloha_ref.py`** — the reference-diff check used by CI. Masks three pre-existing, tracked gaps rather than failing on them every run: mendeleev-derived isotopologue mass precision vs. the originally published mass, the missing `broad`/broadening section (out of scope for v1 — see roadmap above), and one standard-label description wording mismatch (`v`'s library description reads "State vibrational quantum number"; the original AloHa `.def` uses "Vibrational quantum number")

### Changed
- **`samples/AloHa/AloHa.inp`** — `version_date`, `doi`, and `continuum` filled in to match the real published AloHa dataset, so a correct build now reproduces the committed reference for those fields (previously blank/incorrect, which meant even a correct build could never match `ref/`)

### Scope
CI currently covers `AloHa` only. `COmet` is excluded — its `.trans` file (589MB) isn't committed to the repo, so CI has no data to check out for it. It'll be added once the ExoMol sample downloader (next goal, above) can fetch it at CI-time instead.

### Verified
- Full `--init` → build pipeline run locally against `samples/AloHa/27Al-1H`: output matches `ref/` once the three tracked gaps above are accounted for
- `check_aloha_ref.py` correctly flags a genuine regression (verified by injecting a fake field change into a built output and confirming the check fails)
- Not yet exercised on GitHub Actions itself — this will be confirmed on the first push

## [0.6.0] — 2026-07-15 — CAS registry number auto-fill

### Added
- **`cas.py`** — new module, `cas_rn_from_inchikey()` looks up a CAS Registry Number by InChIKey via the [CAS Common Chemistry API](https://commonchemistry.cas.org/api). Implemented as a ~15-line `urllib`/`json` call rather than the `PyComChem` package originally suggested for this — that package's `comchem/__init__.py` does a hard top-level `import cairosvg` (needed only for its unrelated image-export feature), which would have pulled in `cairosvg`/`cairocffi`/`pillow`/`cffi`/`pycparser`/`cssselect2`/`defusedxml`/`tinycss2`/`webencodings` (9 packages) for functionality this project doesn't use
- **`.env` support** — `cas._load_dotenv()` reads a gitignored `KEY=VALUE` `.env` file in the project root and populates `os.environ` (only for keys not already set), so `CAS_API_KEY` doesn't need to be exported in every shell session. No `python-dotenv` dependency added for one variable. `.env` added to `.gitignore`
- **`extractor.main_isotopologue_slug(iso_slugs)`** — returns the isotopologue built from each element's most naturally abundant isotope (via the same `mendeleev` abundance data already used for nuclear spin degeneracy), e.g. picks `1H2-16O` over `2H2-16O`/`1H2-18O` for water, `12C-16O` over `13C-16O` for carbon monoxide
- **`context.run_build`** — looks up the CAS RN once per dataset by the *base* (non-isotopic) InChIKey (derived from the dataset-level SMILES — the same molecule `derive_iso_inchi` already uses), and writes it only to the main isotopologue's `.def`/`.def.json`. Minor (isotopically substituted) isotopologues are left blank, since CAS Common Chemistry registers the parent molecule, not isotope-labeled variants — confirmed against `samples/AloHa`, where AlH's registered entry (CAS `13967-22-1`) uses the base InChIKey rather than an isotope-labeled one. A user-supplied `cas_registry_number` in the `.inp` (dataset- or isotopologue-level) always takes precedence and is never overwritten
- **README / `.inp` template** — `cas_registry_number` field docs updated to describe the auto-fill behavior, the main-isotopologue-only scope, and the `CAS_API_KEY`/`.env` setup

### Verified
- `python3 cas.py` self-check passes (mocked: single match, zero matches, ambiguous multi-match)
- Live API smoke-tested with a real `CAS_API_KEY`: aspirin (`BSYNRYMUTXBXSQ-UHFFFAOYSA-N` → `50-78-2`) resolves correctly; water (`XLYOFNOQVPJJNP-UHFFFAOYSA-N`) correctly returns no match (30 loosely-related substances — hydrates/clusters/isotopologues — trigger the ambiguous-match guard rather than guessing)
- Full `--init` → build against `samples/AloHa/27Al-1H`: output CAS RN (`13967-22-1`) now matches the committed reference exactly; all other diffs are the pre-existing ones already documented in 0.5.4 (unrelated to this change)
- Full `--init` → build against `samples/COmet`: output byte-identical to the committed reference (the ion isn't in Common Chemistry's database, so the field is correctly left blank, changing nothing)
- `extractor.main_isotopologue_slug` spot-checked against water and CO isotopologue sets (see Added, above)
- Bad/missing API key against the live endpoint: logs a warning, returns `None`, does not crash the build

## [0.5.4] — 2026-07-15 — Python 3.8 compatibility backport

### Changed
- **Minimum Python version lowered from 3.10 to 3.8** — the codebase used PEP 604 union syntax (`X | None`, 12 occurrences) and PEP 585 generics (`list[...]`/`dict[...]`/`tuple[...]`, 49 occurrences) throughout type annotations, both of which raise `TypeError` at import time on Python < 3.9/3.10. Since every occurrence was confined to annotations (no runtime `isinstance`/introspection on these types anywhere in the codebase), added `from __future__ import annotations` (PEP 563, supported since 3.7) as the first statement in `context.py`, `extractor.py`, `merger.py`, `renderer.py`, `inchi.py`, `validator.py`, and `inp_handler.py` — defers all annotations to strings, no per-annotation rewrite needed
- **`create_def.py`** — replaced `argparse.BooleanOptionalAction` (3.9+ only) with a plain `--no-verbose-input` / `store_false` flag; matches what the README already documented (the auto-generated `--verbose-input` positive form was never documented or needed)
- **`requirements.txt`** pins lowered to versions with `Requires-Python` floors at or below 3.8: `pandas` 2.3.3 → 2.0.3, `mendeleev` 1.1.0 → 0.16.2, `rdkit` 2026.3.3 → 2024.3.5 (latest release with a `cp38` wheel; PyPI declares no `Requires-Python` for any rdkit release)
- **README** — "Requires Python 3.10+" → "Requires Python 3.8+"
- **`samples/AloHa/AloHa.inp`** filled in with real values (point_group, irreps, quantum_case_label, max_temperature, etc.) — previously checked in as a blank `--init`-generated template, which meant this fixture couldn't reproduce the checked-in `samples/AloHa/27Al-1H/ref/*.def*` output

### Verified
No Python 3.8/3.9 interpreter was available locally or on the host, so verification used `podman` (already installed, rootless, on the Fedora host via `flatpak-spawn --host`) against the official `python:3.8` Docker Hub image (3.8.20):
- All 8 modules import cleanly under 3.8.20 with the new pins
- Full `--init` + build pipeline against `samples/COmet`: output `.def`/`.def.json` byte-identical to the committed reference
- Full pipeline against `samples/AloHa/27Al-1H`: ran without error; remaining diffs vs. `ref/` traced to the reconstructed `.inp` not being the literal original (missing optional `cas_registry_number`/`doi`, a `continuum` flag set differently, an older `version_date`) plus a pre-existing renderer limitation (no `broad`/broadening section support at all) — none caused by this backport
- Directly compared `mendeleev==0.16.2` vs. the old `1.1.0` pin for the isotope masses used in this dataset (Al-27, H-1): bit-for-bit identical (`27.989363439898` both), confirming the dependency downgrade introduces no precision regression

## [0.5.3] — 2026-07-14 — Windows/macOS compatibility pass

### Fixed
- **Missing `encoding="utf-8"` on text file opens in `extractor.py`** — `extract_states_info`, `_load_state_energies`, and `extract_transitions_info` opened `.states`/`.trans` files without an explicit encoding, falling back to the platform's locale-preferred encoding (typically not UTF-8 on Windows); a non-ASCII byte in a data file that read fine on Linux could raise `UnicodeDecodeError` on Windows
- **UTF-8 BOM breaks `.inp` parsing on Windows** — `inp_handler._read_sections` now opens with `encoding="utf-8-sig"`; previously, a BOM added by a Windows text editor on save would prepend `﻿` to the first line, causing the first `[section]` header to go undetected and be reported as a missing section
- **No `.gitattributes`** — added, marking `.bz2`/`.states`/`.trans`/`.pf` as binary as a backstop against Git's `core.autocrlf` (default on Windows) corrupting them on checkout

### Changed
- **Removed the single-implementation renderer registry** — `renderer.py`'s `BaseRenderer` ABC, `REGISTRY`, and `get_renderer()` factory existed for exactly one format (ExoMol); replaced with a plain `render()` function. The now-pointless `--format` CLI flag was dropped from `create_def.py`/`context.py`/README along with it
- **Deduplicated file-discovery and `.bz2`-decompression helpers** — `_data_files`/`_open_maybe_bz2` were defined identically in both `validator.py` and `extractor.py`; `extractor.py` now imports them from `validator.py`
- **Deduplicated the diacritic-stripping helper** — `renderer._to_ascii` and `inp_handler`'s local `_ascii` closure were identical; consolidated into `config.to_ascii()`, used by both
- **Simplified `slug_to_formula`** — replaced a 20-line char-list reverse/insert/reverse routine with a short `rstrip`-based helper; verified against known slug shapes (`27Al-1H`, `12C-16O2`, `12C-16O_p`, etc.)
- **Removed dead code in `merger.py`** — `_set_nested()` was defined but never called; `_REQUIRED_PATHS` had a duplicate `("dataset", "states", "max_energy")` entry

Verified by running the full `--init` → build pipeline against the `COmet` sample end-to-end: output `.def` is byte-identical to the committed reference, and a BOM-prefixed `.inp` now builds successfully (previously would misreport a missing `[options]` section).

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
