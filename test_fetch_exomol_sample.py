"""ponytail: assert-based self-check for fetch_exomol_sample.py's branchy logic, no network -- mocks urlopen."""
from __future__ import annotations

from pathlib import Path
from unittest import mock

from fetch_exomol_sample import _trans_filenames, fetch_sample

_DOZEN_DEF_JSON = {"dataset": {"transitions": {"number_of_transition_files": 20, "max_wavenumber": 20000.0}}}


def _mock_urlopen(payload: bytes):
    resp = mock.MagicMock()
    resp.__enter__.return_value = resp
    resp.read.return_value = payload
    return resp


def _demo():
    # single-file dataset (no def.json needed, or def.json says 1 file)
    assert _trans_filenames("27Al-1H__AloHa", None, None) == ["27Al-1H__AloHa.trans.bz2"]
    assert _trans_filenames("27Al-1H__AloHa", {"dataset": {"transitions": {"number_of_transition_files": 1}}}, None) == [
        "27Al-1H__AloHa.trans.bz2"
    ]

    # split dataset: first N range files, zero-padded, boundaries computed from max_wavenumber
    assert _trans_filenames("12C-16O2__Dozen", _DOZEN_DEF_JSON, 2) == [
        "12C-16O2__Dozen__00000-01000.trans.bz2",
        "12C-16O2__Dozen__01000-02000.trans.bz2",
    ]
    assert _trans_filenames("12C-16O2__Dozen", _DOZEN_DEF_JSON, 20)[-1] == "12C-16O2__Dozen__19000-20000.trans.bz2"

    # split dataset without --trans-files: error, not a silent full download
    try:
        _trans_filenames("12C-16O2__Dozen", _DOZEN_DEF_JSON, None)
        assert False, "expected ValueError"
    except ValueError:
        pass

    # a failing URL is logged and skipped, not fatal -- the rest still get fetched
    with mock.patch("urllib.request.urlopen") as m:
        def side_effect(url, timeout):
            import urllib.error
            if "states" in url:
                raise urllib.error.URLError("simulated failure")
            return _mock_urlopen(b'{"transitions": {"number_of_transition_files": 1}}' if "def.json" in url else b"data")

        m.side_effect = side_effect
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            ok = fetch_sample("27Al-1H", "AloHa", Path(tmp))
            assert ok is False, "one failed file should make the overall result False"
            assert (Path(tmp) / "ref" / "27Al-1H__AloHa.def").exists(), "other files should still be fetched"
            assert (Path(tmp) / "27Al-1H__AloHa.pf").exists()
            assert not (Path(tmp) / "27Al-1H__AloHa.states.bz2").exists()

    # already-cached (non-empty) files are skipped, not re-fetched
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "27Al-1H__AloHa.pf"
        dest.write_bytes(b"cached")
        with mock.patch("urllib.request.urlopen") as m:
            from fetch_exomol_sample import _fetch
            assert _fetch("http://example.invalid", dest) is True
            m.assert_not_called()

    print("test_fetch_exomol_sample: self-check passed")


if __name__ == "__main__":
    _demo()
