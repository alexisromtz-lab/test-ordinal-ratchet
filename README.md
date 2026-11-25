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
```

(Not on PyPI yet, so `uvx test-ordinal-ratchet` does not resolve. `pip install .` and
`python -m ordinal_ratchet` work today.)

## Output contract

| RC | meaning |
|---|---|
| `0` | nothing increased over the declared baseline (which may be zero) |
| `1` | a **new** collision, a counter above the baseline, or declared debt that no longer exists |
| `2` | invalid usage · **no** test file matched · nothing at all parses · `--strict-syntax` and a file does not parse |

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

The loss is also named, per file, with the line that stopped the parser:

```console
$ test-ordinal-ratchet tests --detail
  NOT MEASURED tests/test_structural_pattern_matching.py (line 11: invalid syntax)
```

`--json` carries the same rows as objects, so nothing has to be recovered from a string:

```json
"unparsed": [{"path": "tests/test_structural_pattern_matching.py", "lineno": 11, "reason": "invalid syntax"}]
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
$ test-ordinal-ratchet tests --label-pattern '^test_\d+[a-zA-Z]'
```

Rows set aside are counted and printable, so nothing is silently discarded:

```console
test-ordinal-ratchet: 260 files · shadow 0 · ordinal 0 · shared 0
  (15 test names set aside by --label-pattern `^test_\d+[a-zA-Z]`: their number is a label, not a sequence ordinal; --detail lists them)
RC 0: no new collisions over .ordinal-ratchet.json, on 260 of 260 files read
```

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
whatever the pattern claims, and that is tested.

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

### Flags

| flag | effect |
|---|---|
| `--baseline PATH` | baseline file (default `.ordinal-ratchet.json` in the cwd) |
| `--write-baseline` | freeze the current counts as inherited debt |
| `--label-pattern REGEX` | tests whose **name** matches are not read as sequence ordinals (never affects `shadow`) |
| `--detail` | list every row, including the ones that are not charged |
| `--strict` | also fail (`RC 1`) when two scopes of one file reuse a number |
| `--strict-syntax` | fail (`RC 2`) when any file does not parse, instead of reading the rest |
| `--json` | machine-readable output: counts, every collision, `ups`/`zombies`, `unreadable`, `labels_set_aside`, `rc` |
| `--pattern GLOB` | file glob (default `test_*.py`) |

## The ratchet

A baseline of inherited debt, keyed by path **relative to the argument you scanned**, so it survives
cloning and moving:

```json
{
  "version": 1,
  "pattern": "test_*.py",
  "debt": {
    "tests/test_startup_order.py": {"ordinal": 2, "shadow": 0}
  }
}
```

The ratchet turns one way: the declared count **may go down, never up**. And it charges the opposite
error too — a declared entry that no longer exists is a `zombie`, `RC 1`:

```
ZOMBIE tests/test_startup_order.py: ordinal -2 (the debt no longer exists: remove it from the baseline)
```

A debt list nobody prunes stops being evidence. That is why shrinking is legal but lying is not.

## Real-world audit

Seventeen well-known suites, shallow clone of the default branch, 2026-11-25. Scanned directory is
`tests/` when the repository has it, the repository root otherwise:

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

| repository | test files | shadow | ordinal (raw) | ordinal (labels declared) |
|---|---|---|---|---|
| `apache/airflow` | 2 412 | 0 | 5 | **1** |
| `saleor/saleor` | 1 236 | 0 | 0 | 0 |
| `pandas-dev/pandas` | 994 | 0 | 15 | **3** |
| `ansible/ansible` | 367 | 0 | 0 | 0 |
| `scikit-learn/scikit-learn` | 260 | 0 | 7 | 0 |
| **total** | **5 269** | **0** | **27** | **4** |

**7 682 files**, two silent lost tests, both in the same file of the same project. The `ordinal`
column is where the honest problems are: of the **27** rows the heuristic charges across those five
large suites, 23 have a shape a declared pattern can name, **1** is a genuinely reused ordinal
(`airflow`'s `test_7_…` at `:849` and `:890`), and **3** are numbers that look exactly like sequence
ordinals and are not — `pandas`' `test_20643_comment`, `test_32878_complex_itemsize` and
`test_1000_sep_not_stripped_after_whitespace`.

`sqlalchemy` is the row that justifies the unparseable-file granularity: four of its files do not
parse because they use syntax newer than the interpreter (`test_tstring_py314.py` is Python 3.14
t-strings). Before that change it was `RC 2` over the whole repository — a 239-file audit refused
because of files that are not even code for the interpreter running them.

The two interpreters agree on every collision and disagree on coverage: run on 3.9.6 the same
repositories lose **8** files (django 2, pydantic 2, sqlalchemy 4) and every count above is
unchanged. Point the tool at the interpreter the project targets; when you cannot, the loss is
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

## pre-commit

The hook ships in `.pre-commit-hooks.yaml`, so it installs from the repository itself — no PyPI
needed:

```yaml
repos:
  - repo: https://github.com/alexisromtz-lab/test-ordinal-ratchet
    rev: v0.1.1
    hooks:
      - id: test-ordinal-ratchet
        args: ["tests", "--label-pattern", '^test_\d+[a-zA-Z]']
```

`pass_filenames` is **false** on purpose. pre-commit would otherwise hand the hook the staged files,
which shrinks the universe: the ratchet compares a partial read against a whole-repository baseline
and reports resolved debt that was never looked at. The subject of this tool is the repository, so
the hook triggers on a Python change and then reads everything.

Keep the flag — and the declared labels — in the configuration that runs the check. The declaration
is part of the measurement: the same tree read with and without `--label-pattern` does not produce
the same counts, and the run without it is the loud one.

## GitHub Actions

```yaml
- run: pip install .
- run: test-ordinal-ratchet tests
```

A full workflow is in `.github/workflows/ratchet.yml`.

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
- `shadow` reports the **last** binding and the line of the first one it overwrites.
- Baseline keys are argument-relative: scanning `../other/tests` and `tests` from different
  directories produces different keys. Freeze the baseline from the directory you will run from.

## License

MIT — see `LICENSE`.
