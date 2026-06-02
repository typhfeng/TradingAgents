#!/usr/bin/env python3

import os
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _maybe_reexec_into_repo_venv() -> None:
    active_prefix = Path(sys.prefix).resolve()
    for candidate in (
        REPO_ROOT / ".venv313" / "bin" / "python",
        REPO_ROOT / ".venv" / "bin" / "python",
    ):
        if not candidate.exists():
            continue
        venv_root = candidate.parent.parent.resolve()
        if active_prefix == venv_root:
            return
        os.execv(
            str(candidate),
            [str(candidate), str(Path(__file__).resolve()), *sys.argv[1:]],
        )


_maybe_reexec_into_repo_venv()

from tradingagents.automation.weekly_deep_rebalance import main


if __name__ == "__main__":
    raise SystemExit(main())
