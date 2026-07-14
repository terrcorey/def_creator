import unicodedata
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent


def standard_labels_path() -> Path:
    return _REPO_ROOT / "lib" / "standard_label_structure.json"


def template_path(name: str = "exomol") -> Path:
    return _REPO_ROOT / "def_templates" / f"{name}.json"


def to_ascii(s) -> str:
    """Normalises Unicode to ASCII, dropping diacritics (e.g. Landé → Lande)."""
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", errors="ignore").decode("ascii")
