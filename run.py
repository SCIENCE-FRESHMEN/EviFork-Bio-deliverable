"""EviFork-Bio one-click entry.

Usage (from the repository root):
    py -3 run.py test                     Run the full test suite (19 checks)
    py -3 run.py demo --output my_runs/demo
                                          Synthetic known-truth control (not biology)
    py -3 run.py report                   Regenerate research_results/final summary

All other commands are forwarded to `python -m evifork_bio`:
    py -3 run.py prepare <network_dir> --output <file.json>
    py -3 run.py run <dataset.json> --output <dir> [--seed N] [--budget B] [--original-network <dir>]
    py -3 run.py recommend --state <hypotheses.json> --candidates <candidates.json> --output <file.json>
    py -3 run.py observe --state <hypotheses.json> --observation <observation.json> --output <file.json>

Examples:
    py -3 run.py demo --output my_runs/synthetic
    py -3 run.py prepare Outcome/Arabidopsis/Shoot_Branching_network --output my_runs/shoot.json
    py -3 run.py run my_runs/shoot.json --output my_runs/shoot_seed17 --seed 17 --budget 3 --original-network Outcome/Arabidopsis/Shoot_Branching_network

Output paths must not already exist. Python 3.10+, no third-party dependencies.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    py = sys.executable
    if cmd == "test":
        return subprocess.call([py, "-B", "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=ROOT)
    if cmd == "report":
        return subprocess.call([py, "-X", "utf8", "-B", str(ROOT / "research" / "report_results.py"),
                                str(ROOT / "research_results" / "final")], cwd=ROOT)
    if cmd == "demo":
        args = [py, "-B", "-m", "evifork_bio", "demo"] + rest
    elif cmd in ("prepare", "run", "recommend", "observe"):
        args = [py, "-B", "-m", "evifork_bio", cmd] + rest
    else:
        print(f"Unknown command: {cmd}\nRun `py -3 run.py help` for usage.")
        return 2
    return subprocess.call(args, cwd=ROOT)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
