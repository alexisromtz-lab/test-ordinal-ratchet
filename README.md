# test-ordinal-ratchet

A static reader for Python test suites whose **names are identifiers** — `test_36_something` — and
where two branches can silently break injectivity without `git` saying a word.

`git` compares text. Two branches that add `def test_36_a` and `def test_36_b` in different places
of the same file merge with **zero conflicts**, and the result is not the same kind of defect
depending on where they land:

| class | what happened | does a test stop running? |
|---|---|---|
| `shadow` | same name, **same scope** | **yes**: Python keeps the last binding, the first one disappears |
| `ordinal` | different names, **same number, same scope** | no, but `-k test_36` and reports stop disambiguating |
| `shared` | same number, **different classes of the same file** | no: separate scopes, both run |

The case that started this tool was a `shared` one: two classes of the same file declaring
`test_36`, git with zero textual conflicts, both tests running. The honest conclusion is that ordinal
ambiguity was **not** a lost test — which is why the tool separates the three classes instead of
counting them together.

## Install

No runtime dependencies, Python ≥ 3.9:

```console
$ pip install .
$ test-ordinal-ratchet tests
test-ordinal-ratchet: 320 files · shadow 0 · ordinal 39 · shared 57
```

Without installing anything:

```console
$ python -m ordinal_ratchet tests
test-ordinal-ratchet: 1 file · shadow 0 · ordinal 0 · shared 0
RC 0: no new collisions over .ordinal-ratchet.json, on 1 of 1 file read
```

Not on PyPI yet, so `uvx test-ordinal-ratchet` does not resolve — but the repository does, and the
console script is reachable by its own name (verified against `v0.1.1` on 2026-11-25: it builds and
prints the same report):

```console
$ uvx --from git+https://github.com/alexisromtz-lab/test-ordinal-ratchet test-ordinal-ratchet tests
```

## Output contract

| RC | meaning |
|---|---|
| `0` | nothing increased over the declared baseline (which may be zero) |
| `1` | a **new** collision, a counter above the baseline, or declared debt that no longer exists |
| `2` | invalid usage · **no** test file matched · nothing at all parses · `--strict-syntax` and a file does not parse · the run's universe is not the one the baseline was frozen over |

`RC 2` exists so that absence of subject is never read as zero: if the glob finds nothing, there is no
measurement and the tool refuses to say "clean".

### A file that does not parse is not a veto

A single unparseable file used to blind the whole repository: one `match` statement anywhere and every
other file went unread. Refusing was the safe direction, but it also hid real findings, so it was a
defect of its own. An unreadable file is now reported as **not measured** and the rest of the universe
is read:

```
test-ordinal-ratchet: 239 of 241 files · shadow 0 · ordinal 0 · shared 0
  (2 of 241 files did not parse: not measured, not counted as zero, their declared debt is frozen in place; --detail lists them, --strict-syntax refuses)
RC 0: no new collisions over .ordinal-ratchet.json, on 239 of 241 files read
```

Two consequences of the same rule:

- an unparsed file is **never counted as zero**, so it cannot report itself clean;
- an unparsed file **never frees declared debt**, so it cannot be reported as a `zombie`.

`--strict-syntax` restores the all-or-nothing refusal, and `--write-baseline` refuses to freeze an
incomplete universe instead of locking in debt it could not declare.

The floor is the interpreter, so the ceiling is measured and published instead of inferred. All
**21 repositories**, one scan each (`tests/` when it exists, repository root otherwise), three
interpreters, `2026-11-25` — a file the old interpreter cannot read is *not* a file that hides a
collision:

<!-- audit-table: scanned=tests/ -->
| repository | test files | unread @3.9.6 | unread @3.12.13 | unread @3.14.8 | shadow |
|---|---|---|---|---|---|
| `apache/airflow` | 2 412 | 6 | 0 | 0 | 0 |
| `saleor/saleor` | 1 236 | 0 | 0 | 0 | 0 |
| `pandas-dev/pandas` | 994 | 0 | 0 | 0 | 0 |
| `django/django` | 629 | 2 | 0 | 0 | 0 |
| `fastapi/fastapi` | 550 | 0 | 0 | 0 | 0 |
| `ansible/ansible` | 367 | 0 | 0 | 0 | 0 |
| `scikit-learn/scikit-learn` | 260 | 0 | 0 | 0 | 0 |
| `sqlalchemy/sqlalchemy` | 241 | 4 | 2 | 0 | 0 |
| `fastapi/typer` | 211 | 0 | 0 | 0 | 0 |
| `celery/celery` | 181 | 0 | 0 | 0 | 0 |
| `pydantic/pydantic` | 140 | 2 | 0 | 0 | 0 |
| `python-poetry/poetry` | 130 | 0 | 0 | 0 | 0 |
| `pytest-dev/pytest` | 118 | 0 | 0 | 0 | 0 |
| `aiohttp/aiohttp` | 78 | 0 | 0 | 0 | 0 |
| `Textualize/rich` | 63 | 0 | 0 | 0 | **2** |
| `pallets/click` | 43 | 0 | 0 | 0 | 0 |
| `encode/starlette` | 31 | 0 | 0 | 0 | 0 |
| `encode/httpx` | 31 | 0 | 0 | 0 | 0 |
| `pallets/flask` | 22 | 0 | 0 | 0 | 0 |
| `psf/black` | 14 | 0 | 0 | 0 | 0 |
| `psf/requests` | 9 | 0 | 0 | 0 | 0 |
| **total** | **7 760** | **14** | **2** | **0** | **2** |

Twelve of the 14 files unreadable under 3.9.6 are read under 3.12.13, and the two PEP 750 `t-string`
files of `sqlalchemy` are read under 3.14.8, where the unreadable count is zero everywhere. Going
forward in versions never lost a file and never changed a verdict: on the row where a version
difference exists the collisions are identical at all three (`shadow 0 · ordinal 0`), and every other
row is identical by having nothing to compare. Nothing was hidden behind the parser — the gate was
only a version of `ast`.

The loss is also named, per file, with the line that stopped the parser:

```console
$ test-ordinal-ratchet tests --detail
  NOT MEASURED tests/test_structural_pattern_matching.py (line 11: invalid syntax)
```

`--json` carries the same rows as objects, so nothing has to be recovered from a string:

```json
"unparsed": [{"path": "tests/test_structural_pattern_matching.py", "lineno": 11, "reason": "invalid syntax"}]
```

### The universe is a glob, and a glob can be the wrong one

`test_*.py` and `*_test.py` are the same convention spelled two ways, and a repository picks one.
A single default glob over the other one is not a zero: it is a zero over a universe that was never
declared. So a run that finds nothing names the sibling convention and the flag that would read it,
and a run that finds something counts what it left outside:

```console
$ test-ordinal-ratchet tests          # a tree whose tests are named the other way
RC 2: no file matches `test_*.py` under tests (no subject, no zero)
  2 files match `*_test.py` (e.g. edge_test.py): add --pattern '*_test.py'

$ test-ordinal-ratchet . --pattern 'test_*.py' --pattern '*_test.py'   # pytest, measured
test-ordinal-ratchet: 123 files · shadow 0 · ordinal 0 · shared 0
```

Measured over seven real suites (one scan each, default vs both conventions):

| suite | `test_*.py` | both | difference |
|---|---|---|---|
| pytest | 118 | 123 | **+5** (`bench/unit_test.py`, `testing/acceptance_test.py`, `testing/deprecated_test.py`, …) |
| black · celery · click · poetry · requests · rich | 14 · 181 · 43 · 130 · 9 · 63 | identical | 0 |

The five extra files carry **0** additional collisions: the default glob under-reads pytest, and
reading it does not invent debt. That is why the second convention is offered and counted, not
silently adopted — the published table below is the default-glob universe, and it says so.

`--json` declares both sides of that universe, so a filtered zero is never a mute zero — the same
default run over pytest:

```json
{"files": 118, "patterns": ["test_*.py"],
 "other_patterns": {"*_test.py": ["bench/unit_test.py", "testing/acceptance_test.py",
                                 "testing/deprecated_test.py", "testing/python/show_fixtures_per_test.py",
                                 "testing/example_scripts/perf_examples/collect_stats/template_test.py"]}}
```

### A number is not always a sequence ordinal

`test_36_a` and `test_36_b` share *ordinal 36*. `test_1d_margins` and `test_2d_margins` share *the
digit 1 and 2* — those are dimensions. Neither the file nor the AST says which one you meant, and no
lexical rule can decide: `test_08b_case` in a sequence-numbered suite is the sub-case *b* of ordinal
8, and it looks exactly like `test_1d`. Gluing the digits to a letter is not the signal.

Worse, tightening the rule to "a letter after the digits means a label" would drop 27 real ordinals
from the corpus this tool was extracted from (`test_08b_…`, `test_13b_…` are sub-cases of 08 and 13).
So the label space is **declared by the repository**, never guessed:

```console
$ test-ordinal-ratchet . --label-pattern '^test_\d+[a-zA-Z]'
```

Definitions set aside are counted and printable, so nothing is silently discarded:

```console
test-ordinal-ratchet: 260 files · shadow 0 · ordinal 0 · shared 0
  (16 test definitions set aside by --label-pattern `^test_\d+[a-zA-Z]`: their number is a label, not a sequence ordinal; --detail names the file and line of each)
RC 0: no new collisions over .ordinal-ratchet.json, on 260 of 260 files read
```

The unit is the **definition**, not the name. `scikit-learn` sets aside 16 definitions in 9 files, and
two of them are the same name: `test_1d_input` at `sklearn/ensemble/tests/test_forest.py:1150` and
again at `sklearn/tree/tests/test_tree.py:1618`. Counting distinct names published **15**, which is
neither the number of tests taken out of the ordinal pass nor a number any file can be found from.
Declaring the label space is a declaration about *tests*, so it is counted in tests.

The same run keeps the arithmetic per file, because `--detail` can only name a locus the census has.
For every file with a set-aside name, `--json` publishes `label_files` next to `labels_set_aside`:

```console
$ test-ordinal-ratchet pandas/tests/io/sas --label-pattern '^test_\d+[a-zA-Z]' --json
  "label_files": [
    { "path": "test_sas7bdat.py", "read": 1, "set_aside": 2 }
  ],
  "labels_set_aside": [
    { "lineno": 1083, "name": "test_0x40_control_byte", "path": "test_sas7bdat.py", "scope": "module" },
    { "lineno": 1092, "name": "test_0x00_control_byte", "path": "test_sas7bdat.py", "scope": "module" }
  ],
```

`ordinal_space(f) = read(f) + set_aside(f)`, both terms counted and never obtained by subtraction.
A file with both terms non-zero is **half read**: its ordinal space is ratcheted only in part, so a
reused ordinal that crosses the declaration (`test_2_x` against `test_2d_plot`) is invisible there by
construction. `--detail` prints those files as `HALF READ path: N set aside, M read`.

| suite | files | set-aside definitions | files touched | half read |
|---|---|---|---|---|
| `scikit-learn` | 260 | 16 | 9 | 0 |
| `pandas` | 994 | 34 | 15 | 1 (`test_sas7bdat.py`, 2 set aside / 1 read) |
| `apache/airflow` | 2 412 | 10 | 6 | 0 |
| `aio-libs/aiohttp` | 79 | 9 | 4 | 0 |

The one half-read file in `pandas` is the case the old scalar could not name: `test_0x40_control_byte`
and `test_0x00_control_byte` are labels, one other ordinal in that file is read, and no ordinal
number is shared between the two sides — measured, not assumed: across the four suites above the
cross-overlap is `0`.

Four recipes, each measured on a real suite:

| what the number is | pattern | measured on |
|---|---|---|
| a dimension or a glued letter (`test_1d_x`, `test_2D_x`, `test_0x00_x`, `test_20news`) | `^test_\d+[a-zA-Z]` | `scikit-learn` 7 → 0, `pandas` 15 → 3, `ansible` 1 → 0 |
| an HTTP status code (`test_404_not_in_urls`) | `^test_[1-5]\d\d_` | `django` 5 → 0, `airflow` 404 → 0 |
| a date (`test_2027_02_28_flattens_keyed_xcom`) | `^test_\d{4}_\d\d_\d\d` | `airflow` 3 rows |
| both, joined with `\|` | `^test_[1-5]\d\d_\|^test_\d{4}_\d\d_\d\d` | `airflow` 5 → 1 |

That residual `1` is the point. `airflow-core/tests/unit/timetables/test_interval_timetable.py:890`
declares `test_7_and_9_entering` while `:849` already declares another `test_7_…`: a real reused
ordinal, still `RC 1` after the labels are declared. Declaring labels does not turn the tool off.

The opposite case is honest too: `pandas`' remaining three are `test_1000_sep_not_stripped`,
`test_20643_comment` and `test_32878_complex_itemsize` — a thousands separator and two GitHub issue
numbers. Written with a `_` after the digits they are **syntactically identical** to sequence
ordinals, so no pattern separates them; freeze them in the baseline, which is what the ratchet is
for. The flag keeps the *new* ones from being charged as regressions.

`shadow` is exempt by construction: two identical names in one scope are two identical names,
whatever the pattern claims, and that is tested. A **baseline cannot absorb a shadow** either:
`--write-baseline` leaves it out of the file and still exits `RC 1`, because a shadow is code that
no longer runs, not debt to be paid down. Measured on the real hook (`pre-commit try-repo`, clean
tree vs. one shadow) — see [pre-commit](#pre-commit).

By default only the rows that justify the RC are printed, plus one line with the totals. That is
deliberate: a legacy suite can carry dozens of legal `shared` ordinals, and printing them on every
run buries the verdict.

```
test-ordinal-ratchet: 320 files · shadow 0 · ordinal 39 · shared 57
  (39 ordinal entries inherited inside their baseline: not charged; --detail lists them)
  (57 shared ordinals across scopes: legal, no test is lost; --detail lists them, --strict charges them)
RC 0: no new collisions over .ordinal-ratchet.json, on 320 of 320 files read
```

With **no** baseline file the ratchet has nothing to ratchet against, so every measured `ordinal` is
charged and the run exits `1` — the safe direction. The output says so instead of calling it a
regression, and `--write-baseline` freezes the debt in one step:

```
test-ordinal-ratchet: 320 files · shadow 0 · ordinal 39 · shared 57
  (no baseline at .ordinal-ratchet.json: nothing is ratcheted yet, so all measured debt is charged; freeze it with --write-baseline)
  UP tests/test_acoplamiento_por_ruta.py: ordinal +3
  ...
RC 1: no baseline to ratchet against
```

### What a zero is a zero over

Three identities hold at once, and every term is published, so no term has to be inferred from
another:

```text
files(any convention) = found  + other_patterns        the glob chose a universe; the rest is counted
found                 = parsed + unparsed              a file that does not parse is not a zero
ordinal_space(parsed) = read   + set_aside             per file, with locus (label_files)

charged = ordinal collisions inside read               the ratchet lives here
shadow  = every parsed definition, set-aside included  never frozen into a baseline, never "debt"
```

A count that cannot be located is not a measurement, so none is published alone: `unparsed`,
`labels_set_aside` and `label_files` carry a `path` (and a `lineno` where a line exists), and
`--detail` prints the same rows a human would read.

### Flags

| flag | effect |
|---|---|
| `--baseline PATH` | baseline file (default `.ordinal-ratchet.json` in the cwd) |
| `--write-baseline` | freeze the current counts as inherited debt |
| `--label-pattern REGEX` | tests whose **name** matches are not read as sequence ordinals (never affects `shadow`); counted per definition, with locus |
| `--detail` | list every row, including the ones that are not charged |
| `--strict` | also fail (`RC 1`) when two scopes of one file reuse a number |
| `--strict-syntax` | fail (`RC 2`) when any file does not parse, instead of reading the rest |
| `--version` | the installed distribution's version — the number to quote when reporting a finding |
| `--json` | machine-readable output: counts, every collision, `ups`/`zombies`, `unparsed`, `labels_set_aside` (with `lineno`), `label_files` (`read`/`set_aside` per file), `patterns`, `other_patterns`, `rc` |
| `--pattern GLOB` | file glob (default `test_*.py`); **repeat it** to read several conventions in one run |

## The ratchet

A baseline of inherited debt, keyed by path **relative to the argument you scanned**, so it survives
cloning and moving:

```json
{
  "version": 1,
  "pattern": ["test_*.py"],
  "label_pattern": "^test_[1-5]\\d\\d_",
  "debt": {
    "tests/test_startup_order.py": {"ordinal": 2}
  }
}
```

A count is a count *over* a keyspace, so the file records the universe it was frozen over: `pattern`
(every glob the run read, always written) and `label_pattern` (written only when the run declared
one). Reading a baseline over a different universe is not a regression, it is a change of subject —
the same bytes re-read under another declaration — and it is refused rather than charged:

```
RC 2: not comparable: the baseline was frozen with --label-pattern `^test_[1-5]\d\d_`; this run declares none.
```

Measured before this check existed: freezing `pandas/tests/io` with a label pattern and reading it
without one reported `UP sas/test_sas7bdat.py: ordinal +1` — **1 of 1 declared rows, 100 % of the
debt attributed to the change of declaration**. Both directions are refused (a frozen declaration
read without it, and a run that sets one where the baseline has none), and an old baseline with no
`label_pattern` key still means "nothing declared", so existing files keep working.

Only `ordinal` is ever written here. `shadow` is not debt: a file with a live shadow is `RC 1` with
or without a baseline, and `--write-baseline` exits `1` naming the shadows it refused to freeze.

The ratchet turns one way: the declared count **may go down, never up**. And it charges the opposite
error too — a declared entry that no longer exists is a `zombie`, `RC 1`:

```
ZOMBIE tests/test_startup_order.py: ordinal -2 (the debt no longer exists: remove it from the baseline)
```

A debt list nobody prunes stops being evidence. That is why shrinking is legal but lying is not.

## Real-world audit

Seventeen well-known suites, shallow clone of the default branch, 2026-11-25. Scanned directory is
`tests/` when the repository has it, the repository root otherwise:

<!-- audit-table: scanned=tests/ -->
| repository | test files | unparsed @3.9.6 | shadow | ordinal | shared | RC |
|---|---|---|---|---|---|---|
| `django/django` | 629 | 2 | 0 | 5 | 3 | 1 |
| `fastapi/fastapi` | 550 | 0 | 0 | 0 | 0 | 0 |
| `sqlalchemy/sqlalchemy` | 241 | 4 | 0 | 0 | 0 | 0 |
| `fastapi/typer` | 211 | 0 | 0 | 0 | 0 | 0 |
| `celery/celery` | 181 | 0 | 0 | 0 | 0 | 0 |
| `pydantic/pydantic` | 140 | 2 | 0 | 0 | 0 | 0 |
| `python-poetry/poetry` | 130 | 0 | 0 | 0 | 0 | 0 |
| `pytest-dev/pytest` | 118 | 0 | 0 | 0 | 0 | 0 |
| `Textualize/rich` | 63 | 0 | **2** | 0 | 0 | 1 |
| `pallets/click` | 43 | 0 | 0 | 0 | 0 | 0 |
| `encode/starlette` | 31 | 0 | 0 | 0 | 0 | 0 |
| `encode/httpx` | 31 | 0 | 0 | 0 | 0 | 0 |
| `pallets/flask` | 22 | 0 | 0 | 0 | 0 | 0 |
| `psf/black` | 14 | 0 | 0 | 0 | 0 | 0 |
| `psf/requests` | 9 | 0 | 0 | 0 | 0 | 0 |
| **total** | **2 413** | **8** | **2** | **5** | **3** | |

Five more, same day, chosen for size rather than for tidiness — and measured twice, with and without
a declared label space:

<!-- audit-table: scanned=tests/ -->
| repository | test files | shadow | ordinal (raw) | ordinal (labels declared) |
|---|---|---|---|---|
| `apache/airflow` | 2 412 | 0 | 5 | **1** |
| `saleor/saleor` | 1 236 | 0 | 0 | 0 |
| `pandas-dev/pandas` | 994 | 0 | 15 | **3** |
| `ansible/ansible` | 367 | 0 | 0 | 0 |
| `scikit-learn/scikit-learn` | 260 | 0 | 7 | 0 |
| **total** | **5 269** | **0** | **27** | **4** |

**7 760 distinct files** over **21 repositories**, one scan each — 23 280 parses across the three
interpreters — plus a second look at the repository root for the five async-heavy suites, which
adds 21 files the `tests/` scan does not reach and does not add a repository. Two silent lost tests,
both in the same file of the same project. Across the whole sweep
the heuristic charges **31** `ordinal` rows: **27** have a shape a declared pattern can name (23 in
the five large suites plus `aiohttp`'s four), **1** is a genuinely reused ordinal (`airflow`'s
`test_7_…` at `:849` and `:890`), and **3** are numbers that look exactly like sequence ordinals and
are not — `pandas`' `test_20643_comment`, `test_32878_complex_itemsize` and
`test_1000_sep_not_stripped_after_whitespace`.

Five async-heavy suites, scanned at the **repository root** — `fastapi`, `typer`, `httpx` and
`starlette` also appear above, there scanned at `tests/`, which is 21 files less — because
`async def test_x` is an `ast.AsyncFunctionDef`, a different node type from `ast.FunctionDef`:

<!-- audit-table: scanned=. -->
| repository | test files | `async def` tests | shadow | ordinal (raw) | ordinal (labels declared) |
|---|---|---|---|---|---|
| `aiohttp/aiohttp` | 79 | 2 156 | 0 | 4 | **0** |
| `fastapi/fastapi` | 567 | 78 | 0 | 0 | 0 |
| `fastapi/typer` | 215 | 0 | 0 | 0 | 0 |
| `encode/httpx` | 31 | 114 | 0 | 0 | 0 |
| `encode/starlette` | 31 | 56 | 0 | 0 | 0 |
| **total** | **923** | **2 404** | **0** | **4** | **0** |

Async definitions collide exactly like plain ones — same name in the same class is a `shadow`, same
number in the same scope is an `ordinal`, whether the other side is `def` or `async def` — and the
suite pins it so it cannot regress into a silent zero. `aiohttp`'s four raw rows are all one HTTP
label again (`test_100_continue_*`: the `100 Continue` status), taken out by
`--label-pattern '^test_[1-5]\d\d_'`, which sets aside nine definitions across four files
(`test_client_functional.py:1155`, `test_urldispatch.py:1093` and `:1099`, `test_web_functional.py` five
times, `test_web_response.py:832`).

`sqlalchemy` is the row that justifies the unparseable-file granularity: four of its files do not
parse because they use syntax newer than the interpreter (`test_tstring_py314.py` is Python 3.14
t-strings). Before that change it was `RC 2` over the whole repository — a 239-file audit refused
because of files that are not even code for the interpreter running them.

The three interpreters agree on every collision and disagree on coverage: run on 3.9.6 the same
repositories lose **14** files (airflow 6, sqlalchemy 4, django 2, pydantic 2) and every count above
is unchanged. Point the tool at the interpreter the project targets; when you cannot, the loss is
declared instead of swallowed.

`django`'s five `ordinal` rows are all HTTP status codes — `400`, `403`, `404` — not sequence
numbers. The finding is literally true (`-k test_404` matches two tests and disambiguates neither)
but reading them as collisions of a *sequence* is wrong, and `--label-pattern '^test_[1-5]\d\d_'`
takes them out without touching `shadow`.

`rich` is the interesting one. `tests/test_console.py` defines two module-level functions twice:

- `test_soft_wrap` at `:47` and again at `:603` — the first one never runs;
- `test_force_color` at `:952`, **parametrized with three values**, and again at `:967` without
  parameters — the parametrized version is garbage-collected at class definition time.

Python's semantics are not ambiguous here; a three-line reproduction shows the loss:

```python
import pytest

@pytest.mark.parametrize("env_value", ["", "something", "0"])
def test_force_color(env_value):
    assert env_value in ("", "something", "0")

def test_force_color():
    assert True
```

```console
$ pytest test_proof.py --collect-only -q
test_proof.py::test_force_color
1 test collected
```

One test collected out of four. `git` sees nothing; CI stays green.

### The table has a reader

Every number above is a claim, and a claim nobody re-measures ages in place. `tools/auditar_tabla.py`
takes a directory of clones, measures each repository **through the package's own entry point**, and
compares the row against the table:

```bash
mkdir -p /tmp/corpus && git clone -q --depth 1 https://github.com/Textualize/rich /tmp/corpus/Textualize__rich
python tools/auditar_tabla.py --corpus /tmp/corpus --check
```

A clone is found by its `owner__repo` name (or by the bare repository name). Each table declares the
universe it scanned in an HTML comment on the line directly above it — `scanned=tests/`, or
`scanned=.` for the repository root — and the reader scans exactly that; `tests/` and the repository
root are not the same universe, and `fastapi` is 550 files in one and 567 in the other, which is the
whole reason the declaration is machine-readable instead of a sentence. A table without one is
`NO_MEDIDO`, not a guess.

Three verdicts, and none of them is silence:

| verdict | meaning |
| -- | -- |
| `MATCH` | the row and the measurement agree |
| `DRIFT` | the row says one number, the tree says another — `RC 1`, both printed |
| `NO_MEDIDO` | no clone, no declared scope, or a column no instrument here reproduces |

`RC 2` when nothing at all was compared: a run over an empty corpus is not a pass. Columns the tool
cannot reproduce are named rather than skipped — `` `async def` tests `` (the table's own second
pass) and `ordinal (labels declared)` (the per-repository pattern is not published in the table) —
and a column whose header names an interpreter other than the one running the check is refused one
column at a time, because a count of unparsed files is a fact about grammar:

```
$ python3 tools/auditar_tabla.py --corpus /tmp/corpus --check
MATCH     fastapi/fastapi (line 90, scanned tests/)
          test files                   table 550     measured 550     ok
          unread @3.12.13              NO_MEDIDO: the table declares 3.12.13, this check runs 3.9: a count of unparsed files is a fact about grammar
...
21 values compared · 0 drift
```

Measured, not assumed: over two clones (`Textualize/rich`, `fastapi/fastapi`) the run compares **21**
published values across four rows and drifts on none; rewriting one of them — `63` files to `64` —
turns the same run into `DRIFT Textualize/rich (line 101) · test files table 64 · measured 63` and
`RC 1`. The instrument that reports drift has itself been made to drift on purpose.


## pre-commit

The hook ships in `.pre-commit-hooks.yaml`, so it installs from the repository itself — no PyPI
needed:

```yaml
repos:
  - repo: https://github.com/alexisromtz-lab/test-ordinal-ratchet
    rev: v0.2.5
    hooks:
      - id: test-ordinal-ratchet
        args: ["tests", "--label-pattern", '^test_\d+[a-zA-Z]']
```

`pass_filenames` is **false** on purpose. pre-commit would otherwise hand the hook the staged files,
which shrinks the universe: the ratchet compares a partial read against a whole-repository baseline
and reports resolved debt that was never looked at. The subject of this tool is the repository, so
the hook triggers on a Python change and then reads everything.

Measured, not assumed — `pre-commit try-repo /path/to/test-ordinal-ratchet` on a scratch repository:

| tree | command | result |
|---|---|---|
| two files, no collision | `--all-files` | `Passed`, `RC 0` |
| one shadow in `tests/test_clean.py` | `--all-files` | `Failed`, `RC 1`, names `:11` overwriting `:8` |
| same shadow, hook handed a **clean** file | `--files tests/test_other.py` | `Failed`, `RC 1` — the argument is ignored, the whole tree is read |

The third row is the one that matters: it is the falsifier for `pass_filenames: false`. With
`pass_filenames: true` that run would have passed and shipped the shadow.

Keep the flag — and the declared labels — in the configuration that runs the check. The declaration
is part of the measurement: the same tree read with and without `--label-pattern` does not produce
the same counts, and the run without it is the loud one.

## GitHub Actions

```yaml
- run: pip install .
- run: test-ordinal-ratchet tests
```

A full workflow is in `.github/workflows/ratchet.yml`.

## How this is tested

53 tests, and a mutation audit of the tests themselves. A passing test says the code does what the
test asserts; it does not say the test would notice if the code stopped doing it, and a guard whose
removal no test notices is not a guard — it is a comment with a colour.

```bash
python tools/mutar.py
```

The harness holds **26 mutations**, each hoisting one promise out of `scanner.py` or `cli.py`: the
ordinal needs its underscore, `async def` is read, a class body is read, a repeated name in one scope
is a shadow, the label declaration is honoured in the ordinal pass, a frozen glob **and** a frozen
label pattern are both checked on read, a shadow can never be frozen into the baseline, two homonym
roots keep two keys. Every anchor must appear exactly once before anything is written; the package
and its tests are copied into a temporary directory and the suite runs there, so nothing touches the
checkout.

| RC | meaning |
| -- | -- |
| `0` | every mutation was killed |
| `1` | at least one survived — it names the promise that has no falsifier |
| `2` | the harness cannot measure: an anchor is missing or is not unique |

The first run left **8** of 26 alive: 4 were the harness's own anchors landing on a missing or
duplicated line, and **4 were real holes** — a `testcase` name (pytest collects `test*`, not
`test_*`) was never read as a definition, the set-aside list was ordered by name instead of by
locus, two set-aside names in one file collapsed into one term, and a baseline frozen over two globs
was tied to the order they were declared in. Repairing the anchors then exposed two more: one mutant
only rewrote an error message instead of the `rc = 1` that emits it, and one file carrying both a
ratcheted and an unratcheted count leaked the unratcheted one into the frozen baseline. One
falsifier per hole, and one strengthened to a file that carries both kinds of debt:

```
26 mutations · 26 killed · 0 survived
```

`tools/` is not part of the installed package: this is the audit of the repository, not a feature of
the wheel.

## Declared limits

- It **does not execute** anything: it reads definitions from the AST.
- One file is one universe. Cross-file scope, plugins that rewrite collection, and dynamic binding
  beyond plain `def`/`class` nesting are out of scope.
- Numbers are recognized only as a `test_` prefix followed by digits (`test_36_x`); `test_case_36`
  is not an ordinal. A number that is a **label** and not a sequence is charged unless the repository
  declares it with `--label-pattern`; the flag is a declaration, not a detector, and three shapes
  (`test_20643_comment`, `test_32878_complex_itemsize`, `test_1000_sep_…`) are syntactically
  identical to sequence ordinals and can only be frozen in the baseline. The `ordinal` counter is a
  ratchet on a heuristic, not a proof.
- A file that does not parse is reported as **not measured** and the rest is read;
  `--strict-syntax` restores the all-or-nothing refusal. Either way it is never a silent zero.
- **Fixtures are not covered, and measured they do not need to be**: across the seventeen
  repositories above, 2 437 `test_*.py` and `conftest.py` files hold **zero** cases of two same-named
  definitions in one scope where at least one is a `@pytest.fixture`. Overriding a fixture from
  `conftest.py` inside a module is legal and would be a false positive, not a defect.
- **A definition inside a control-flow block is not read.** `if`/`try`/`for`/`while`/`with` bodies are
  skipped, and so is anything nested inside a function body, so a test that exists only under a
  condition is invisible here rather than guessed at. This was measured before being formalized:
  **0 of 14 022** `test*` definitions at module or class level — 5 378 in the 320-file corpus, 8 644
  across the five latest repositories — live inside such a block. If yours does, the guard belongs at
  the branch, not in the name.
- `shadow` reports the **last** binding and the line of the first one it overwrites.
- **A half-read file is named, and its blind spot is bounded.** When `--label-pattern` takes some
  names out of a file's ordinal space and leaves others in, an ordinal reused across the declaration
  (`test_2_x` against `test_2d_plot`) is invisible there by construction: one side is not read. The
  census in `--json` says which files those are and how the space splits; measured across
  `scikit-learn` (0), `pandas` (1: `test_sas7bdat.py`), `airflow` (0) and `aiohttp` (0), the
  cross-overlap is **0**. The declaration is the repository's own statement that those numbers are
  not a sequence, so the crossing is not charged — it is declared instead of being silent.
- **The ledger counts, it does not keep identity.** Each class is a number per file, so a change
  that fixes one ordinal collision and introduces another **in the same file** nets to zero and is
  not charged. Measured rather than assumed: over 58 real commit transitions (`scikit-learn`
  `--depth 40`, `pandas` `--depth 20`, 2026-11-25) touching 10 debt-bearing files, the event fired
  **0 times**. Recording each colliding number would charge every renumbering as new debt — a false
  red traded for a false green nobody has observed. Declared, not built.
- Baseline keys are argument-relative: scanning `../other/tests` and `tests` from different
  directories produces different keys. Freeze the baseline from the directory you will run from.
  The globs and the label pattern **are** recorded, so reading across either is `RC 2`; the roots
  are not, so two runs that reach the same file from different arguments still share a key.
  When two arguments would produce the same relative key (`a/tests/test_x.py` and
  `b/tests/test_x.py`), each key is prefixed with the argument it came from, so both files are
  measured; the same file reached twice is measured once. Keying on the relative path alone silently
  dropped the second file — collisions included.

## License

MIT — see `LICENSE`.

## Field notes

This repository belongs to an audit corpus whose measurements are published as
field notes. Two of them come from the same work:

- [Encontré 2 bugs reales en Django y decidí no reportarlos. La razón es más interesante que el bug.](https://dev.to/alexisromtz7/encontre-2-bugs-reales-en-django-y-decidi-no-reportarlos-la-razon-es-mas-interesante-que-el-bug-3b7n)
- [My falsifier was measuring my laptop](https://dev.to/alexisromtz7/my-falsifier-was-measuring-my-laptop-499p)
