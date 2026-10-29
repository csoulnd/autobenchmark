"""Shared skeleton CLI; deliberately performs no infrastructure operations."""
import argparse
import json
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]

def main(stage):
    parser = argparse.ArgumentParser(description=f"{stage}: scaffold only")
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    if not args.run_dir.is_absolute():
        parser.error("--run-dir must be absolute")
    print(json.dumps({"stage": stage, "status": "BLOCKED",
                      "message": "Not implemented; no resources modified",
                      "artifacts": []}))
    return 2
