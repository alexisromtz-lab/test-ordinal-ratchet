"""Collisions between test names: silent shadowing and reused ordinals.

Two different defects share one cause: a test's name is an identifier, and
identifiers get reused when branches merge.

  shadow  two definitions of the SAME name in the SAME scope. Python keeps the
          last binding and the first one never runs: the test disappears while
          git reports no conflict, because the text never collides.
  ordinal two DIFFERENT names sharing a numeric prefix (`test_36_a`,
          `test_36_b`). Both run, but any reference to "test_36" stops being
          injective: `-k test_36` and the reports cannot tell them apart.
  shared  the same ordinal in different classes of one file. Legal: separate
          scopes, both run. Counted and published, never charged by default.

Read with `ast`, not with regular expressions: a name inside a docstring or a
comment is not a definition.
"""

from __future__ import annotations

import ast
import dataclasses
import re
from typing import Dict, Iterable, Iterator, List, Sequence, Tuple

RE_ORDINAL = re.compile(r"^test_(\d+)")

SHADOW = "shadow"
ORDINAL = "ordinal"
SHARED = "shared"

#: Only these are charged by the ratchet. `shared` is counted and published but
#: never fails by default: two classes of one file may reuse an ordinal without
#: a single test stopping to run.
RATCHETED = (SHADOW, ORDINAL)
CLASSES = (SHADOW, ORDINAL, SHARED)


@dataclasses.dataclass(frozen=True)
class Definition:
    path: str
    scope: str
    name: str
    line: int


@dataclasses.dataclass(frozen=True)
class Collision:
    kind: str
    path: str
    scope: str
    name: str
    line: int
    first: int

    def report_line(self) -> str:
        if self.kind == SHADOW:
            return "%s:%d %s.%s overwrites the definition at :%d (that test never runs)" % (
                self.path,
                self.line,
                self.scope,
                self.name,
                self.first,
            )
        if self.kind == SHARED:
            return "%s:%d %s since :%d (legal: no test stops running)" % (
                self.path,
                self.line,
                self.name,
                self.first,
            )
        return "%s:%d %s.%s reuses the ordinal of the definition at :%d" % (
            self.path,
            self.line,
            self.scope,
            self.name,
            self.first,
        )


def _definitions(body: List[ast.stmt], scope: str, path: str) -> Iterator[Definition]:
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test"):
                yield Definition(path, scope, node.name, node.lineno)
        elif isinstance(node, ast.ClassDef):
            nested = node.name if scope == "module" else scope + "." + node.name
            yield from _definitions(node.body, nested, path)


def definitions(source: str, path: str) -> List[Definition]:
    """`test*` definitions of one source, with their scope. `ast` or nothing."""
    tree = ast.parse(source)
    return list(_definitions(tree.body, "module", path))


def collisions(defs: Sequence[Definition]) -> List[Collision]:
    """Shadow always; ordinal inside one scope; `shared` only counted."""
    found: List[Collision] = []

    first_seen: Dict[Tuple[str, str, str], int] = {}
    for d in defs:
        key = (d.path, d.scope, d.name)
        if key in first_seen:
            found.append(Collision(SHADOW, d.path, d.scope, d.name, d.line, first_seen[key]))
        else:
            first_seen[key] = d.line

    groups: Dict[Tuple[str, int], List[Definition]] = {}
    for d in defs:
        match = RE_ORDINAL.match(d.name)
        if match:
            groups.setdefault((d.path, int(match.group(1))), []).append(d)

    for (path, number), group in sorted(groups.items()):
        by_scope: Dict[str, List[Definition]] = {}
        for d in group:
            by_scope.setdefault(d.scope, []).append(d)
        if len(by_scope) > 1:
            first = min(d.line for d in group)
            found.append(
                Collision(
                    SHARED,
                    path,
                    "*",
                    "ordinal %d in %d scopes" % (number, len(by_scope)),
                    first,
                    first,
                )
            )
        for scope, ds in by_scope.items():
            if len({d.name for d in ds}) < 2:
                continue
            ordered = sorted(ds, key=lambda d: d.line)
            for d in ordered[1:]:
                found.append(Collision(ORDINAL, path, scope, d.name, d.line, ordered[0].line))
    return found


def count(cols: Iterable[Collision]) -> Dict[str, int]:
    return {kind: sum(1 for c in cols if c.kind == kind) for kind in CLASSES}


def scan(sources: Dict[str, str]) -> Tuple[List[Collision], Dict[str, str]]:
    """Return (collisions, unreadable). A source that does not parse is not guessed."""
    every: List[Collision] = []
    unreadable: Dict[str, str] = {}
    for path in sorted(sources):
        try:
            every.extend(collisions(definitions(sources[path], path)))
        except SyntaxError as error:
            unreadable[path] = "line %s: %s" % (error.lineno, error.msg)
    return every, unreadable
