"""Grade every attempt of an evaluation folder and print one line per attempt.

    python showreel/tools/scoreboard.py /path/to/runs

Expects <runs>/<NN_name>/<round>/demo.py; the line budget is read from the
matching showreel/prompts/<NN_name>.md ("Line budget: N").
"""

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROMPTS = HERE.parent / "prompts"


def budget(demo: str) -> int:
    match = re.search(r"Line budget: (\d+)", (PROMPTS / f"{demo}.md").read_text())
    if match is None:
        raise ValueError(f"no line budget in the prompt of {demo}")
    return int(match.group(1))


def main() -> int:
    runs = Path(sys.argv[1])
    print(f"{'demo':28} {'round':5} {'result':6} {'lines':>9} {'filters':>7} {'controls':>8} {'ms':>6}  notes")
    for script in sorted(runs.glob("[0-9][0-9]_*/*/demo.py")):
        demo, round_name = script.parts[-3], script.parts[-2]
        out = script.parent / "grade"
        subprocess.run(
            [sys.executable, str(HERE / "grade.py"), str(script), "--out", str(out), "--max-lines", str(budget(demo))],
            capture_output=True,
            check=False,
        )
        report = json.loads((out / "report.json").read_text())
        static, dynamic = report["static"], report["dynamic"]
        notes = static["problems"] + dynamic["problems"] + dynamic.get("warnings", []) + static["notes"]
        print(
            f"{demo:28} {round_name:5} {'PASS' if report['passed'] else 'FAIL':6} "
            f"{static['code_lines']:>4}/{budget(demo):<4} {len(dynamic.get('filters', [])):>7} "
            f"{len(dynamic.get('controls', [])):>8} {1000 * dynamic.get('seconds_default', 0):>6.0f}  "
            + "; ".join(notes)
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
