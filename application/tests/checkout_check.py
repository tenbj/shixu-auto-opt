"""Verify Git checkout filters preserve the exact Docker evidence input bytes."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from docker_contract import snapshot


def main():
    repository = Path(subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "--show-toplevel"], encoding="utf-8"
    ).strip()).resolve()
    contract = json.loads((ROOT / "project-contract.json").read_text(encoding="utf-8"))
    inputs = snapshot(ROOT, contract["docker"]["inputs"])
    mismatches = []
    for entry in inputs:
        path = ROOT / entry["path"]
        data = path.read_bytes()
        raw = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        relative = path.relative_to(repository).as_posix()
        filtered = subprocess.check_output(
            ["git", "-C", str(repository), "hash-object", "--path=" + relative, str(path)], encoding="utf-8"
        ).strip()
        if raw != filtered:
            mismatches.append(entry["path"])
    report = {
        "passed": not mismatches,
        "delivery_id": contract["delivery_id"],
        "files_checked": len(inputs),
        "mismatched_paths": mismatches,
        "scope": "Every declared Docker input raw blob compared with Git clean-filter result; frozen source exceptions retain exact bytes",
    }
    output = ROOT / "verification" / "line-ending-report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8", newline="\n")
    print(json.dumps(report))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
