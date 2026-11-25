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
test-ordinal-ratchet: 319 files · shadow 0 · ordinal 39 · shared 57
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
| `2` | invalid usage · **no** test file matched · a file that does not parse |

`RC 2` exists so that absence of subject is never read as zero: if the glob finds nothing, or a file
does not parse, there is no measurement and the tool refuses to say "clean".

By default only the rows that justify the RC are printed, plus one line with the totals. That is
deliberate: a legacy suite can carry dozens of legal `shared` ordinals, and printing them on every
run buries the verdict.

```
test-ordinal-ratchet: 319 files · shadow 0 · ordinal 39 · shared 57
  (39 ordinal entries inherited inside their baseline: not charged; --detail lists them)
  (57 shared ordinals across scopes: legal, no test is lost; --detail lists them, --strict charges them)
RC 0: no new collisions over .ordinal-ratchet.json
```

With **no** baseline file the ratchet has nothing to ratchet against, so every measured `ordinal` is
charged and the run exits `1` — the safe direction. The output says so instead of calling it a
regression, and `--write-baseline` freezes the debt in one step:

```
test-ordinal-ratchet: 319 files · shadow 0 · ordinal 39 · shared 57
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

Five well-known suites, shallow clone of the default branch, 2026-11-25, Python 3.9.6:

| repository | test files | shadow | ordinal | shared | RC |
|---|---|---|---|---|---|
| `psf/requests` | 9 | 0 | 0 | 0 | 0 |
| `encode/httpx` | 31 | 0 | 0 | 0 | 0 |
| `pytest-dev/pytest` | 118 | 0 | 0 | 0 | 0 |
| `Textualize/rich` | 63 | **2** | 0 | 0 | 1 |
| `pydantic/pydantic` | — | — | — | — | 2 |

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

`pydantic` exits `RC 2` because its suites use `match` statements (3.10+) and the interpreter running
the scan was 3.9: the tool refuses to report as "clean" what it could not parse. Run it under the
interpreter your project targets.

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
  is not an ordinal.
- A file that does not parse is `RC 2`, never a silent zero.
- `shadow` reports the **last** binding and the line of the first one it overwrites.
- Baseline keys are argument-relative: scanning `../other/tests` and `tests` from different
  directories produces different keys. Freeze the baseline from the directory you will run from.

## License

MIT — see `LICENSE`.
