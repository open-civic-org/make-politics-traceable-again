from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from collectors.base.archive import ArchiveError, archive_raw, build_raw_from_bytes, verify_artifact
from collectors.base.git import get_git_commit_sha, get_git_dirty


def test_get_git_commit_sha_override() -> None:
    assert get_git_commit_sha(override="abc123") == "abc123"
    assert get_git_commit_sha(override="") == "UNKNOWN"


def test_get_git_commit_sha_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MPTA_GIT_COMMIT_SHA", "deadbeef")
    assert get_git_commit_sha() == "deadbeef"


def test_get_git_dirty_override() -> None:
    assert get_git_dirty(override=True) is True
    assert get_git_dirty(override=False) is False


def test_archive_and_verify(tmp_path: Path) -> None:
    raw = build_raw_from_bytes(
        source_name="eci",
        source_url="fixture://test",
        payload=b'{"ok": true}',
        collector_version="0.1.0",
        git_commit_sha="testsha",
        retrieved_at=datetime(2024, 6, 1, tzinfo=UTC),
    )
    archived = archive_raw(
        raw, raw_root=tmp_path, category="election_results", year=2024, payload_filename="payload.json"
    )
    assert archived.payload_path.is_file()
    assert archived.metadata_path.is_file()
    result = verify_artifact(archived.archive_dir)
    assert result["ok"] is True
    assert result["sha256"] == raw.sha256


def test_archive_dedup_same_content(tmp_path: Path) -> None:
    payload = b'{"election": 1}'
    raw1 = build_raw_from_bytes(
        source_name="eci",
        source_url="fixture://a",
        payload=payload,
        collector_version="0.1.0",
        git_commit_sha="sha1",
        retrieved_at=datetime(2024, 6, 1, tzinfo=UTC),
    )
    first = archive_raw(raw1, raw_root=tmp_path, category="election_results", year=2024)
    # Second archive with same bytes — should not overwrite first payload
    raw2 = build_raw_from_bytes(
        source_name="eci",
        source_url="fixture://b",
        payload=payload,
        collector_version="0.1.0",
        git_commit_sha="sha1",
        retrieved_at=datetime(2024, 6, 2, tzinfo=UTC),
    )
    second = archive_raw(raw2, raw_root=tmp_path, category="election_results", year=2024)
    assert first.sha256 == second.sha256
    # First directory still valid
    verify_artifact(first.archive_dir)
    verify_artifact(second.archive_dir)
    assert first.payload_path.read_bytes() == payload


def test_verify_missing_payload(tmp_path: Path) -> None:
    d = tmp_path / "art"
    d.mkdir()
    (d / "metadata.json").write_text(
        json.dumps({"sha256": "a" * 64, "payload_file": "payload.json"}), encoding="utf-8"
    )
    with pytest.raises(ArchiveError, match="missing payload"):
        verify_artifact(d)


def test_verify_tampered_payload(tmp_path: Path) -> None:
    raw = build_raw_from_bytes(
        source_name="eci",
        source_url="fixture://t",
        payload=b"original",
        collector_version="0.1.0",
        git_commit_sha="x",
    )
    archived = archive_raw(raw, raw_root=tmp_path, category="election_results", year=2024)
    archived.payload_path.write_bytes(b"tampered")
    with pytest.raises(ArchiveError, match="sha256 mismatch"):
        verify_artifact(archived.archive_dir)


def test_verify_invalid_metadata(tmp_path: Path) -> None:
    d = tmp_path / "bad"
    d.mkdir()
    (d / "metadata.json").write_text("{not-json", encoding="utf-8")
    with pytest.raises(ArchiveError, match="invalid metadata"):
        verify_artifact(d)
