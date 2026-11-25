"""The reader and its ratchet: silent shadow, ordinal per scope, shared ordinal."""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ordinal_ratchet import cli, scanner  # noqa: E402

# Real case (measured when merging two branches of a 319-bank corpus): two
# different classes of the same file both declare `test_36`. Legal: both run.
LAW_WITH_SHARED_ORDINAL = """
import unittest


class ThePredicate(unittest.TestCase):
    def test_36_debt_that_runs_long_goes_red(self):
        pass


class TheWindow(unittest.TestCase):
    def test_36_the_window_does_not_charge_the_simulation(self):
        pass
"""

LAW_WITH_ORDINAL_IN_ONE_SCOPE = """
class Codes:
    def test_1_the_lock_wins(self):
        pass

    def test_1_lock_without_a_single_citation(self):
        pass
"""

LAW_WITH_SHADOW = """
class TheWindow:
    def test_36_a(self):
        pass

    def test_36_a(self):
        pass
"""

# Measured in Django: `400` is an HTTP status code, not the 400th test.
LAW_WITH_HTTP_CODE_LABELS = """
class TestDebug:
    def test_400_bad_request(self):
        pass

    def test_400_empty_body(self):
        pass

    def test_36_the_real_sequence(self):
        pass

    def test_36_also_the_real_sequence(self):
        pass
"""

LAW_WITH_SHADOW_INSIDE_LABELS = """
class TestDebug:
    def test_404_missing(self):
        pass

    def test_404_missing(self):
        pass
"""

# `async def test_x` parses to ast.AsyncFunctionDef, a different node type from
# ast.FunctionDef. It is the same kind of definition: measured over five
# async-heavy suites, 2 404 of 8 660 test definitions are `async def`.
LAW_WITH_ASYNC_COLLISIONS = """
async def test_7_streams():
    pass


async def test_7_streams_again():
    pass


def test_3_sync():
    pass


async def test_3_async():
    pass


class TestClient:
    async def test_9_connect(self):
        pass

    async def test_9_connect(self):
        pass
"""


def _write(root: Path, rel: str, text: str) -> Path:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


def _run(argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        rc = cli.main(argv)
    return rc, out.getvalue()


class TheReaderSeesTheShadowAndTheOrdinal(unittest.TestCase):
    def test_a_repeated_name_in_the_same_scope_is_shadow(self) -> None:
        cols = scanner.collisions(scanner.definitions(LAW_WITH_SHADOW, "law.py"))
        self.assertEqual([c.kind for c in cols], [scanner.SHADOW])
        self.assertEqual(cols[0].first, 3)

    def test_the_same_name_in_different_classes_is_not_shadow(self) -> None:
        source = """
class A:
    def test_something(self):
        pass


class B:
    def test_something(self):
        pass
"""
        self.assertEqual(scanner.collisions(scanner.definitions(source, "law.py")), [])

    def test_two_names_sharing_an_ordinal_in_one_scope_is_ordinal(self) -> None:
        cols = scanner.collisions(scanner.definitions(LAW_WITH_ORDINAL_IN_ONE_SCOPE, "law.py"))
        self.assertEqual([c.kind for c in cols], [scanner.ORDINAL])
        self.assertEqual(cols[0].scope, "Codes")
        self.assertEqual((cols[0].line, cols[0].first), (6, 3))

    def test_the_same_ordinal_in_two_classes_is_counted_but_not_ordinal(self) -> None:
        cols = scanner.collisions(scanner.definitions(LAW_WITH_SHARED_ORDINAL, "law.py"))
        self.assertEqual([c.kind for c in cols], [scanner.SHARED])

    def test_a_name_inside_a_docstring_defines_nothing(self) -> None:
        source = '''
"""def test_36_fake(): pass
def test_36_also_fake(): pass
"""


def test_1_real():
    pass
'''
        self.assertEqual(scanner.collisions(scanner.definitions(source, "law.py")), [])

    def test_shadow_and_ordinal_are_not_counted_twice_over_the_same_pair(self) -> None:
        tally = scanner.count(scanner.collisions(scanner.definitions(LAW_WITH_SHADOW, "law.py")))
        self.assertEqual(tally, {"shadow": 1, "ordinal": 0, "shared": 0})

    def test_a_file_that_does_not_parse_is_unreadable_not_zero(self) -> None:
        _cols, unreadable, _labels = scanner.scan({"law.py": "def test_1(:\n"})
        self.assertEqual([u.path for u in unreadable], ["law.py"])
        self.assertIsNotNone(unreadable[0].lineno)

    def test_a_label_pattern_takes_the_number_out_of_the_ordinal_pass(self) -> None:
        defs = scanner.definitions(LAW_WITH_HTTP_CODE_LABELS, "law.py")
        loose = scanner.count(scanner.collisions(defs))
        tight = scanner.count(scanner.collisions(defs, re.compile(r"^test_[1-5]\d\d_")))
        self.assertEqual(loose["ordinal"], 2)
        self.assertEqual(tight["ordinal"], 1)
        self.assertEqual(
            scanner.labels_set_aside(defs, re.compile(r"^test_[1-5]\d\d_")),
            ["test_400_bad_request", "test_400_empty_body"],
        )

    def test_a_label_pattern_never_reaches_the_shadow_pass(self) -> None:
        defs = scanner.definitions(LAW_WITH_SHADOW_INSIDE_LABELS, "law.py")
        cols = scanner.collisions(defs, re.compile(r"^test_[1-5]\d\d_"))
        self.assertEqual([c.kind for c in cols], [scanner.SHADOW])

    def test_an_async_definition_collides_like_a_plain_one(self) -> None:
        defs = scanner.definitions(LAW_WITH_ASYNC_COLLISIONS, "law.py")
        self.assertEqual(len(defs), 6)
        cols = scanner.collisions(defs)
        self.assertEqual(
            sorted((c.kind, c.name) for c in cols),
            [
                (scanner.ORDINAL, "test_3_async"),
                (scanner.ORDINAL, "test_7_streams_again"),
                (scanner.SHADOW, "test_9_connect"),
            ],
        )
        self.assertEqual(sorted({c.scope for c in cols}), ["TestClient", "module"])

    def test_an_async_shadow_is_rc_1_and_names_the_line_it_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "tests/test_a.py", LAW_WITH_ASYNC_COLLISIONS)
            rc, out = _run([str(root), "--baseline", str(root / ".ordinal-ratchet.json")])
        self.assertEqual(rc, 1, out)
        self.assertIn("TestClient.test_9_connect overwrites the definition at :", out)


class TheRatchetBites(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.baseline = self.root / ".ordinal-ratchet.json"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _argv(self):
        return [str(self.root), "--baseline", str(self.baseline)]

    def test_a_clean_tree_is_rc_0(self) -> None:
        _write(self.root, "tests/test_a.py", "def test_1_a():\n    pass\n")
        rc, out = _run(self._argv())
        self.assertEqual(rc, 0, out)
        self.assertIn("shadow 0", out)

    def test_an_ordinal_over_an_empty_baseline_is_rc_1(self) -> None:
        _write(self.root, "tests/test_a.py", LAW_WITH_ORDINAL_IN_ONE_SCOPE)
        rc, out = _run(self._argv())
        self.assertEqual(rc, 1, out)
        self.assertIn("UP", out)
        self.assertIn("reuses the ordinal of the definition at", out)

    def test_a_missing_baseline_says_so_instead_of_calling_it_a_regression(self) -> None:
        _write(self.root, "tests/test_a.py", LAW_WITH_ORDINAL_IN_ONE_SCOPE)
        rc, out = _run(self._argv())
        self.assertEqual(rc, 1, out)
        self.assertIn("no baseline at", out)
        self.assertIn("no baseline to ratchet against", out)
        self.assertNotIn("files go up", out)

        rc, out = _run(self._argv() + ["--json"])
        self.assertFalse(json.loads(out)["baseline_present"])

    def test_a_shared_ordinal_does_not_fail_unless_strict(self) -> None:
        _write(self.root, "tests/test_a.py", LAW_WITH_SHARED_ORDINAL)
        rc, out = _run(self._argv())
        self.assertEqual(rc, 0, out)
        self.assertIn("shared 1", out)
        rc, out = _run(self._argv() + ["--strict"])
        self.assertEqual(rc, 1, out)

    def test_the_shared_detail_does_not_drown_the_verdict(self) -> None:
        _write(self.root, "tests/test_a.py", LAW_WITH_SHARED_ORDINAL)
        _rc, out = _run(self._argv())
        self.assertIn("shared 1", out)
        self.assertIn("--detail lists them", out)
        self.assertNotIn("legal: no test stops running", out)
        _rc, out = _run(self._argv() + ["--detail"])
        self.assertIn("legal: no test stops running", out)

    def test_the_default_output_only_shows_what_is_charged(self) -> None:
        _write(self.root, "tests/test_a.py", LAW_WITH_ORDINAL_IN_ONE_SCOPE)
        _run(self._argv() + ["--write-baseline"])
        rc, out = _run(self._argv())
        self.assertEqual(rc, 0, out)
        self.assertIn("ordinal 1", out)
        self.assertNotIn("reuses the ordinal of the definition at", out)
        self.assertIn("--detail lists them", out)
        _rc, out = _run(self._argv() + ["--detail"])
        self.assertIn("reuses the ordinal of the definition at", out)

    def test_a_frozen_baseline_absolves_inherited_debt(self) -> None:
        _write(self.root, "tests/test_a.py", LAW_WITH_ORDINAL_IN_ONE_SCOPE)
        rc, _ = _run(self._argv() + ["--write-baseline"])
        self.assertEqual(rc, 0)
        debt = json.loads(self.baseline.read_text(encoding="utf-8"))["debt"]
        self.assertEqual(debt["tests/test_a.py"]["ordinal"], 1)
        rc, out = _run(self._argv())
        self.assertEqual(rc, 0, out)

    def test_a_new_collision_over_the_baseline_is_rc_1(self) -> None:
        _write(self.root, "tests/test_a.py", LAW_WITH_ORDINAL_IN_ONE_SCOPE)
        _run(self._argv() + ["--write-baseline"])
        _write(self.root, "tests/test_b.py", LAW_WITH_SHADOW)
        rc, out = _run(self._argv())
        self.assertEqual(rc, 1, out)
        self.assertIn("tests/test_b.py", out)

    def test_a_resolved_debt_still_declared_is_rc_1(self) -> None:
        _write(self.root, "tests/test_a.py", LAW_WITH_ORDINAL_IN_ONE_SCOPE)
        _run(self._argv() + ["--write-baseline"])
        _write(self.root, "tests/test_a.py", "def test_36_only():\n    pass\n")
        rc, out = _run(self._argv())
        self.assertEqual(rc, 1, out)
        self.assertIn("ZOMBIE", out)

    def test_no_test_files_is_rc_2(self) -> None:
        rc, out = _run(self._argv())
        self.assertEqual(rc, 2, out)

    def test_a_file_that_does_not_parse_is_rc_2(self) -> None:
        _write(self.root, "tests/test_a.py", "def test_1(:\n")
        rc, out = _run(self._argv())
        self.assertEqual(rc, 2, out)

    def test_a_file_that_does_not_parse_does_not_blind_the_others(self) -> None:
        _write(self.root, "tests/test_a.py", "def test_1(:\n")
        _write(self.root, "tests/test_b.py", LAW_WITH_SHADOW)
        rc, out = _run(self._argv())
        self.assertEqual(rc, 1, out)
        self.assertIn("tests/test_b.py", out)
        self.assertIn("1 of 2 files did not parse", out)

    def test_an_unparsed_file_keeps_its_debt_instead_of_freeing_it(self) -> None:
        _write(self.root, "tests/test_a.py", LAW_WITH_ORDINAL_IN_ONE_SCOPE)
        _write(self.root, "tests/test_b.py", "def test_1_b():\n    pass\n")
        _run(self._argv() + ["--write-baseline"])
        _write(self.root, "tests/test_a.py", "def test_1(:\n")
        rc, out = _run(self._argv())
        self.assertEqual(rc, 0, out)
        self.assertNotIn("ZOMBIE", out)
        self.assertIn("1 of 2 files did not parse", out)

    def test_strict_syntax_refuses_an_unparsed_file(self) -> None:
        _write(self.root, "tests/test_a.py", "def test_1_a():\n    pass\n")
        _write(self.root, "tests/test_b.py", "def test_1(:\n")
        rc, out = _run(self._argv() + ["--strict-syntax"])
        self.assertEqual(rc, 2, out)

    def test_a_baseline_is_not_frozen_over_an_incomplete_universe(self) -> None:
        _write(self.root, "tests/test_a.py", "def test_1_a():\n    pass\n")
        _write(self.root, "tests/test_b.py", "def test_1(:\n")
        rc, out = _run(self._argv() + ["--write-baseline"])
        self.assertEqual(rc, 2, out)
        self.assertFalse(self.baseline.exists())
        self.assertIn("incomplete universe", out)

    def test_json_declares_how_many_files_were_read(self) -> None:
        _write(self.root, "tests/test_a.py", "def test_1_a():\n    pass\n")
        _write(self.root, "tests/test_b.py", "def test_1(:\n")
        rc, out = _run(self._argv() + ["--json"])
        self.assertEqual(rc, 0, out)
        data = json.loads(out)
        self.assertEqual((data["files"], data["parsed"]), (2, 1))
        unparsed = data["unparsed"]
        self.assertEqual([u["path"] for u in unparsed], ["tests/test_b.py"])
        self.assertEqual(unparsed[0]["lineno"], 1)
        self.assertIn("syntax", unparsed[0]["reason"])

    def test_a_label_pattern_silences_the_status_code_noise_and_says_so(self) -> None:
        _write(self.root, "tests/test_a.py", LAW_WITH_HTTP_CODE_LABELS)
        _rc, out = _run(self._argv())
        self.assertIn("ordinal 2", out)

        argv = self._argv() + ["--label-pattern", r"^test_[1-5]\d\d_"]
        rc, out = _run(argv)
        self.assertEqual(rc, 1, out)
        self.assertIn("ordinal 1", out)
        self.assertIn("2 test names set aside by --label-pattern", out)

        _rc, out = _run(argv + ["--detail"])
        self.assertIn("LABEL test_400_bad_request", out)
        data = json.loads(_run(argv + ["--json"])[1])
        self.assertEqual(len(data["labels_set_aside"]), 2)

    def test_a_shadow_inside_the_label_space_is_still_charged(self) -> None:
        _write(self.root, "tests/test_a.py", LAW_WITH_SHADOW_INSIDE_LABELS)
        rc, out = _run(self._argv() + ["--label-pattern", r"^test_[1-5]\d\d_"])
        self.assertEqual(rc, 1, out)
        self.assertIn("overwrites the definition at", out)

    def test_a_malformed_label_pattern_is_rc_2(self) -> None:
        _write(self.root, "tests/test_a.py", LAW_WITH_HTTP_CODE_LABELS)
        rc, out = _run(self._argv() + ["--label-pattern", "test_("])
        self.assertEqual(rc, 2, out)
        self.assertIn("is not a regex", out)

    def test_json_carries_the_counts_and_the_rc(self) -> None:
        _write(self.root, "tests/test_a.py", LAW_WITH_SHARED_ORDINAL)
        rc, out = _run(self._argv() + ["--json"])
        self.assertEqual(rc, 0, out)
        data = json.loads(out)
        self.assertEqual(data["total"], {"shadow": 0, "ordinal": 0, "shared": 1})
        self.assertEqual(data["rc"], 0)
        self.assertEqual(data["collisions"][0]["name"], "ordinal 36 in 2 scopes")

    def test_two_roots_sharing_a_relative_key_are_both_measured(self) -> None:
        _write(self.root, "a/tests/test_x.py", "def test_1_x():\n    pass\n")
        _write(self.root, "b/tests/test_x.py", LAW_WITH_ORDINAL_IN_ONE_SCOPE)
        here = os.getcwd()
        os.chdir(self.root)
        try:
            files, missing = cli._collect(["a/tests", "b/tests"], "test_*.py")
        finally:
            os.chdir(here)
        self.assertEqual(missing, [])
        self.assertEqual([key for key, _ in files], ["a/tests/test_x.py", "b/tests/test_x.py"])

    def test_the_second_root_is_charged_instead_of_disappearing(self) -> None:
        _write(self.root, "a/tests/test_x.py", "def test_1_x():\n    pass\n")
        _write(self.root, "b/tests/test_x.py", LAW_WITH_ORDINAL_IN_ONE_SCOPE)
        roots = [str(self.root / "a" / "tests"), str(self.root / "b" / "tests")]
        rc, out = _run(roots + ["--baseline", str(self.baseline), "--json"])
        self.assertEqual(rc, 1, out)
        data = json.loads(out)
        self.assertEqual(data["files"], 2)
        self.assertEqual(data["total"]["ordinal"], 1)

    def test_the_same_file_reached_twice_is_measured_once(self) -> None:
        _write(self.root, "tests/test_a.py", LAW_WITH_ORDINAL_IN_ONE_SCOPE)
        here = os.getcwd()
        os.chdir(self.root)
        try:
            files, _missing = cli._collect(["tests", "./tests", "tests/test_a.py"], "test_*.py")
        finally:
            os.chdir(here)
        self.assertEqual([key for key, _ in files], ["test_a.py"])


if __name__ == "__main__":
    unittest.main()
