import pytest

from mizan.data.snapshot import verify_snapshot, write_snapshot
from tests.test_snapshot import ITEMS


def test_items_file_uses_lf_line_endings_on_every_platform(tmp_path):
    snap = write_snapshot(ITEMS, tmp_path / "v1")
    raw = (snap / "items.jsonl").read_bytes()
    assert b"\r" not in raw
    assert raw.count(b"\n") == len(ITEMS)


def test_verify_accepts_a_fresh_snapshot(tmp_path):
    verify_snapshot(write_snapshot(ITEMS, tmp_path / "v1"))


def test_verify_detects_an_edited_items_file(tmp_path):
    snap = write_snapshot(ITEMS, tmp_path / "v1")
    path = snap / "items.jsonl"
    path.write_bytes(path.read_bytes().replace(b"text AAA-1", b"text CHANGED"))
    with pytest.raises(ValueError, match="does not match manifest"):
        verify_snapshot(snap)


def test_verify_detects_crlf_conversion(tmp_path):
    snap = write_snapshot(ITEMS, tmp_path / "v1")
    path = snap / "items.jsonl"
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    with pytest.raises(ValueError, match="CRLF"):
        verify_snapshot(snap)
