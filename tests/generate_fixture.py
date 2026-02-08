"""Generate versioned JSONL fixture files for regression testing.

Checks out dogcat code at each git tag, runs demo issue generation using
that version's code, and saves the resulting issues.jsonl as a frozen
fixture in tests/fixtures/.

Tags whose schema and demo output are identical to an earlier tag are
skipped by default. Pass a specific tag to force generation.

Usage:
    python tests/generate_fixture.py              # Schema-changing tags only
    python tests/generate_fixture.py v0.3.0       # Specific tag (always runs)
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"

# Tags whose schema (models.py, demo.py, storage.py serialization) is
# identical to an earlier tag. Generating fixtures for these produces
# the same JSONL structure, so they are skipped when running without
# arguments.  Pass the tag explicitly to force generation.
#
# v0.1.1-v0.1.9 — identical schema + demo to v0.1.0
# v0.5.1-v0.5.2 — identical schema + demo to v0.5.0
SKIP_TAGS: set[str] = {
    "v0.1.1",
    "v0.1.2",
    "v0.1.3",
    "v0.1.4",
    "v0.1.5",
    "v0.1.6",
    "v0.1.7",
    "v0.1.8",
    "v0.1.9",
    "v0.5.1",
    "v0.5.2",
}


def _get_all_tags() -> list[str]:
    """Return all version tags sorted by version."""
    result = subprocess.run(
        ["git", "tag", "--list", "v*", "--sort=v:refname"],
        capture_output=True,
        text=True,
        check=True,
        cwd=REPO_ROOT,
    )
    return [t.strip() for t in result.stdout.strip().splitlines() if t.strip()]


def _generate_for_tag(tag: str, clone_dir: Path) -> Path:
    """Generate a fixture file for a specific git tag.

    Clones the repo (if not already cloned), checks out the tag,
    installs the package, and runs demo generation.

    Returns the path to the generated fixture file.
    """
    fixture_name = f"{tag}_issues.jsonl"
    fixture_path = FIXTURES_DIR / fixture_name

    if fixture_path.exists():
        print(f"  Skipping {tag} — {fixture_name} already exists")
        return fixture_path

    # Clone if needed
    if not (clone_dir / ".git").exists():
        print(f"  Cloning repo to {clone_dir}")
        subprocess.run(
            ["git", "clone", "--quiet", str(REPO_ROOT), str(clone_dir)],
            check=True,
        )

    # Checkout the tag
    subprocess.run(
        ["git", "checkout", "--quiet", tag],
        cwd=clone_dir,
        check=True,
    )

    # Create a venv and install the package at this tag
    venv_dir = clone_dir / ".venv"
    if venv_dir.exists():
        shutil.rmtree(venv_dir)

    subprocess.run(
        ["uv", "venv", str(venv_dir), "--quiet"],
        cwd=clone_dir,
        check=True,
    )

    subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "--quiet",
            "-e",
            str(clone_dir),
            "--python",
            str(venv_dir / "bin" / "python"),
        ],
        cwd=clone_dir,
        check=True,
    )

    python = str(venv_dir / "bin" / "python")

    # Generate demo issues in a temp .dogcats dir using the tagged code
    with tempfile.TemporaryDirectory() as tmpdir:
        dogcats_dir = Path(tmpdir) / ".dogcats"
        dogcats_dir.mkdir()
        issues_path = dogcats_dir / "issues.jsonl"

        script = f"""\
import sys
sys.path.insert(0, "{clone_dir / "src"}")
from dogcat.storage import JSONLStorage
from dogcat.demo import generate_demo_issues

storage = JSONLStorage("{issues_path}", create_dir=True)
ids = generate_demo_issues(storage, "{dogcats_dir}")
print(f"Generated {{len(ids)}} issues")
"""
        result = subprocess.run(
            [python, "-c", script],
            capture_output=True,
            text=True,
            cwd=clone_dir,
        )

        if result.returncode != 0:
            print(f"  ERROR generating fixture for {tag}:")
            print(f"    stdout: {result.stdout.strip()}")
            print(f"    stderr: {result.stderr.strip()}")
            msg = f"Failed to generate fixture for {tag}"
            raise RuntimeError(msg)

        print(f"  {tag}: {result.stdout.strip()}")

        # Copy the generated file to fixtures
        FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(issues_path, fixture_path)

    return fixture_path


def main() -> None:
    """Generate fixtures for specified tags or all tags."""
    if len(sys.argv) > 1:
        # Explicit tags — always honour the request
        tags = sys.argv[1:]
    else:
        all_tags = _get_all_tags()
        skipped = [t for t in all_tags if t in SKIP_TAGS]
        tags = [t for t in all_tags if t not in SKIP_TAGS]
        if skipped:
            print(
                f"Skipping {len(skipped)} tag(s) with "
                "redundant schemas: {', '.join(skipped)}",
            )

    if not tags:
        print("No tags found")
        sys.exit(1)

    print(f"Generating fixtures for {len(tags)} tag(s)")
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

    clone_dir = Path("/tmp/dcat-fixture-gen")
    if clone_dir.exists():
        shutil.rmtree(clone_dir)

    try:
        for tag in tags:
            print(f"Processing {tag}...")
            _generate_for_tag(tag, clone_dir)
    finally:
        if clone_dir.exists():
            shutil.rmtree(clone_dir)

    print(f"\nDone. Fixtures in {FIXTURES_DIR}/")


if __name__ == "__main__":
    main()
