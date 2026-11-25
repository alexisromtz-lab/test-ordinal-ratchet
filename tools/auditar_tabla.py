#!/usr/bin/env python3
"""Read this repository's published audit table with an instrument.

The table in README.md is a set of claims: "63 test files, 2 shadow" for one
repository, "2 413" for a total. A claim nobody re-measures ages in place, and a
number that cannot be reproduced by a reader is not evidence, it is prose. This
tool takes a directory of already-cloned repositories, measures each one with the
package itself, and compares the row against the table.

    python tools/auditar_tabla.py --corpus /tmp/corpus            # measure
    python tools/auditar_tabla.py --corpus /tmp/corpus --check    # and compare

A row whose repository is not in the corpus is NO_MEDIDO, never a match: the
absence of a clone is state of the calculation, not state of the table.

Columns the instrument cannot reproduce are declared, not skipped in silence:
`async def tests` (the table's own second pass) and `ordinal (labels declared)`
(whose per-repository pattern lives outside the table) are reported as
NO_MEDIDO, and a column whose header names an interpreter other than the one
running the check refuses the comparison with RC 2 — a count of unparsed files
is a fact about grammar, and grammar is the interpreter.

RC 0 every compared value matches · RC 1 drift (the row and the measurement are
named) · RC 2 nothing was compared.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import pathlib
import re
import sys
import tempfile
from typing import Dict, List, NamedTuple, Optional, Tuple

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ordinal_ratchet import cli  # noqa: E402

RE_REPO = re.compile(r"^[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+$")
#: what a table declares it scanned, immediately above it. A table that does not
#: say so is NO_MEDIDO: `tests/` and the repository root are not the same universe.
RE_SCOPE = re.compile(r"<!--\s*audit-table:\s*scanned=(\S+)\s*-->")
RE_VERSION = re.compile(r"@\s*(\d+)\.(\d+)\.(\d+)")

#: header cell -> key of the measurement. A column absent from this map is
#: measured by nobody here and is published as NO_MEDIDO rather than assumed.
COLUMNS = {
    "test files": "files",
    "unparsed": "unparsed",
    "unread": "unparsed",
    "shadow": "shadow",
    "shared": "shared",
    "rc": "rc",
    "ordinal": "ordinal",
    "ordinal (raw)": "ordinal",
}
DECLARED = {
    "async def tests": "the table's second pass over the repository root is not re-run here",
    "ordinal (labels declared)": "the per-repository --label-pattern is not published in the table",
}


class Row(NamedTuple):
    line: int
    cells: List[str]

    @property
    def repo(self) -> str:
        return self.cells[0].strip("`* ")

    @property
    def covered(self) -> bool:
        return bool(RE_REPO.match(self.repo))


def _cells(line: str) -> List[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _number(cell: str) -> Optional[int]:
    # The table writes thousands with a space and marks the aggregates in bold.
    digits = re.sub(r"[^0-9]", "", cell)
    if not cell or not digits:
        return None
    if re.search(r"[A-Za-z]", cell.replace("n/a", "x")):
        return None
    return int(digits)


def table(readme: pathlib.Path) -> List[Tuple[List[str], List[Row], Optional[str]]]:
    """Every table with an `owner/repo` first column: headers, rows, declared scope."""
    lines = readme.read_text(encoding="utf-8").splitlines()
    blocks: List[Tuple[List[str], List[Row], Optional[str]]] = []
    header: Optional[List[str]] = None
    rows: List[Row] = []
    scope: Optional[str] = None
    for number, line in enumerate(lines, 1):
        if not line.startswith("|"):
            if header is not None:
                blocks.append(([name.lower() for name in header], rows, scope))
                header, rows, scope = None, [], None
            continue
        cells = _cells(line)
        if header is None:
            header = cells
            scope = None
            for above in reversed(lines[max(0, number - 3) : number - 1]):
                found = RE_SCOPE.search(above)
                if found:
                    scope = found.group(1)
                    break
            continue
        row = Row(number, cells)
        if row.covered:
            rows.append(row)
    if header is not None:
        blocks.append(([name.lower() for name in header], rows, scope))
    return [block for block in blocks if block[1]]


def locate(corpus: pathlib.Path, repo: str) -> Optional[pathlib.Path]:
    for name in (repo.replace("/", "__"), repo.replace("/", "_"), repo.split("/")[1]):
        candidate = corpus / name
        if candidate.is_dir():
            return candidate
    return None


def scan(target: pathlib.Path, scope: Optional[str]) -> Dict[str, object]:
    """Measure one clone through the package's own entry point, not a copy of it."""
    if scope in (None, "", "."):
        scanned = target
    else:
        scanned = target / scope.strip("/")
    out, err = io.StringIO(), io.StringIO()
    with tempfile.TemporaryDirectory(prefix="tabla-") as tmp:
        argv = [
            str(scanned),
            "--json",
            "--baseline",
            str(pathlib.Path(tmp) / "absent.json"),
        ]
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = cli.main(argv)
    payload = json.loads(out.getvalue())
    totals = payload["total"]
    return {
        "files": payload["files"],
        "unparsed": len(payload["unparsed"]),
        "shadow": totals["shadow"],
        "ordinal": totals["ordinal"],
        "shared": totals["shared"],
        "rc": rc,
        "scanned": scanned.as_posix(),
    }


def want(value: Optional[int], measured: int) -> bool:
    return value is not None and value == measured


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", required=True, type=pathlib.Path)
    parser.add_argument("--readme", default=ROOT / "README.md", type=pathlib.Path)
    parser.add_argument("--check", action="store_true", help="compare, and fail on drift")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if not args.corpus.is_dir():
        print("RC 2: no corpus at %s" % args.corpus, file=sys.stderr)
        return 2

    running = sys.version_info
    findings: List[Dict[str, object]] = []
    compared = 0
    drifted = 0

    for columns, rows, scope in table(args.readme):
        for row in rows:
            entry: Dict[str, object] = {
                "repo": row.repo,
                "line": row.line,
                "scanned": scope,
                "fields": {},
            }
            clip = locate(args.corpus, row.repo)
            if clip is None:
                entry["status"] = "NO_MEDIDO"
                entry["why"] = "no clone in the corpus"
                findings.append(entry)
                continue
            if scope is None:
                entry["status"] = "NO_MEDIDO"
                entry["why"] = "the table does not declare what it scanned"
                findings.append(entry)
                continue
            measured = scan(clip, scope)
            entry["measured"] = measured
            status = "MATCH"
            for index, header_name in enumerate(columns[1:], start=1):
                if index >= len(row.cells):
                    break
                base = header_name.split("@")[0].strip()
                key = COLUMNS.get(base)
                if key is None:
                    entry["fields"][header_name] = DECLARED.get(
                        header_name, "not reproduced by any instrument here"
                    )
                    continue
                version = RE_VERSION.search(header_name)
                if version and tuple(int(part) for part in version.groups())[:2] != tuple(
                    running[:2]
                ):
                    entry["fields"][header_name] = (
                        "the table declares %s, this check runs %d.%d: a count of unparsed"
                        " files is a fact about grammar" % (".".join(version.groups()), *running[:2])
                    )
                    continue
                claimed = _number(row.cells[index])
                if claimed is None:
                    entry["fields"][header_name] = "not a number"
                    continue
                match = want(claimed, int(measured[key]))
                entry["fields"][header_name] = {
                    "readme": claimed,
                    "measured": measured[key],
                    "match": match,
                }
                compared += 1
                if not match:
                    drifted += 1
                    status = "DRIFT"
            entry.setdefault("status", status)
            findings.append(entry)

    if args.json:
        print(json.dumps({"compared": compared, "drift": drifted, "rows": findings}, indent=2))
    else:
        for entry in findings:
            print(
                "%-9s %s (line %d, scanned %s)"
                % (entry["status"], entry["repo"], entry["line"], entry["scanned"])
            )
            if entry["status"] == "NO_MEDIDO":
                print("          %s" % entry["why"])
            for field, value in sorted(entry["fields"].items()):
                if isinstance(value, dict):
                    print(
                        "          %-28s table %-7s measured %-7s %s"
                        % (
                            field,
                            value["readme"],
                            value["measured"],
                            "ok" if value["match"] else "DRIFT",
                        )
                    )
                else:
                    print("          %-28s NO_MEDIDO: %s" % (field, value))
        print("%d values compared · %d drift" % (compared, drifted))

    if compared == 0:
        print(
            "RC 2: nothing compared: no published row had a clone in %s" % args.corpus,
            file=sys.stderr,
        )
        return 2
    return 0 if drifted == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
