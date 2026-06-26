import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent


def def_updater_path() -> Path:
    """
    Resolves the path to the def_updater project.

    Resolution order:
    1. DEF_UPDATER_PATH environment variable (absolute or relative to cwd)
    2. Sibling directory: <repo_root>/../def_updater
    3. EnvironmentError with a helpful message if neither exists
    """
    env = os.environ.get("DEF_UPDATER_PATH")
    if env:
        p = Path(env).expanduser().resolve()
        if p.is_dir():
            return p
        raise EnvironmentError(
            f"DEF_UPDATER_PATH='{env}' does not exist or is not a directory"
        )
    sibling = (_REPO_ROOT / ".." / "def_updater").resolve()
    if sibling.is_dir():
        return sibling
    raise EnvironmentError(
        "Cannot find def_updater. Set the DEF_UPDATER_PATH environment variable "
        "to the absolute path of the def_updater project directory.\n"
        f"Tried sibling path: {sibling}"
    )


def standard_labels_path() -> Path:
    return def_updater_path() / "other_materials" / "lib" / "standard_label_structure.json"


def template_path(name: str = "exomol") -> Path:
    return _REPO_ROOT / "def_templates" / f"{name}.json"
