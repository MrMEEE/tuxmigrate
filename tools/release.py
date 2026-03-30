#!/usr/bin/env python3
"""
tuxmigrate Release Manager

Bumps the project version in versions.json, then commits, tags, and pushes.
This controls the *tuxmigrate tool itself* — not the packages it produces.

Usage:
    python tools/release.py                    # patch bump  (1.0.0 → 1.0.1)
    python tools/release.py --minor            # minor bump  (1.0.1 → 1.1.0)
    python tools/release.py --major            # major bump  (1.1.0 → 2.0.0)
    python tools/release.py --version 2.0.0    # explicit version
    python tools/release.py --dry-run          # preview — no changes written
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# ── Project layout ─────────────────────────────────────────────────────────────
PROJECT_ROOT  = Path(__file__).resolve().parent.parent
VERSION_FILE  = PROJECT_ROOT / "version.py"

# ──────────────────────────────────────────────────────────────────────────────


class ReleaseError(RuntimeError):
    pass


class ReleaseManager:
    def __init__(self, dry_run: bool = False) -> None:
        self.dry_run = dry_run
        self._changes: list[str] = []

    # ── Logging ────────────────────────────────────────────────────────────────

    def _log(self, msg: str, level: str = "INFO") -> None:
        prefix = "[DRY-RUN] " if self.dry_run else ""
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"{ts}  {prefix}{level}: {msg}")

    def info(self, msg: str)  -> None: self._log(msg, "INFO")
    def ok(self, msg: str)    -> None: self._log(msg, "OK  ")
    def warn(self, msg: str)  -> None: self._log(msg, "WARN")
    def error(self, msg: str) -> None: self._log(msg, "ERROR")

    # ── Shell helpers ──────────────────────────────────────────────────────────

    def _run(
        self,
        cmd: list[str],
        *,
        capture: bool = True,
        check: bool = True,
        read_only: bool = False,
    ) -> subprocess.CompletedProcess:
        self.info(f"$ {' '.join(cmd)}")
        if self.dry_run and not read_only:
            self._log("(skipped in dry-run mode)", "DEBUG")
            return subprocess.CompletedProcess(cmd, 0, "", "")
        try:
            result = subprocess.run(
                cmd,
                cwd=PROJECT_ROOT,
                capture_output=capture,
                text=True,
                check=check,
            )
            if capture and result.stdout.strip():
                self._log(result.stdout.strip(), "OUT ")
            return result
        except subprocess.CalledProcessError as exc:
            self.error(f"Command failed (exit {exc.returncode})")
            if exc.stderr:
                self.error(exc.stderr.strip())
            raise

    # ── Version helpers ────────────────────────────────────────────────────────

    @staticmethod
    def parse_version(s: str) -> tuple[int, int, int]:
        m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", s.strip())
        if not m:
            raise ReleaseError(f"Invalid version format: {s!r}  (expected X.Y.Z)")
        return int(m.group(1)), int(m.group(2)), int(m.group(3))

    @staticmethod
    def fmt(t: tuple[int, int, int]) -> str:
        return f"{t[0]}.{t[1]}.{t[2]}"

    def current_version(self) -> str:
        if not VERSION_FILE.exists():
            raise ReleaseError(
                f"{VERSION_FILE.name} not found in project root."
            )
        text = VERSION_FILE.read_text()
        m = re.search(r'^VERSION\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
        if not m:
            raise ReleaseError(f"Could not find VERSION in {VERSION_FILE.name}")
        return m.group(1)

    def bump(self, current: str, mode: str) -> str:
        maj, min_, pat = self.parse_version(current)
        if mode == "major":
            return self.fmt((maj + 1, 0, 0))
        if mode == "minor":
            return self.fmt((maj, min_ + 1, 0))
        return self.fmt((maj, min_, pat + 1))  # patch

    # ── Pre-flight checks ──────────────────────────────────────────────────────

    def check_git_state(self) -> None:
        branch = self._run(
            ["git", "branch", "--show-current"], read_only=True
        ).stdout.strip()
        if branch not in ("main", "master"):
            raise ReleaseError(
                f"Releases must be made from 'main' or 'master' (currently: {branch!r})"
            )

        status = self._run(
            ["git", "status", "--porcelain"], read_only=True
        ).stdout.strip()
        if status:
            raise ReleaseError(
                "Working tree has uncommitted changes:\n" + status
            )

        ahead = self._run(
            ["git", "rev-list", "--count", f"origin/{branch}..HEAD"],
            read_only=True,
            check=False,
        ).stdout.strip()
        if ahead and ahead != "0":
            self.warn(
                f"{ahead} commit(s) ahead of origin/{branch} — "
                "they will be pushed along with the release tag."
            )

    def check_tag_doesnt_exist(self, version: str) -> None:
        tag = f"v{version}"
        existing = self._run(
            ["git", "tag", "-l", tag], read_only=True
        ).stdout.strip()
        if existing:
            raise ReleaseError(f"Tag {tag!r} already exists.")

    # ── File updates ───────────────────────────────────────────────────────────

    def update_version_file(self, new_version: str) -> None:
        self.info(f"Updating {VERSION_FILE.name}")
        today = datetime.now().strftime("%Y-%m-%d")
        text = VERSION_FILE.read_text()
        text = re.sub(
            r'^(VERSION\s*=\s*)["\'][^"\']+["\']',
            rf'\g<1>"{new_version}"',
            text,
            flags=re.MULTILINE,
        )
        text = re.sub(
            r'^(BUILD_DATE\s*=\s*)["\'][^"\']+["\']',
            rf'\g<1>"{today}"',
            text,
            flags=re.MULTILINE,
        )
        if not self.dry_run:
            VERSION_FILE.write_text(text)
        self._changes.append(str(VERSION_FILE.relative_to(PROJECT_ROOT)))

    # ── Git operations ─────────────────────────────────────────────────────────

    def git_commit_tag_push(self, new_version: str) -> None:
        tag = f"v{new_version}"
        self._run(["git", "add"] + self._changes)
        self._run(["git", "commit", "-m", f"chore: release {new_version}"])
        self._run(["git", "tag", "-a", tag, "-m", f"Release {new_version}"])
        self._run(["git", "push", "origin", "HEAD"])
        self._run(["git", "push", "origin", tag])
        self.ok(f"Tag {tag} pushed.")

    # ── Entrypoint ─────────────────────────────────────────────────────────────

    def run(self, mode: str, explicit_version: str | None) -> None:
        if self.dry_run:
            self.warn("DRY-RUN mode — no files or git objects will be written.")

        current = self.current_version()
        if explicit_version:
            self.parse_version(explicit_version)   # validates format
            new_version = explicit_version
        else:
            new_version = self.bump(current, mode)

        self.info(f"Current version : {current}")
        self.info(f"New version     : {new_version}")

        self.check_git_state()
        self.check_tag_doesnt_exist(new_version)

        self.update_version_file(new_version)
        self.git_commit_tag_push(new_version)

        self.ok(f"Release {new_version} complete.")


# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="tuxmigrate release manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    bump_group = parser.add_mutually_exclusive_group()
    bump_group.add_argument("--major",   action="store_true", help="Major version bump")
    bump_group.add_argument("--minor",   action="store_true", help="Minor version bump")
    bump_group.add_argument("--patch",   action="store_true", help="Patch version bump (default)")
    bump_group.add_argument("--version", metavar="X.Y.Z",     help="Set an explicit version")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing anything")

    args = parser.parse_args()

    if args.major:
        mode = "major"
    elif args.minor:
        mode = "minor"
    else:
        mode = "patch"

    try:
        ReleaseManager(dry_run=args.dry_run).run(mode, args.version)
    except ReleaseError as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
