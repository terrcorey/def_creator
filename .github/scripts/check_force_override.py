"""CI smoke test: corrupt a copy of AloHa.inp's 27Al-1H section and verify --force's
override behavior — blocks without it, builds through with it, never renders "None".

# ponytail: reuses 27Al-1H's already-fetched raw data files in a scratch work_dir instead
# of re-fetching, since the main AloHa job step already consumes its own work_dir's temp
# cache by the time this step runs.
"""
import shutil
import subprocess
import sys
from pathlib import Path

work_dir = Path(sys.argv[1])
ds_name = work_dir.parent.name  # "AloHa"
iso_slug = "27Al-1H"

scratch = work_dir.parent / "work_dir_force_test"
scratch.mkdir(exist_ok=True)
for f in work_dir.glob(f"{iso_slug}__{ds_name}*"):
    shutil.copy(f, scratch / f.name)
shutil.copy(work_dir.parent / f"{ds_name}.inp", scratch / f"{ds_name}.inp")


def run(*args):
    return subprocess.run(
        [sys.executable, "create_def.py", *args, str(scratch)],
        capture_output=True, text=True,
    )


init = run("--init")
assert init.returncode == 0, f"--init failed:\n{init.stdout}{init.stderr}"

inp_path = scratch / f"{ds_name}.inp"
head, sep, tail = inp_path.read_text(encoding="utf-8").partition(f"[isotopologue.27Al-2H]")
head = (
    head.replace("max_temperature            = 5000", "max_temperature            = not-a-number")
    .replace("point_group                 = C", "point_group                 = ")
    .replace("irreps                      = Sigma+:12, Sigma-:12", "irreps                      = Sigma+:99, Sigma-:99")
    .replace("quantum_case_label          = dos", "quantum_case_label          = not-a-real-case")
)
inp_path.write_text(head + sep + tail, encoding="utf-8")

blocked = run()
assert blocked.returncode == 1, f"expected build to block without --force, got {blocked.returncode}:\n{blocked.stdout}"
assert f"error(s) in {ds_name}.inp" in blocked.stdout, blocked.stdout

forced = run("--force")
assert forced.returncode == 0, f"expected --force build to succeed, got {forced.returncode}:\n{forced.stdout}{forced.stderr}"

def_text = (scratch / f"{iso_slug}__{ds_name}.def").read_text()
assert "None" not in def_text, "blank/raw fields must never render the literal 'None'"
assert "not-a-number" in def_text, "raw max_temperature should be written through"
assert "not-a-real-case" in def_text, "raw quantum_case_label should be written through"

print("check_force_override: self-check passed")
