# libvcs Strips Whitespace From Captured git Output

`libvcs.cmd.git.Git.run()` does not return git's output verbatim. It strips every line and
drops blank lines before handing the string back. For single-token reads (`rev-parse HEAD`,
`remote get-url`) this is harmless, but it silently corrupts any whitespace-significant output —
most importantly `git diff`, where a leading space marks a context line and blank lines are part
of the content. The captured diff is no longer a valid, applicable patch.

This repository is a minimal, self-contained reproduction.

## Reproduce

```bash
uv run pytest
```

The test applies `change.patch` to `file_having_a_diff.py` in this repo (setup), captures
`git diff` through both `subprocess` and `libvcs`, then restores the file (teardown) — the repo
is left exactly as it was.

`test_std_cli_diff_round_trips_the_patch` passes: `subprocess` returns the applied patch
verbatim. `test_libvcs_diff_round_trips_the_patch` **fails**: `libvcs` returns the same diff
with the leading whitespace stripped and the blank line gone. The failing assertion is the bug
report.

With `mise` installed, `mise run test` does the same after fetching the pinned `uv`.

## Observed output

`change.patch` is the faithful diff; `garbled_diff.txt` is what `libvcs` returns for the same
`git diff`. `diff garbled_diff.txt change.patch` (`<` is libvcs, `>` is faithful) shows every
loss:

```text
6c6
< def greet(name):
---
>  def greet(name):
9,10c9,11
< print(message)
< return message
\ No newline at end of file
---
>  
>      print(message)
>      return message
```

Every context line lost its leading space, the blank line vanished, and the trailing newline is
gone. The result is no longer a valid patch — `git apply` rejects it (`corrupt patch at line 6`),
while `change.patch` applies cleanly. Any tool that captures `git diff` through `libvcs` (an AI
commit-message drafter, a patch parser) therefore receives malformed input.

## Root cause

In `src/libvcs/_internal/run.py`, `run()` post-processes captured stdout roughly as:

```python
all_output = console_to_str(b"\n".join(line.strip() for line in proc.stdout.readlines() if line.strip()))
```

`line.strip()` removes leading and trailing whitespace from every line, and the `if line.strip()`
filter drops blank lines entirely. There is no flag to disable this.

This was introduced deliberately in [PR #493 — fix(run) Fix live / streaming / flushing of
output](https://github.com/vcs-python/libvcs/pull/493), which moved `run()` to byte-mode and
trims each line so `git clone` progress bars flush correctly. Output fidelity was traded for
clean progress display. The murky output contract is acknowledged in the open roadmap issue
[#515 — \[Agentic DX\] … contract roadmap](https://github.com/vcs-python/libvcs/issues/515)
("Output and behavior contracts are explicit" is listed under "Done when").

## Workaround

Redirect `stdout` to a file so `libvcs` writes raw bytes and never runs its line-stripping path
(`proc.stdout` is then `None`, so the post-processing is skipped):

```python
import tempfile
from pathlib import Path
from libvcs.cmd.git import Git

def faithful_run(args: list[str], repo: Path) -> str:
    with tempfile.TemporaryFile() as fh:
        Git(path=repo).run(args, stdout=fh)
        fh.seek(0)
        return fh.read().decode()
```

`libvcs` still resolves the binary, sets the cwd, and raises `CommandError` on non-zero exit —
only the capture is byte-faithful.

## Files

- `file_having_a_diff.py` — the committed base file (indented, with a blank line).
- `change.patch` — a real unified diff that edits `file_having_a_diff.py`; its context lines
  carry the leading whitespace and blank line that expose the bug, and it is the expected output
  the tests assert against.
- `garbled_diff.txt` — the incorrect diff `libvcs` returns for `change.patch`, captured verbatim
  for reference (stripped indentation, dropped blank line, no trailing newline).
- `test_diff_whitespace.py` — applies the patch (setup), runs the passing `subprocess` test and
  the failing `libvcs` test, then restores the file (teardown).
- `pyproject.toml`, `uv.lock` — project metadata with pinned `libvcs` and `pytest`.
- `mise.toml`, `mise.lock` — installs the pinned `uv`; provides the `test` task.

## Environment

- `libvcs==0.42.0` (pinned in `pyproject.toml`)
- Python `>=3.10`
- any recent `git`
