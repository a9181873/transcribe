import os

import pytest

import job_retention
from job_retention import (
    ACTIVE_MARKER,
    FINISHED_MARKER,
    cleanup_expired_jobs,
    mark_job_active,
    mark_job_finished,
)


NOW = 2_000_000_000.0
RETENTION_SECONDS = 72 * 3600


def _token(character):
    return character * 24


def _set_mtime(path, value):
    os.utime(path, (value, value))


def _make_job(root, token):
    job = root / token
    job.mkdir(parents=True)
    (job / "result.txt").write_text("result", encoding="utf-8")
    return job


def test_finished_job_is_deleted_only_after_72_hours(tmp_path):
    root = tmp_path / "jobs"
    expired = _make_job(root, _token("A"))
    boundary = _make_job(root, _token("B"))
    recent = _make_job(root, _token("C"))

    mark_job_finished(expired, now=NOW - RETENTION_SECONDS - 1)
    mark_job_finished(boundary, now=NOW - RETENTION_SECONDS)
    mark_job_finished(recent, now=NOW - RETENTION_SECONDS + 1)

    deleted = cleanup_expired_jobs(
        root,
        retention_seconds=RETENTION_SECONDS,
        now=NOW,
    )

    assert deleted == [expired]
    assert not expired.exists()
    assert boundary.exists()
    assert recent.exists()


def test_active_job_is_kept_and_stale_interrupted_job_is_removed(tmp_path):
    root = tmp_path / "jobs"
    active = _make_job(root, _token("D"))
    interrupted = _make_job(root, _token("E"))

    mark_job_active(active, now=NOW - 60)
    mark_job_active(interrupted, now=NOW - RETENTION_SECONDS - 10)
    old = NOW - RETENTION_SECONDS - 10
    _set_mtime(interrupted / "result.txt", old)
    _set_mtime(interrupted, old)

    cleanup_expired_jobs(root, retention_seconds=RETENTION_SECONDS, now=NOW)

    assert active.exists()
    assert not interrupted.exists()


def test_legacy_job_uses_newest_descendant_mtime(tmp_path):
    root = tmp_path / "jobs"
    job = _make_job(root, _token("F"))
    old = NOW - RETENTION_SECONDS - 10
    _set_mtime(job, old)
    _set_mtime(job / "result.txt", NOW - 60)

    cleanup_expired_jobs(root, retention_seconds=RETENTION_SECONDS, now=NOW)

    assert job.exists()


def test_invalid_directory_and_symlink_are_never_deleted(tmp_path):
    root = tmp_path / "jobs"
    invalid = _make_job(root, "not-a-job-token")
    _set_mtime(invalid / "result.txt", NOW - RETENTION_SECONDS - 10)
    _set_mtime(invalid, NOW - RETENTION_SECONDS - 10)

    target = tmp_path / "outside"
    target.mkdir()
    link = root / _token("G")
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("Directory symlinks are unavailable on this host")

    cleanup_expired_jobs(root, retention_seconds=RETENTION_SECONDS, now=NOW)

    assert invalid.exists()
    assert link.is_symlink()
    assert target.exists()


def test_one_delete_error_does_not_stop_other_jobs(tmp_path, monkeypatch):
    root = tmp_path / "jobs"
    blocked = _make_job(root, _token("H"))
    removable = _make_job(root, _token("I"))
    old = NOW - RETENTION_SECONDS - 1
    mark_job_finished(blocked, now=old)
    mark_job_finished(removable, now=old)

    real_rmtree = job_retention.shutil.rmtree

    def selective_rmtree(path):
        if path == blocked:
            raise PermissionError("busy")
        real_rmtree(path)

    monkeypatch.setattr(job_retention.shutil, "rmtree", selective_rmtree)
    deleted = cleanup_expired_jobs(
        root,
        retention_seconds=RETENTION_SECONDS,
        now=NOW,
    )

    assert blocked.exists()
    assert deleted == [removable]
    assert not removable.exists()


def test_markers_transition_and_missing_root_is_a_noop(tmp_path):
    job = tmp_path / "jobs" / _token("J")
    mark_job_active(job, now=NOW - 10)

    assert (job / ACTIVE_MARKER).exists()
    assert not (job / FINISHED_MARKER).exists()

    mark_job_finished(job, now=NOW)

    assert not (job / ACTIVE_MARKER).exists()
    assert (job / FINISHED_MARKER).stat().st_mtime == NOW
    assert cleanup_expired_jobs(tmp_path / "missing", now=NOW) == []
