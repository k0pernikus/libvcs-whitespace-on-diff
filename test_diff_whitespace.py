import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from libvcs.cmd.git import Git


REPO_ROOT = Path(__file__).resolve().parent
TARGET = "file_having_a_diff.py"
PATCH = REPO_ROOT / "change.patch"
EXPECTED_DIFF = PATCH.read_text()


@pytest.fixture
def applied_patch() -> Iterator[None]:
    git = Git(path=REPO_ROOT)
    git.run(["apply", str(PATCH)])
    try:
        yield
    finally:
        git.run(["restore", "--", TARGET])


def std_cli_diff() -> str:
    completed = subprocess.run(
        ["git", "diff", "--no-color", "--", TARGET],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout


def libvcs_diff() -> str:
    return Git(path=REPO_ROOT).run(["diff", "--no-color", "--", TARGET])


@pytest.mark.usefixtures("applied_patch")
def test_std_cli_diff_round_trips_the_patch() -> None:
    assert std_cli_diff() == EXPECTED_DIFF


@pytest.mark.usefixtures("applied_patch")
def test_libvcs_diff_round_trips_the_patch() -> None:
    assert libvcs_diff() == EXPECTED_DIFF
