"""Score a seeded scratch clone: rerun the scan and compare it with the seed list.

`score.py TARGET [--seeds PATH]` scans the clone TARGET that `seed.py` seeded
and counts how the scan treated the frozen list of items: a stale item the scan
reports is detected (a report under another class than the expected one is
counted apart as wrong class), a control the scan reports is a false positive.
It prints `pass` or `fail` on the first line, then the counts, and exits 0 on
pass and 1 on fail. The probe passes when every stale item is detected and no
control is reported.
"""

import argparse
import json
import sys
from pathlib import Path

PROBE_DIR = Path(__file__).resolve().parent
if str(PROBE_DIR) not in sys.path:
    sys.path.insert(0, str(PROBE_DIR))

import seed  # noqa: E402

NOT_REPORTED = ("unchanged", "changed-elsewhere")


def _record_key(record):
    return (record["file"], record["line"], record.get("ref_path"))


def _item_key(item):
    return (item["file"], item["line"], item.get("ref_path") if item["kind"] == "ref" else None)


def score(seed_list, records):
    """Count detections and false positives of scan `records` against `seed_list`."""
    reported = {}
    for record in records:
        if record.get("class") in NOT_REPORTED:
            continue
        reported.setdefault(_record_key(record), set()).add(record.get("class"))

    stale = [item for item in seed_list["items"] if item["stale"]]
    controls = [item for item in seed_list["items"] if not item["stale"]]
    detected = [item for item in stale if _item_key(item) in reported]
    wrong_class = [item for item in detected
                   if item["expected_class"] not in reported[_item_key(item)]]
    detected_ids = {item["id"] for item in detected}
    false_positives = [item for item in controls if _item_key(item) in reported]
    return {
        "seeded": len(stale),
        "detected": len(detected),
        "wrong_class": len(wrong_class),
        "missed": len(stale) - len(detected),
        "controls": len(controls),
        "false_positives": len(false_positives),
        "passed": len(detected) == len(stale) and not false_positives,
        "missed_ids": [item["id"] for item in stale if item["id"] not in detected_ids],
        "wrong_class_ids": [
            f"{item['id']} expected {item['expected_class']} got "
            + "/".join(sorted(str(c) for c in reported[_item_key(item)]))
            for item in wrong_class
        ],
        "false_positive_ids": [item["id"] for item in false_positives],
    }


def main(argv=None, *, scan=None):
    parser = argparse.ArgumentParser(
        prog="score.py", description="Score a seeded scratch clone.")
    parser.add_argument("target", help="the clone that seed.py seeded")
    parser.add_argument("--seeds", help="frozen seed list (default: TARGET.seeds.json)")
    args = parser.parse_args(argv)
    seeds_path = Path(args.seeds) if args.seeds else seed.default_list_path(args.target)
    try:
        seed_list = json.loads(seeds_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        print(f"cannot read seed list {seeds_path}: {error}", file=sys.stderr)
        return 2

    records = (scan or seed.run_scan)(args.target)
    result = score(seed_list, records)
    print("pass" if result["passed"] else "fail")
    print(f"seeded {result['seeded']} detected {result['detected']} "
          f"wrong_class {result['wrong_class']} missed {result['missed']}")
    print(f"controls {result['controls']} false_positives {result['false_positives']}")
    for label, key in (("missed", "missed_ids"), ("wrong class", "wrong_class_ids"),
                       ("false positive", "false_positive_ids")):
        for entry in result[key]:
            print(f"{label}: {entry}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
