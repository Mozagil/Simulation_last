"""1.22a — ham kartlar: starter deck'e /END'den önce aynen eklenir."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.api.crash import CrashSolveRequest
from app.api.crash_runs import REQUEST_KEYS
from app.solvers.base import SolverError
from app.solvers.openradioss import RAW_CARDS_MARKER, OpenRadiossAdapter
from tests.test_crash_multipart import _two_part_params

_CARD = "\n".join(
    [
        "/GRNOD/NODE/900001",
        "ham_mesnet",
        f"{1:10d}{2:10d}",
        "/BCS/900001",
        "ham_bcs",
        f"   111 111{0:10d}{900001:10d}",
    ]
)


def _deck(tmp_path, raw=None):
    p = _two_part_params(tmp_path)
    if raw is not None:
        p["raw_cards"] = raw
    return OpenRadiossAdapter().build_input(p).path.read_text(encoding="utf-8")


def test_empty_raw_cards_leaves_deck_identical(tmp_path):
    base = _deck(tmp_path / "a")
    assert _deck(tmp_path / "b", "") == base
    assert _deck(tmp_path / "c", "\n  \n") == base
    assert RAW_CARDS_MARKER not in base


def test_raw_cards_inserted_verbatim_before_end(tmp_path):
    s = _deck(tmp_path, _CARD + "\n\n")
    lines = s.split("\n")
    i = lines.index(RAW_CARDS_MARKER)
    assert lines[i + 1 : i + 7] == _CARD.split("\n")  # kolonlar dokunulmadan
    assert lines[i + 7] == "/END"
    assert s.count("/END") == 1


def test_crlf_normalized(tmp_path):
    s = _deck(tmp_path, _CARD.replace("\n", "\r\n"))
    assert "\r" not in s
    assert "/GRNOD/NODE/900001\nham_mesnet\n" in s


@pytest.mark.parametrize("bad", ["/END", "  /end  ", "/BEGIN"])
def test_end_or_begin_rejected(tmp_path, bad):
    with pytest.raises(SolverError, match="satır 2"):
        _deck(tmp_path, f"#yorum\n{bad}")


def test_request_field_and_persisted_key():
    assert CrashSolveRequest(geometry_id=1).raw_cards == ""
    assert CrashSolveRequest(geometry_id=1, raw_cards=_CARD).raw_cards == _CARD
    with pytest.raises(ValidationError):
        CrashSolveRequest(geometry_id=1, raw_cards="x" * 200_001)
    assert "raw_cards" in REQUEST_KEYS
