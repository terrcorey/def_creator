"""
CAS Registry Number lookup via the CAS Common Chemistry API
(https://commonchemistry.cas.org/api), keyed by InChIKey.

Requires a free API key from https://commonchemistry.cas.org, supplied via
the CAS_API_KEY environment variable. Falls back to no lookup (blank/manual
entry) if the key is unset, the request fails, or the match is ambiguous —
same graceful-degradation behavior as SMILES auto-derivation for polyatomics.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path

_SEARCH_URL = "https://commonchemistry.cas.org/api/search"
_ENV_FILE = Path(__file__).parent / ".env"


def _load_dotenv() -> None:
    """ponytail: minimal KEY=VALUE loader for a gitignored .env; skip python-dotenv for one var."""
    if not _ENV_FILE.exists():
        return
    for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def cas_rn_from_inchikey(inchikey: str) -> str | None:
    """
    Looks up the CAS Registry Number for a given InChIKey.
    Returns None if CAS_API_KEY is unset, the request fails, or the match
    isn't exactly one result.
    """
    _load_dotenv()
    api_key = os.environ.get("CAS_API_KEY")
    if not api_key:
        logging.info("cas: CAS_API_KEY not set — skipping CAS RN lookup")
        return None

    req = urllib.request.Request(
        f"{_SEARCH_URL}?q=InChIKey={inchikey}",
        headers={"X-API-KEY": api_key},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.load(response)
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        logging.warning(f"cas: lookup failed for '{inchikey}': {e}")
        return None

    results = data.get("results") or []
    if len(results) != 1:
        logging.info(f"cas: {len(results)} match(es) for '{inchikey}' — skipping")
        return None

    return results[0].get("rn") or None


def _demo():
    """ponytail: assert-based self-check, no network — mocks urlopen."""
    from unittest import mock

    os.environ.pop("CAS_API_KEY", None)
    with mock.patch(f"{__name__}._load_dotenv", lambda: None):
        assert cas_rn_from_inchikey("XLYOFNOQVPJJNP-UHFFFAOYSA-N") is None

    os.environ["CAS_API_KEY"] = "test-key"
    try:
        fake_response = mock.MagicMock()
        fake_response.__enter__.return_value = fake_response

        fake_response.read.return_value = json.dumps(
            {"results": [{"rn": "7732-18-5", "name": "water"}]}
        ).encode()
        with mock.patch("urllib.request.urlopen", return_value=fake_response):
            assert cas_rn_from_inchikey("XLYOFNOQVPJJNP-UHFFFAOYSA-N") == "7732-18-5"

        fake_response.read.return_value = json.dumps({"results": []}).encode()
        with mock.patch("urllib.request.urlopen", return_value=fake_response):
            assert cas_rn_from_inchikey("XLYOFNOQVPJJNP-UHFFFAOYSA-N") is None

        fake_response.read.return_value = json.dumps(
            {"results": [{"rn": "1"}, {"rn": "2"}]}
        ).encode()
        with mock.patch("urllib.request.urlopen", return_value=fake_response):
            assert cas_rn_from_inchikey("XLYOFNOQVPJJNP-UHFFFAOYSA-N") is None
    finally:
        del os.environ["CAS_API_KEY"]

    print("cas: self-check passed")


if __name__ == "__main__":
    _demo()
