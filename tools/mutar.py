#!/usr/bin/env python3
"""Mutation audit of this package's own tests.

A guard whose removal no test notices is not a guard: it is decoration. Every
row below inverts one documented behaviour of `ordinal_ratchet`; the suite has
to fail for each of them. A row that survives names a behaviour nobody pins,
and that is the finding — not the tool's opinion of itself.

Dev tool, not shipped in the wheel. RC 0 every mutant dies · RC 1 survivors ·
RC 2 the harness itself cannot measure (an anchor is missing or not unique).
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
from typing import List, NamedTuple

ROOT = pathlib.Path(__file__).resolve().parents[1]


class Mutation(NamedTuple):
    path: str
    anchor: str
    replace: str
    label: str


MUTATIONS: List[Mutation] = [
    Mutation(
        "ordinal_ratchet/scanner.py",
        'RE_ORDINAL = re.compile(r"^test_(\\d+)")',
        'RE_ORDINAL = re.compile(r"^test(\\d+)")',
        "ordinal needs the underscore before the digits",
    ),
    Mutation(
        "ordinal_ratchet/scanner.py",
        "isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))",
        "isinstance(node, ast.FunctionDef)",
        "async def is read as a definition",
    ),
    Mutation(
        "ordinal_ratchet/scanner.py",
        "            yield from _definitions(node.body, nested, path)",
        "            pass",
        "a class body is read",
    ),
    Mutation(
        "ordinal_ratchet/scanner.py",
        'if node.name.startswith("test"):',
        'if node.name.startswith("test_"):',
        "the `test` prefix, not only `test_`",
    ),
    Mutation(
        "ordinal_ratchet/scanner.py",
        "if match and not (label and label.search(d.name)):",
        "if match:",
        "the label declaration is honoured in the ordinal pass",
    ),
    Mutation(
        "ordinal_ratchet/scanner.py",
        "        if key in first_seen:",
        "        if False and key in first_seen:",
        "same name in one scope is a shadow",
    ),
    Mutation(
        "ordinal_ratchet/scanner.py",
        "        if len(by_scope) > 1:",
        "        if len(by_scope) > 99:",
        "one ordinal in two scopes is counted as shared",
    ),
    Mutation(
        "ordinal_ratchet/scanner.py",
        "            if len({d.name for d in ds}) < 2:",
        "            if len(ds) < 2:",
        "names are compared, not counts, in one scope",
    ),
    Mutation(
        "ordinal_ratchet/scanner.py",
        "RATCHETED = (ORDINAL,)",
        "RATCHETED = (ORDINAL, SHADOW)",
        "a shadow can never be frozen into the baseline",
    ),
    Mutation(
        "ordinal_ratchet/scanner.py",
        "        key=lambda d: (d.path, d.line),",
        "        key=lambda d: (d.name,),",
        "every set-aside definition keeps its locus",
    ),
    Mutation(
        "ordinal_ratchet/scanner.py",
        "            aside[d.path] = aside.get(d.path, 0) + 1",
        "            aside[d.path] = 1",
        "the set-aside term is counted, not set",
    ),
    Mutation(
        "ordinal_ratchet/scanner.py",
        "            unreadable.append(Unreadable(path, error.lineno, error.msg))",
        '            unreadable.append(Unreadable(path, None, "?"))',
        "an unread file names its line and reason",
    ),
    Mutation(
        "ordinal_ratchet/cli.py",
        "    if frozen.label_pattern != label_pattern:",
        "    if False:",
        "a frozen label declaration is checked on read",
    ),
    Mutation(
        "ordinal_ratchet/cli.py",
        "    if frozen.patterns is not None and tuple(sorted(set(patterns))) != frozen.patterns:",
        "    if False:",
        "a frozen glob is checked on read",
    ),
    Mutation(
        "ordinal_ratchet/cli.py",
        '    if label_pattern:\n        payload["label_pattern"] = label_pattern',
        '    if label_pattern:\n        payload["label_pattern"] = "x"',
        "the baseline writes the label declaration it was frozen with",
    ),
    Mutation(
        "ordinal_ratchet/cli.py",
        "        return tuple(sorted(set(value)))",
        "        return tuple(value)",
        "the frozen globs are compared as a set",
    ),
    Mutation(
        "ordinal_ratchet/cli.py",
        "rc = 1 if (ups or zombies or totals[scanner.SHADOW]) else 0",
        "rc = 1 if (ups or zombies) else 0",
        "a shadow fails the run",
    ),
    Mutation(
        "ordinal_ratchet/cli.py",
        "            elif declared[kind] > now[kind] and path not in blind:",
        "            elif declared[kind] > now[kind]:",
        "an unread file's debt is neither charged nor resolved",
    ),
    Mutation(
        "ordinal_ratchet/cli.py",
        "            if now[kind] > declared[kind]:",
        "            if False:",
        "debt above the baseline is charged",
    ),
    Mutation(
        "ordinal_ratchet/cli.py",
        "if kind in scanner.RATCHETED}",
        "if True}",
        "only ratcheted classes are written to the baseline",
    ),
    Mutation(
        "ordinal_ratchet/cli.py",
        "    if args.strict and totals[scanner.SHARED]:\n        rc = 1",
        "    if False:\n        rc = 1",
        "--strict charges a shared ordinal",
    ),
    Mutation(
        "ordinal_ratchet/cli.py",
        "    if args.strict_syntax and unreadable:",
        "    if False:",
        "--strict-syntax refuses an incomplete read",
    ),
    Mutation(
        "ordinal_ratchet/cli.py",
        "        if key in disputed:",
        "        if False:",
        "two homonym roots keep two keys",
    ),
    Mutation(
        "ordinal_ratchet/cli.py",
        "        if not sibling or sibling in seen:",
        "        if True:",
        "the sibling naming convention is counted",
    ),
    Mutation(
        "ordinal_ratchet/cli.py",
        "    if args.write_baseline and unreadable:",
        "    if False:",
        "no baseline is frozen over an incomplete universe",
    ),
    Mutation(
        "ordinal_ratchet/cli.py",
        '                    "label_files": [',
        '                    "label_file": [',
        "the census is published under its declared key",
    ),
    Mutation(
        "ordinal_ratchet/__init__.py",
        '    __version__ = _installed_version("test-ordinal-ratchet")',
        '    __version__ = "0.1.0"',
        "the version is the installed one, not a literal",
    ),
    Mutation(
        "ordinal_ratchet/cli.py",
        'parser.add_argument("--version", action="version", version="%(prog)s " + _VERSION)',
        'parser.add_argument("--version", action="version", version="%(prog)s 0.1.0")',
        "the CLI reports the package version, not its own literal",
    ),
]


def one(mutation: Mutation) -> str:
    """None when the mutant is dead (the suite fails), else why it lived."""
    with tempfile.TemporaryDirectory(prefix="mut-") as tmp:
        sandbox = pathlib.Path(tmp)
        for name in ("ordinal_ratchet", "tests"):
            shutil.copytree(
                ROOT / name, sandbox / name, ignore=shutil.ignore_patterns("__pycache__")
            )
        target = sandbox / mutation.path
        source = target.read_text(encoding="utf-8")
        if source.count(mutation.anchor) != 1:
            return "anchor found %d times" % source.count(mutation.anchor)
        target.write_text(source.replace(mutation.anchor, mutation.replace), encoding="utf-8")
        env = dict(os.environ, PYTHONPATH=str(sandbox))
        done = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-x", "tests"],
            cwd=str(sandbox),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        return None if done.returncode != 0 else "no test failed"


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="machine-readable result")
    args = parser.parse_args(argv)

    rows = []
    broken = False
    for mutation in MUTATIONS:
        lived = one(mutation)
        if lived is not None and lived.startswith("anchor"):
            broken = True
        rows.append({"label": mutation.label, "killed": lived is None, "why": lived})

    killed = sum(1 for row in rows if row["killed"])
    if args.json:
        print(json.dumps({"mutations": len(rows), "killed": killed, "rows": rows}, indent=2))
    else:
        for row in rows:
            verdict = "KILLED  " if row["killed"] else "SURVIVED"
            print("%s %s%s" % (verdict, row["label"], "" if row["killed"] else " — %s" % row["why"]))
        print("%d mutations · %d killed · %d survived" % (len(rows), killed, len(rows) - killed))
    if broken:
        print("RC 2: the harness cannot measure: an anchor is missing or not unique", file=sys.stderr)
        return 2
    return 0 if killed == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
