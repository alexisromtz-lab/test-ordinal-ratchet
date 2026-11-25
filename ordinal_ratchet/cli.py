"""CLI for `test-ordinal-ratchet`.

Output contract:

  RC 0  nothing increased over the declared baseline (which may be zero)
  RC 1  a NEW collision, a counter above the baseline, or declared debt that no
        longer exists (zombie debt: it was resolved, remove it)
  RC 2  invalid usage, no test file at all (absence of subject is not zero),
        nothing at all could be parsed, or a file does not parse under
        --strict-syntax

A file that does not parse is NOT a veto over the rest of the repository. It is
reported as not measured: it cannot hide a collision (it is never counted as
zero) and it cannot free declared debt (it is never reported as a zombie). An
older interpreter then still audits the 99% of a modern suite it can read.

The same rule governs labels. `test_1d_margins` carries a dimension and
`test_08b_case` carries the sub-case b of ordinal 8; the two are
syntactically identical, so which numbers are labels is DECLARED by the
repository (`--label-pattern`) and never guessed. Rows kept out this way are
counted and printable, and `shadow` is exempt: two identical names are two
identical names whatever the pattern claims.

The baseline is a JSON file holding the INHERITED debt. The ratchet turns one
way: the declared count may go down, never up.

By default only the rows that justify the RC are printed; the totals travel in
the header. `--detail` lists every row, `--json` emits all of them.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import sys
from typing import Dict, List, Optional, Sequence, Tuple

from . import scanner

try:
    from importlib.metadata import version as _installed_version

    _VERSION = _installed_version("test-ordinal-ratchet")
except Exception:  # a source checkout that was never installed
    _VERSION = "0+unknown"

DEFAULT_BASELINE = ".ordinal-ratchet.json"
BASELINE_VERSION = 1

Counts = Dict[str, int]
ByFile = Dict[str, Counts]


def _collect(paths: Sequence[str], pattern: str) -> Tuple[List[Tuple[str, pathlib.Path]], List[str]]:
    """Return (key, file) pairs. The key is relative to the argument that found it.

    An absolute key would tie the baseline to the machine where it was frozen,
    and the inherited debt would stop being readable after a clone.

    One file reached twice is one file, and it is deduplicated by its resolved
    path. Two DIFFERENT files that merely share a relative key (`a/tests/
    test_x.py` and `b/tests/test_x.py`, reached through two arguments) are two
    files, and both are measured: the key of each is prefixed with the argument
    it came from, so the baseline stays portable and no file is dropped in
    silence. Keying by the relative path alone made the second file invisible,
    collisions included.
    """
    found: List[Tuple[str, str, pathlib.Path]] = []
    missing: List[str] = []
    for raw in paths:
        entry = pathlib.Path(raw)
        if entry.is_dir():
            for path in sorted(entry.rglob(pattern)):
                found.append((raw, path.relative_to(entry).as_posix(), path))
        elif entry.is_file():
            found.append((raw, entry.name, entry))
        else:
            missing.append(raw)

    unique: Dict[pathlib.Path, Tuple[str, str, pathlib.Path]] = {}
    for row in found:
        unique.setdefault(row[2].resolve(), row)
    rows = list(unique.values())

    counts = collections.Counter(key for _, key, _ in rows)
    disputed = {key for key, times in counts.items() if times > 1}
    files: List[Tuple[str, pathlib.Path]] = []
    for argument, key, path in rows:
        if key in disputed:
            key = pathlib.Path(argument).as_posix().rstrip("/") + "/" + key
        files.append((key, path))
    return sorted(files), missing


def _read(files: Sequence[Tuple[str, pathlib.Path]]) -> Dict[str, str]:
    sources: Dict[str, str] = {}
    for key, path in files:
        try:
            sources[key] = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            sources[key] = ""
    return sources


def _load_baseline(path: pathlib.Path) -> Tuple[ByFile, Optional[str]]:
    if not path.is_file():
        return {}, None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return {}, "unreadable baseline: %s" % error
    debt = data.get("debt")
    if not isinstance(debt, dict):
        return {}, "baseline without a `debt` object"
    clean: ByFile = {}
    for name, counts in debt.items():
        if not isinstance(counts, dict):
            return {}, "baseline entry that is not an object: %s" % name
        clean[str(name)] = {kind: int(counts.get(kind, 0) or 0) for kind in scanner.CLASSES}
    return clean, None


def _measured_by_file(cols: Sequence[scanner.Collision]) -> ByFile:
    out: ByFile = {}
    for c in cols:
        out.setdefault(c.path, {kind: 0 for kind in scanner.CLASSES})[c.kind] += 1
    return out


def _compare(
    measured: ByFile, baseline: ByFile, unreadable: Sequence[str] = ()
) -> Tuple[ByFile, ByFile]:
    """Charged increases and resolved debt. A file that would not parse is neither.

    Its declared debt cannot be called resolved: it was never looked at.
    """
    blind = set(unreadable)
    ups: ByFile = {}
    zombies: ByFile = {}
    for path in sorted(set(measured) | set(baseline)):
        now = measured.get(path, {kind: 0 for kind in scanner.CLASSES})
        declared = baseline.get(path, {kind: 0 for kind in scanner.CLASSES})
        for kind in scanner.RATCHETED:
            if now[kind] > declared[kind]:
                ups.setdefault(path, {})[kind] = now[kind] - declared[kind]
            elif declared[kind] > now[kind] and path not in blind:
                zombies.setdefault(path, {})[kind] = declared[kind] - now[kind]
    return ups, zombies


def _debt_of(measured: ByFile) -> ByFile:
    return {
        path: {kind: value for kind, value in counts.items() if kind in scanner.RATCHETED}
        for path, counts in measured.items()
        if any(counts.get(kind) for kind in scanner.RATCHETED)
    }


def _write_baseline(path: pathlib.Path, pattern: str, measured: ByFile) -> None:
    payload = {"version": BASELINE_VERSION, "pattern": pattern, "debt": _debt_of(measured)}
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _summary(measured: ByFile) -> Counts:
    return {kind: sum(c.get(kind, 0) for c in measured.values()) for kind in scanner.CLASSES}


def _files(n: int) -> str:
    return "1 file" if n == 1 else "%d files" % n


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="test-ordinal-ratchet",
        description="Detect test names that overwrite each other or reuse an ordinal, "
        "with a one-way ratchet over inherited debt.",
    )
    parser.add_argument("--version", action="version", version="%(prog)s " + _VERSION)
    parser.add_argument("paths", nargs="*", default=["."], help="directories or files")
    parser.add_argument("--pattern", default="test_*.py", help="file glob inside directories")
    parser.add_argument(
        "--baseline",
        default=None,
        help="debt baseline (default %s next to the working directory)" % DEFAULT_BASELINE,
    )
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="freeze the current counts as inherited debt",
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument(
        "--detail",
        action="store_true",
        help="also list the rows that are not charged (inherited and shared)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="also fail when two scopes of one file reuse an ordinal",
    )
    parser.add_argument(
        "--strict-syntax",
        action="store_true",
        help="fail with RC 2 when any file does not parse (default: report it and read the rest)",
    )
    parser.add_argument(
        "--label-pattern",
        default=None,
        metavar="REGEX",
        help="tests whose NAME matches are not read as sequence ordinals (a dimension, a "
        "dataset or an issue number: `^test_\\d+[a-zA-Z]`, `^test_[1-5]\\d\\d_`). Never affects shadow",
    )
    args = parser.parse_args(argv)

    label = None
    if args.label_pattern:
        try:
            label = re.compile(args.label_pattern)
        except re.error as error:
            print(
                "RC 2: --label-pattern is not a regex (%s): %s" % (args.label_pattern, error),
                file=sys.stderr,
            )
            return 2

    baseline_path = (
        pathlib.Path(args.baseline) if args.baseline else pathlib.Path(DEFAULT_BASELINE)
    )

    files, missing = _collect(args.paths or ["."], args.pattern)
    if missing:
        print("RC 2: path does not exist: %s" % ", ".join(missing), file=sys.stderr)
        return 2
    if not files:
        print(
            "RC 2: no file matches `%s` under %s (no subject, no zero)"
            % (args.pattern, ", ".join(args.paths or ["."])),
            file=sys.stderr,
        )
        return 2

    cols, unreadable, labels = scanner.scan(_read(files), label)
    parsed = len(files) - len(unreadable)
    if not parsed:
        for u in unreadable:
            print("RC 2: cannot parse %s" % u.report_line(), file=sys.stderr)
        print("RC 2: none of the %d files parses: no subject, no zero" % len(files), file=sys.stderr)
        return 2
    if args.strict_syntax and unreadable:
        for u in unreadable:
            print("RC 2: cannot parse %s" % u.report_line(), file=sys.stderr)
        print(
            "RC 2: --strict-syntax: %d of %d files unparsed" % (len(unreadable), len(files)),
            file=sys.stderr,
        )
        return 2

    measured = _measured_by_file(cols)
    totals = _summary(measured)

    if args.write_baseline and unreadable:
        print(
            "RC 2: not freezing a baseline over an incomplete universe: %d of %d files"
            " do not parse, so their debt would be undeclarable (%s)"
            % (
                len(unreadable),
                len(files),
                ", ".join(u.path for u in unreadable),
            ),
            file=sys.stderr,
        )
        return 2

    if args.write_baseline:
        _write_baseline(baseline_path, args.pattern, measured)
        shadows = totals[scanner.SHADOW]
        if args.json:
            print(
                json.dumps(
                    {
                        "baseline": baseline_path.as_posix(),
                        "debt": _debt_of(measured),
                        "total": totals,
                        "rc": 1 if shadows else 0,
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print(
                "baseline written to %s: %d files · shadow %d · ordinal %d"
                % (
                    baseline_path.as_posix(),
                    len(_debt_of(measured)),
                    shadows,
                    totals[scanner.ORDINAL],
                )
            )
            if labels:
                print(
                    "  (%d test names were not read as ordinals: --label-pattern `%s`)"
                    % (len(labels), args.label_pattern)
                )
        if shadows:
            print(
                "RC 1: %d shadows left out of the baseline (a shadow is overwritten code,"
                " not debt to ratchet)" % shadows
            )
            return 1
        return 0

    baseline_present = baseline_path.is_file()
    baseline, error = _load_baseline(baseline_path)
    if error:
        print("RC 2: %s" % error, file=sys.stderr)
        return 2

    ups, zombies = _compare(measured, baseline, [u.path for u in unreadable])
    rc = 1 if (ups or zombies or totals[scanner.SHADOW]) else 0
    if args.strict and totals[scanner.SHARED]:
        rc = 1

    if args.json:
        print(
            json.dumps(
                {
                    "files": len(files),
                    "parsed": parsed,
                    "unparsed": [
                        {"path": u.path, "lineno": u.lineno, "reason": u.reason}
                        for u in unreadable
                    ],
                    "label_pattern": args.label_pattern,
                    "labels_set_aside": labels,
                    "total": totals,
                    "collisions": [
                        {
                            "kind": c.kind,
                            "path": c.path,
                            "scope": c.scope,
                            "name": c.name,
                            "line": c.line,
                            "first": c.first,
                        }
                        for c in cols
                    ],
                    "ups": ups,
                    "zombies": zombies,
                    "baseline": baseline_path.as_posix(),
                    "baseline_present": baseline_present,
                    "rc": rc,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return rc

    print(
        "test-ordinal-ratchet: %s · shadow %d · ordinal %d · shared %d"
        % (
            _files(len(files)) if not unreadable else "%d of %s" % (parsed, _files(len(files))),
            totals[scanner.SHADOW],
            totals[scanner.ORDINAL],
            totals[scanner.SHARED],
        )
    )
    if unreadable:
        if args.detail:
            for u in unreadable:
                print("  NOT MEASURED %s" % u.report_line())
        else:
            print(
                "  (%d of %d files did not parse: not measured, not counted as zero,"
                " their declared debt is frozen in place; --detail lists them,"
                " --strict-syntax refuses)" % (len(unreadable), len(files))
            )
    if labels:
        if args.detail:
            for name in labels:
                print("  LABEL %s (the number is a label, not a sequence ordinal)" % name)
        else:
            print(
                "  (%d test names set aside by --label-pattern `%s`: their number is a label,"
                " not a sequence ordinal; --detail lists them)"
                % (len(labels), args.label_pattern)
            )
    hidden_ordinal = 0
    hidden_shared = 0
    for c in cols:
        if c.kind == scanner.SHARED:
            if not (args.strict or args.detail):
                hidden_shared += 1
                continue
        elif c.kind == scanner.ORDINAL and not args.detail and c.path not in ups:
            hidden_ordinal += 1
            continue
        print("  " + c.report_line())
    if hidden_ordinal:
        print(
            "  (%d ordinal entries inherited inside their baseline: not charged; --detail lists them)"
            % hidden_ordinal
        )
    if hidden_shared:
        print(
            "  (%d shared ordinals across scopes: legal, no test is lost;"
            " --detail lists them, --strict charges them)" % hidden_shared
        )
    if ups and not baseline_present:
        print(
            "  (no baseline at %s: nothing is ratcheted yet, so all measured debt is charged;"
            " freeze it with --write-baseline)" % baseline_path.as_posix()
        )
    for path, counts in sorted(ups.items()):
        print("  UP %s: %s" % (path, ", ".join("%s +%d" % pair for pair in sorted(counts.items()))))
    for path, counts in sorted(zombies.items()):
        print(
            "  ZOMBIE %s: %s (the debt no longer exists: remove it from the baseline)"
            % (path, ", ".join("%s -%d" % pair for pair in sorted(counts.items())))
        )
    if rc:
        causes = []
        if totals[scanner.SHADOW]:
            causes.append(
                "%d shadows (a test that never runs: no baseline can absorb them)"
                % totals[scanner.SHADOW]
            )
        if ups and not baseline_present:
            causes.append("no baseline to ratchet against")
        elif ups:
            causes.append("%d files go up" % len(ups))
        if zombies:
            causes.append("%d declare resolved debt" % len(zombies))
        if args.strict and totals[scanner.SHARED]:
            causes.append("%d shared ordinals charged by --strict" % totals[scanner.SHARED])
        print("RC 1: " + " · ".join(causes))
    else:
        print(
            "RC 0: no new collisions over %s, on %d of %s read"
            % (baseline_path.as_posix(), parsed, _files(len(files)))
        )
    return rc


if __name__ == "__main__":
    sys.exit(main())
