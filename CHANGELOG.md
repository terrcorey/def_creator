# Changelog

## Upcoming features/tests

v1 targets a polished tool for generating the base ExoMol template only. Broadening and photodissociation data will get their own def-template structures in a future v2, once the tool is generalized to support multiple template types.

1. **Extend CI coverage** — three gaps identified after shipping `--force` in 0.10.0:
   - `ci.yml` hardcodes Python 3.12 only, with no matrix dimension for interpreter version. The README claims "Requires Python 3.8+" but nothing has continuously verified that floor since it was hand-tested via podman back in v0.5.4 — add Python 3.8 as a second matrix dimension alongside 3.12, across all three OSes (full 3×2 matrix)
   - `test_fetch_exomol_sample.py` and `test_force_override.py` are self-checks that exist but are never actually invoked by `ci.yml` — wire both in as CI steps, placed right after `pip install` so they fail fast before any network fetch is spent
   - Nothing in CI exercises the `--force` path at all — add `.github/scripts/check_force_override.py` (same standalone-script pattern as `check_aloha_ref.py`), riding along in the existing AloHa job step reusing already-fetched `27Al-1H` data: corrupt a copy of `AloHa.inp`'s `27Al-1H` section (non-numeric `max_temperature`, blank `point_group`, out-of-range irreps degeneracy, invalid `quantum_case_label`), assert the build exits 1 without `--force`, then exits 0 with `--force` and writes the raw/blank values through correctly (including no literal `"None"` from a blank required field)

`COmet` cannot rejoin the CI matrix via `fetch_exomol_sample.py` — it isn't a published/live dataset on exomol.com yet, so there's nothing there to fetch. Revisit if/when it's published.

## [0.10.0] — 2026-07-22 — Assistive/overridable validation via --force

### Added
- **`--force` flag (build step)** — pushes the build past `.inp` validation errors and missing required fields instead of blocking, writing best-effort output (raw/blank values where a field couldn't be resolved) rather than refusing to build. Also auto-confirms the existing warnings `y/N` prompt. Errors and missing fields are always printed in full regardless of `--force`, with a banner naming what was overridden. Deliberately all-or-nothing rather than a per-check allowlist — this is an internal tool for expert (Masters-level) users who know their data, not a general-audience one, and there's no guarantee the ExoMol `.def` schema stays fixed enough to justify hardcoding which checks are "safe" to relax
- **`parse_inp` preserves raw values on failed coercion** — a non-blank `version_date`/`max_temperature`/isotopologue boolean flag that fails its normal type parse is now kept as raw text instead of being silently dropped, so `--force` has something to write through instead of an empty field

### Changed
- **`--init`'s wipe-and-regenerate flag renamed `--force` → `--reset-input`** — frees up `--force` for the build-time meaning above; the two were unrelated operations sharing a confusing name

### Fixed
- **`.def` rendered the literal text `"None"`** for any required field left unresolved — `renderer._fmt_line` passed a `None` value through `str()` rather than treating it as blank. Most user-suppliable fields default to explicit `None` in the extraction schema, and `dict.get(key, "")` only applies its fallback when the key is absent, not when it's present with value `None`. Only reachable once `--force` could push a build past a missing required field, but the underlying bug predates this change

### Scope
Kept unconditionally blocking, with no `--force` override: `validator.py`'s file-discovery/structural checks (missing work directory, no matching files, wrong file counts, ambiguous dataset names, too-few-columns spot checks). These guard against there being no file or column to read at all, not an unusual value in one, and they run before `--init`/build has a `.inp` to check anything against.

### Verified
- Full `--init` → build pipeline for `samples/AloHa` (both isotopologues) and `samples/COmet` rebuilds clean with no `--force` passed: AloHa still matches its reference modulo the same 3 pre-existing documented gaps, COmet still byte-identical
- A deliberately broken `AloHa.inp` (invalid `max_temperature`, blank `point_group`, out-of-range irreps degeneracy, unrecognized `quantum_case_label`) correctly blocks without `--force` (exit 1, all 5 errors printed) and correctly builds with `--force` (exit 0), writing the raw/blank values through and printing everything it overrode
- `test_force_override.py` — new self-check covering `parse_inp`'s raw-value preservation and the `None`-renders-blank fix

## [0.9.1] — 2026-07-21 — Fix Python 3.12 CI crash from the v0.9.0 streaming fix

### Fixed
- **`--init` crashed on every CI platform** with `AttributeError: 'BZ2File' object has no attribute 'name'` — v0.9.0's streaming rewrite of `_open_maybe_bz2` read `.name` off the bz2-wrapped file handle for error/debug messages in `_spot_check_states`/`_spot_check_trans`. `bz2.BZ2File` exposes `.name` on Python 3.13 but not on 3.12, which is what CI actually runs (and what local testing didn't catch, since it ran on 3.13). Fixed by passing the filename explicitly from the caller's already-available `Path.name` instead of reading it off the file handle

### Verified
- Full fetch → `--init` → build → reference-check pipeline for AloHa (both isotopologues) run clean inside a Python 3.12 environment with the exact pinned dependencies from `requirements.txt` (`mendeleev==0.16.2`, `rdkit==2024.3.5`) — reproducing and confirming the fix required matching CI's actual interpreter version, since the local dev environment (Python 3.13, unpinned newer dependency versions) never hit this bug at all

## [0.9.0] — 2026-07-21 — CO2 `Dozen` fixture + two real bugs it exposed

### Added
- **New fixture: CO2 `Dozen`, isotopologue `12C-16O2`** — fetches the full `.states`/`.pf` plus 2 of its 20 wavenumber-range `.trans` files. First fixture to exercise the repeated-element manual SMILES/InChI entry path (CO2 has two oxygens) and multi-`.trans`-file handling. Wired into CI via `.github/scripts/check_dozen_ref.py`
- **`fetch_exomol_sample.py` retries transient connection failures** — `_fetch()` retries a couple of times before giving up. Found via a real Windows CI failure on the v0.8.0 run: two separate downloads hit a WinError 10060 connection timeout against exomol.com, while the identical URLs succeeded fine on macOS/Ubuntu in the same run and on every other fetch in the same job — a transient network blip, not a platform bug, but one a single stalled connection shouldn't be able to fail the whole job over

### Fixed
- **`_open_maybe_bz2` decompressed entire `.bz2` files into a temp directory before use**, even when the caller only needed to peek at a handful of lines — harmless for AloHa/COmet's small files, but `Dozen`'s `.trans.bz2` files decompress to ~1.3GB each, which blew past this machine's 3.1GB tmpfs `/tmp` and crashed `--init`. Now streams decompression via `bz2.open` instead, so memory/disk usage no longer scales with file size; `tempfile.TemporaryDirectory()` removed from all 6 call sites across `validator.py`/`extractor.py`
- **`.def` isotope list wrote one "Isotope number/Element symbol" line per atom instead of per unique element** — CO2 (3 atoms, 2 unique elements: C, O, O) exposed this; AloHa/COmet never caught it since both are distinct-element diatomics where the two counts are the same. Now dedupes to match the real ExoMol `.def` convention and this tool's own (already-correct) `.def.json` output
- **`.inp` template quantum-labels comment block silently merged two lines into one** — a missing comma in `inp_handler.py`'s `_INP_COMMENTS["quantum_labels"]` list caused Python's implicit string-literal concatenation to join an example line into the next one

### Changed
- **`.inp` template comment wording polish** — clarified `cas_registry_number`/`irreps`/`cooling_function_available`/`specific_heat_available`/`continuum`/quantum-labels comment text, added a SMILES lookup link and a quantum-cases lookup link

### Verified
- `Dozen`/`12C-16O2` build matches the real published reference exactly outside three documented, non-fixable gaps: CAS registry number (live-queried CAS Common Chemistry registers CO2's neutral molecule, its anion, and its dimer all under the same InChIKey *and* the same reported InChI — confirmed by pulling each candidate's detail record — so the existing ambiguous-match guard correctly declines to guess); the InChI isotope-layer suffix (this tool adds one, matching AlH's tested behavior and its real published `.def`; Dozen's real published `.def` omits it — a difference in upstream dataset curation, not this tool); and transition counts / `max_energy` (expected, since only 2 of 20 `.trans` files were fetched and `max_energy` there is an author-curated "complete-up-to" threshold, not the literal maximum energy in the `.states` file)
- AloHa (both isotopologues) and COmet rebuilt clean after both bug fixes — no regression; the atom-dedup fix is a no-op for both since they're distinct-element diatomics
- Full fetch → stage → `--init` → build → reference-check pipeline run end-to-end locally for `Dozen`, matching what CI now runs

## [0.8.0] — 2026-07-21 — AloHa fetch-on-demand + multi-isotopologue fixture

### Changed
- **`samples/AloHa` fixture migrated to fetch-on-demand** — its committed `.states`/`.trans` (plain and `.bz2`) and `ref/*.def*` files are no longer tracked in git; `.github/workflows/ci.yml` now fetches them via `fetch_exomol_sample.py` as a setup step before `--init`/build. `.gitignore` extended to cover `*.states.bz2`/`*.trans.bz2`, and the now-unused `ref/*.def` allowlist exception removed
- **`cooling_function_available`, `specific_heat_available`, `continuum` moved from `[dataset]` to `[isotopologue.*]`** in the `.inp` format — these can genuinely differ per isotopologue (AlH's real published `continuum = true` vs AlD's `continuum = false`, within the same AloHa dataset), which the old dataset-level-only field couldn't express. **Breaking**: existing `.inp` files need these three keys moved from `[dataset]` into each `[isotopologue.*]` section. `samples/AloHa/AloHa.inp` and `samples/COmet/COmet.inp` updated accordingly. README's `.inp` field reference tables updated to match

### Added
- **New fixture: AloHa isotopologue `27Al-2H`** (AlD) — added alongside `27Al-1H` in a renamed `samples/AloHa/work_dir/` (was `samples/AloHa/27Al-1H/`), exercising the multi-isotopologue-per-dataset build path for the first time in CI. CI now fetches and diffs both isotopologues against their fetched references

### Fixed
- **`.def.json` always wrote `cas_registry_number: null`** for isotopologues without a CAS number, where ExoMol's real published format omits the key entirely (confirmed against AlD's fetched reference); by contrast, ExoMol does write `uncertainty_description` as `null` when absent, so omission isn't a blanket rule for every optional field. New `merger.strip_null_optional()` omits just `cas_registry_number` when absent, applied before writing `.def.json`

### Verified
- All three isotopologues (AlH and AlD from AloHa; CO+ from COmet) rebuild matching their real reference data (fetched for AloHa, local untracked file for COmet) after both fixes, via `.github/scripts/check_aloha_ref.py` for AloHa
- AlD's real published data confirmed live via `fetch_exomol_sample.py`: `continuum = false` (vs AlH's `true`), 14 states-file columns (vs AlH's 16 — no `Auxiliary:SourceType`/`Auxiliary:Ecal`), `quantum_case_label = dcs` (vs AlH's `dos`)

## [0.7.0] — 2026-07-21 — ExoMol sample downloader

### Added
- **`fetch_exomol_sample.py`** — standalone script, separate from `create_def.py`, that downloads a dataset/isotopologue's `.states.bz2`/`.trans.bz2`/`.pf` files plus its published reference `.def`/`.def.json` from ExoMol's public API (`https://www.exomol.com/db/...`) into a local directory. Molecule name is derived from `iso_slug` via the existing `extractor.slug_to_hill_formula_and_charge` rather than a new lookup. Files already present (non-empty) in the destination are left alone, so re-running only fetches what's missing
  - `--trans-files N` selects how many wavenumber-range `.trans.bz2` files to fetch for split datasets (ascending from 0 cm⁻¹); required whenever a dataset has more than one (`.def.json`'s `dataset.transitions.number_of_transition_files` > 1) — omitting it errors out naming the total file count rather than guessing
  - A failed download (404, network error) is logged with the failing URL and skipped rather than stopping the whole run; the script exits non-zero if any file was never obtained
  - `.def`/`.def.json` are always fetched into a `dest_dir/ref/` subdirectory, matching the existing `samples/*/ref/` convention
  - **README** — new section documenting the script's CLI and behavior

### Verified
- Live-fetched `27Al-1H`/`AloHa` end-to-end: `.states.bz2`/`.trans.bz2`/`.pf` are byte-identical to the committed `samples/AloHa/27Al-1H` fixture; `ref/.def`/`.def.json` are structurally identical (`json.load` equality) — the only raw-byte differences are CRLF line endings and JSON indentation currently served by exomol.com, not a content mismatch
- Live-fetched `12C-16O2`/`Dozen` (a 20-file split-`.trans` dataset): omitting `--trans-files` errors out naming the file count rather than guessing; `--trans-files 2` fetches exactly the two lowest-range files (`__00000-01000`, `__01000-02000`)
- A bad iso_slug/dataset (`99Zz-1H`/`NotReal`) 404s on every file, each logged individually, script exits 1
- Re-running against an already-populated directory skips every file with no network calls
- `test_fetch_exomol_sample.py` (mocked, no network): trans-filename selection for single-file vs. split datasets, missing-`--trans-files` error, a failing fetch not blocking the rest, and cache-skip behavior

## [0.6.2] — 2026-07-16 — Python 3.12 install fix

### Fixed
- **`requirements.txt`** — `pandas` was pinned to an exact `2.0.3` (chosen in 0.5.4 for the Python 3.8 floor), which has no Python 3.12 wheel; installing on 3.12 fell back to a from-source build and failed on all three CI runners. Loosened to `pandas>=2.0.3,<3`, so pip resolves a version with a matching wheel for whichever interpreter it's installed on

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
