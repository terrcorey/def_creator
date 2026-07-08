import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent


def standard_labels_path() -> Path:
    return _REPO_ROOT / "lib" / "standard_label_structure.json"


def template_path(name: str = "exomol") -> Path:
    return _REPO_ROOT / "def_templates" / f"{name}.json"
