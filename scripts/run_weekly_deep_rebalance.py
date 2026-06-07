#!/usr/bin/env python3

import os
from pathlib import Path
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _maybe_reexec_into_repo_venv() -> None:
    active_prefix = Path(sys.prefix).resolve()
    candidates = (
        REPO_ROOT / ".venv" / "bin" / "python",
        REPO_ROOT / ".venv313" / "bin" / "python",
    )

    def _has_mcp(candidate: Path) -> bool:
        try:
            result = subprocess.run(
                [str(candidate), "-c", "import mcp"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except OSError:
            return False
        return result.returncode == 0

    preferred = [candidate for candidate in candidates if candidate.exists() and _has_mcp(candidate)]
    fallback = [candidate for candidate in candidates if candidate.exists() and candidate not in preferred]

    for candidate in (*preferred, *fallback):
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
