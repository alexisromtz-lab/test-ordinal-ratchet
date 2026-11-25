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
| `--detail` | list every row, including the ones that are not charged |
| `--strict` | also fail (`RC 1`) when two scopes of one file reuse a number |
| `--strict-syntax` | fail (`RC 2`) when any file does not parse, instead of reading the rest |
| `--json` | machine-readable output: counts, every collision, `ups`/`zombies`, `rc` |
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

Twelve well-known suites, shallow clone of the default branch, 2026-11-25. Scanned directory is
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
| `Textualize/rich` | 63 | 0 | **2** | 0 | 0 | 1 |
| `pallets/click` | 43 | 0 | 0 | 0 | 0 | 0 |
| `encode/starlette` | 31 | 0 | 0 | 0 | 0 | 0 |
| `pallets/flask` | 22 | 0 | 0 | 0 | 0 | 0 |
| `psf/black` | 14 | 0 | 0 | 0 | 0 | 0 |

2 255 files, two silent lost tests, and both of them are in the same file of the same project. An
earlier pass over three more suites — `psf/requests` 9, `encode/httpx` 31, `pytest-dev/pytest` 118 —
found nothing either; 2 413 files in total.

`sqlalchemy` is the row that justifies the granularity: four of its files do not parse because they
use syntax newer than the interpreter (`test_tstring_py314.py` is Python 3.14 t-strings). Before this
change that was `RC 2` over the whole repository — a 239-file audit refused because of files that are
not even code for the interpreter running them.

The two interpreters agree on every collision and disagree on coverage: run on 3.9.6 the same twelve
repositories lose **8** files (django 2, pydantic 2, sqlalchemy 4) and every count above is
unchanged. Point the tool at the interpreter the project targets; when you cannot, the loss is
declared instead of swallowed.

`django`'s five `ordinal` rows are the honest false positive: `400`, `403` and `404` are HTTP status
codes, not sequence numbers, and they still share a `test_` prefix followed by digits. The finding is
literally true — `-k test_404` matches two tests and disambiguates neither — but reading them as
collisions of a sequence is wrong. Freeze the baseline: the ratchet then blocks a **new** reuse,
which is the actual contract.

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
  is not an ordinal. A number that is a **label** and not a sequence is still counted: `django`'s
  `test_400_*` (HTTP status) shares `400`, so `-k test_400` is ambiguous — true, but not the defect
  this tool ratchets. The `ordinal` counter is a ratchet on a heuristic, not a proof.
- A file that does not parse is reported as **not measured** and the rest is read;
  `--strict-syntax` restores the all-or-nothing refusal. Either way it is never a silent zero.
- **Fixtures are not covered, and measured they do not need to be**: across the twelve repositories
  above, 2 437 `test_*.py` and `conftest.py` files hold **zero** cases of two same-named definitions
  in one scope where at least one is a `@pytest.fixture`. Overriding a fixture from `conftest.py`
  inside a module is legal and would be a false positive, not a defect.
- `shadow` reports the **last** binding and the line of the first one it overwrites.
- Baseline keys are argument-relative: scanning `../other/tests` and `tests` from different
  directories produces different keys. Freeze the baseline from the directory you will run from.

## License

MIT — see `LICENSE`.
