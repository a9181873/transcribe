"""Retention helpers for public transcription jobs.

Only token-named directories directly below the configured jobs root are ever
eligible for deletion. Local and batch outputs elsewhere under output are
intentionally outside this cleaner's scope.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import shutil
import time
from pathlib import Path


DEFAULT_RETENTION_HOURS = 72.0
DEFAULT_INTERVAL_SECONDS = 3600.0
JOB_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{20,64}$")
ACTIVE_MARKER = ".job-active"
FINISHED_MARKER = ".job-finished"

log = logging.getLogger(__name__)


def mark_job_active(job_dir: Path, *, now: float | None = None) -> None:
    """Mark a public job as active and clear any stale finished marker."""
    job_dir = Path(job_dir)
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / FINISHED_MARKER).unlink(missing_ok=True)
    marker = job_dir / ACTIVE_MARKER
    if marker.is_symlink():
        marker.unlink()
    marker.touch(exist_ok=True)
    if now is not None:
        os.utime(marker, (now, now))


def mark_job_finished(job_dir: Path, *, now: float | None = None) -> None:
    """Start the retention window, whether processing succeeded or failed."""
    job_dir = Path(job_dir)
    marker = job_dir / FINISHED_MARKER
    if marker.is_symlink():
        marker.unlink()
    marker.touch(exist_ok=True)
    if now is not None:
        os.utime(marker, (now, now))
    (job_dir / ACTIVE_MARKER).unlink(missing_ok=True)


def _newest_mtime(job_dir: Path) -> float:
    """Return the newest mtime without following symlinks."""
    newest = job_dir.lstat().st_mtime
    for current_root, dirnames, filenames in os.walk(job_dir, followlinks=False):
        current = Path(current_root)
        for name in (*dirnames, *filenames):
            candidate = current / name
            try:
                newest = max(
                    newest,
                    candidate.lstat().st_mtime,
                )
            except FileNotFoundError:
                continue
    return newest


def cleanup_expired_jobs(
    jobs_root: Path,
    *,
    retention_seconds: float = DEFAULT_RETENTION_HOURS * 3600,
    now: float | None = None,
) -> list[Path]:
    """Delete expired public jobs and return the deleted paths.

    Finished jobs expire from their completion marker. Legacy or interrupted
    jobs without one use the newest descendant mtime, so an active writer is
    never removed merely because its parent directory is old.
    """
    root = Path(jobs_root)
    if not root.is_dir():
        return []

    cutoff = (time.time() if now is None else now) - retention_seconds
    deleted: list[Path] = []

    try:
        entries = list(root.iterdir())
    except OSError as exc:
        log.warning("Unable to scan public jobs root %s: %s", root, exc)
        return deleted

    for job_dir in entries:
        if not JOB_TOKEN_RE.fullmatch(job_dir.name) or job_dir.is_symlink():
            continue
        try:
            if not job_dir.is_dir():
                continue

            finished_marker = job_dir / FINISHED_MARKER
            if finished_marker.is_file() and not finished_marker.is_symlink():
                reference_mtime = finished_marker.stat(
                    follow_symlinks=False
                ).st_mtime
            else:
                reference_mtime = _newest_mtime(job_dir)

            if reference_mtime >= cutoff:
                continue

            shutil.rmtree(job_dir)
            deleted.append(job_dir)
            log.info("Deleted expired public job: %s", job_dir.name)
        except FileNotFoundError:
            continue
        except OSError as exc:
            log.warning("Unable to delete public job %s: %s", job_dir, exc)

    return deleted


def run_cleanup_loop(
    jobs_root: Path,
    *,
    retention_seconds: float,
    interval_seconds: float,
    once: bool = False,
) -> None:
    while True:
        deleted = cleanup_expired_jobs(
            jobs_root,
            retention_seconds=retention_seconds,
        )
        log.info("Retention pass complete; deleted %d job(s)", len(deleted))
        if once:
            return
        time.sleep(interval_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="Delete expired public jobs")
    parser.add_argument("--root", type=Path, default=Path("./output/jobs"))
    parser.add_argument(
        "--retention-hours", type=float, default=DEFAULT_RETENTION_HOURS
    )
    parser.add_argument(
        "--interval-seconds", type=float, default=DEFAULT_INTERVAL_SECONDS
    )
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    if args.retention_hours <= 0 or args.interval_seconds <= 0:
        parser.error("retention and interval must be greater than zero")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    run_cleanup_loop(
        args.root,
        retention_seconds=args.retention_hours * 3600,
        interval_seconds=args.interval_seconds,
        once=args.once,
    )


if __name__ == "__main__":
    main()
