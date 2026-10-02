"""Exit-code journal for detached background jobs.

`jobs.launch()` runs the CLI through this module instead of invoking it
directly, because the parent process persists only the child's PID: by the
time `poll()` notices the job has ended, the original Popen handle is long
gone and the exit code cannot be retrieved portably. The runner closes that
gap by journaling the CLI's exit code to a sidecar file that `poll()` reads.

Usage:
    python -m devagent.background.runner <exit-file> <cli args...>
"""

from __future__ import annotations

import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    exit_file = Path(args.pop(0))
    code = 0
    try:
        from devagent.cli import app

        app(args)
    except SystemExit as exc:  # typer/click signal the result via SystemExit
        code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
    except BaseException:
        code = 1
        raise
    finally:
        try:
            exit_file.write_text(str(code), encoding="utf-8")
        except OSError:
            pass
    return code


if __name__ == "__main__":
    raise SystemExit(main())
