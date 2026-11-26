"""The reader and its ratchet: silent shadow, ordinal per scope, shared ordinal."""

from __future__ import annotations

import contextlib
import importlib.metadata as metadata
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
import ordinal_ratchet  # noqa: E402

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

    def test_a_test_prefixed_name_without_underscore_is_still_a_shadow(self) -> None:
        # pytest collects `test*`, not `test_*`: `testcase` twice is one test that
        # stops running, while RE_ORDINAL never sees it because it carries no number.
        source = "\ndef testcase():\n    pass\n\n\ndef testcase():\n    pass\n"
        cols = scanner.collisions(scanner.definitions(source, "law.py"))
        self.assertEqual([(c.kind, c.name) for c in cols], [(scanner.SHADOW, "testcase")])

    def test_shadow_and_ordinal_are_not_counted_twice_over_the_same_pair(self) -> None:
        tally = scanner.count(scanner.collisions(scanner.definitions(LAW_WITH_SHADOW, "law.py")))
        self.assertEqual(tally, {"shadow": 1, "ordinal": 0, "shared": 0})

    def test_a_file_that_does_not_parse_is_unreadable_not_zero(self) -> None:
        _cols, unreadable, _aside, census = scanner.scan({"law.py": "def test_1(:\n"})
        self.assertEqual([u.path for u in unreadable], ["law.py"])
        self.assertIsNotNone(unreadable[0].lineno)
        self.assertEqual(census, [])

    def test_a_label_pattern_takes_the_number_out_of_the_ordinal_pass(self) -> None:
        defs = scanner.definitions(LAW_WITH_HTTP_CODE_LABELS, "law.py")
        loose = scanner.count(scanner.collisions(defs))
        tight = scanner.count(scanner.collisions(defs, re.compile(r"^test_[1-5]\d\d_")))
        self.assertEqual(loose["ordinal"], 2)
        self.assertEqual(tight["ordinal"], 1)
        self.assertEqual(
            [d.name for d in scanner.labels_set_aside(defs, re.compile(r"^test_[1-5]\d\d_"))],
            ["test_400_bad_request", "test_400_empty_body"],
        )
        self.assertEqual(
            [d.line for d in scanner.labels_set_aside(defs, re.compile(r"^test_[1-5]\d\d_"))],
            [3, 6],
        )

    def test_set_aside_definitions_are_ordered_by_locus_not_by_name(self) -> None:
        source = "\ndef test_9_zulu():\n    pass\n\n\ndef test_1_alpha():\n    pass\n"
        aside = scanner.labels_set_aside(scanner.definitions(source, "law.py"), re.compile(r"^test_\d+_"))
        self.assertEqual([d.name for d in aside], ["test_9_zulu", "test_1_alpha"])
        self.assertEqual([d.line for d in aside], [2, 6])

    def test_a_label_pattern_never_reaches_the_shadow_pass(self) -> None:
        defs = scanner.definitions(LAW_WITH_SHADOW_INSIDE_LABELS, "law.py")
        cols = scanner.collisions(defs, re.compile(r"^test_[1-5]\d\d_"))
        self.assertEqual([c.kind for c in cols], [scanner.SHADOW])

    def test_two_set_aside_names_in_one_file_are_two_terms(self) -> None:
        source = "def test_1a():\n    pass\n\ndef test_2b():\n    pass\n\ndef test_3_c():\n    pass\n"
        census = scanner.label_census(scanner.definitions(source, "law.py"), re.compile(r"^test_\d+[a-z]"))
        self.assertEqual([(f.path, f.set_aside, f.read) for f in census], [("law.py", 2, 1)])

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

    def test_a_two_pattern_baseline_declares_both_globs(self) -> None:
        _write(self.root, "tests/test_a.py", LAW_WITH_ORDINAL_IN_ONE_SCOPE)
        _write(self.root, "tests/edge_test.py", LAW_WITH_ORDINAL_IN_ONE_SCOPE)
        rc, out = _run(
            self._argv() + ["--pattern", "test_*.py", "--pattern", "*_test.py", "--write-baseline"]
        )
        self.assertEqual(rc, 0, out)
        payload = json.loads(self.baseline.read_text(encoding="utf-8"))
        self.assertEqual(payload["pattern"], ["test_*.py", "*_test.py"])
        self.assertEqual(sorted(payload["debt"]), ["tests/edge_test.py", "tests/test_a.py"])

    def test_a_baseline_frozen_over_a_label_space_refuses_a_run_that_declares_none(
        self,
    ) -> None:
        _write(self.root, "tests/test_a.py", LAW_WITH_HTTP_CODE_LABELS)
        rc, out = _run(self._argv() + ["--label-pattern", r"^test_[1-5]\d\d_", "--write-baseline"])
        self.assertEqual(rc, 0, out)
        payload = json.loads(self.baseline.read_text(encoding="utf-8"))
        self.assertEqual(payload["label_pattern"], r"^test_[1-5]\d\d_")
        rc, out = _run(self._argv())
        self.assertEqual(rc, 2, out)
        self.assertIn("frozen with --label-pattern", out)
        self.assertIn("this run declares none", out)

    def test_a_baseline_frozen_without_a_label_space_refuses_a_run_that_sets_one(
        self,
    ) -> None:
        _write(self.root, "tests/test_a.py", LAW_WITH_HTTP_CODE_LABELS)
        rc, out = _run(self._argv() + ["--write-baseline"])
        self.assertEqual(rc, 0, out)
        rc, out = _run(self._argv() + ["--label-pattern", r"^test_[1-5]\d\d_"])
        self.assertEqual(rc, 2, out)
        self.assertIn("frozen with no --label-pattern", out)

    def test_the_same_label_space_reads_the_baseline_it_wrote(self) -> None:
        _write(self.root, "tests/test_a.py", LAW_WITH_HTTP_CODE_LABELS)
        _run(self._argv() + ["--label-pattern", r"^test_[1-5]\d\d_", "--write-baseline"])
        rc, out = _run(self._argv() + ["--label-pattern", r"^test_[1-5]\d\d_"])
        self.assertEqual(rc, 0, out)

    def test_a_baseline_frozen_over_two_globs_is_read_in_any_order(self) -> None:
        _write(self.root, "tests/test_a.py", LAW_WITH_ORDINAL_IN_ONE_SCOPE)
        rc, out = _run(self._argv() + ["--pattern", "test_*.py", "--pattern", "*_test.py", "--write-baseline"])
        self.assertEqual(rc, 0, out)
        rc, out = _run(self._argv() + ["--pattern", "*_test.py", "--pattern", "test_*.py"])
        self.assertEqual(rc, 0, out)

    def test_a_shared_ordinal_is_never_frozen_into_the_baseline(self) -> None:
        # A file that carries both kinds of debt is where the filter can leak: the
        # frozen row must hold the ratcheted term alone, never a count nothing charges.
        source = (
            "class Codes:\n"
            "    def test_3_a(self):\n"
            "        pass\n\n"
            "    def test_3_b(self):\n"
            "        pass\n\n\n"
            "class Other:\n"
            "    def test_7_x(self):\n"
            "        pass\n\n\n"
            "class Third:\n"
            "    def test_7_y(self):\n"
            "        pass\n"
        )
        _write(self.root, "tests/test_a.py", source)
        rc, out = _run(self._argv() + ["--write-baseline"])
        self.assertEqual(rc, 0, out)
        payload = json.loads(self.baseline.read_text(encoding="utf-8"))
        self.assertEqual(payload["debt"], {"tests/test_a.py": {"ordinal": 1}})

    def test_a_file_with_no_ratcheted_debt_is_not_written_at_all(self) -> None:
        _write(self.root, "tests/test_a.py", LAW_WITH_SHARED_ORDINAL)
        rc, out = _run(self._argv() + ["--write-baseline"])
        self.assertEqual(rc, 0, out)
        payload = json.loads(self.baseline.read_text(encoding="utf-8"))
        self.assertEqual(payload["debt"], {})

    def test_a_baseline_frozen_over_one_glob_refuses_to_be_read_over_another(self) -> None:
        _write(self.root, "tests/test_a.py", LAW_WITH_ORDINAL_IN_ONE_SCOPE)
        _write(self.root, "tests/edge_test.py", LAW_WITH_ORDINAL_IN_ONE_SCOPE)
        rc, out = _run(self._argv() + ["--write-baseline"])
        self.assertEqual(rc, 0, out)
        rc, out = _run(self._argv() + ["--pattern", "*_test.py"])
        self.assertEqual(rc, 2, out)
        self.assertIn("not comparable", out)
        self.assertIn("this run measures `*_test.py`", out)

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
        self.assertIn("2 test definitions set aside by --label-pattern", out)

        _rc, out = _run(argv + ["--detail"])
        self.assertIn("LABEL tests/test_a.py:", out)
        self.assertIn("test_400_bad_request", out)
        data = json.loads(_run(argv + ["--json"])[1])
        self.assertEqual(len(data["labels_set_aside"]), 2)

    def test_one_label_name_in_two_files_is_two_definitions_with_two_loci(self) -> None:
        _write(self.root, "tests/test_a.py", "def test_2d_plot():\n    pass\n")
        _write(self.root, "tests/test_b.py", "def test_2d_plot():\n    pass\n")
        argv = self._argv() + ["--label-pattern", r"^test_\d+[a-zA-Z]", "--json"]
        data = json.loads(_run(argv)[1])
        self.assertEqual(
            [(d["path"], d["lineno"], d["name"]) for d in data["labels_set_aside"]],
            [
                ("tests/test_a.py", 1, "test_2d_plot"),
                ("tests/test_b.py", 1, "test_2d_plot"),
            ],
        )

    def test_every_half_read_file_publishes_both_terms_of_its_ordinal_space(self) -> None:
        _write(
            self.root,
            "tests/test_a.py",
            "def test_1_a():\n    pass\n\ndef test_2d_plot():\n    pass\n\ndef test_3_b():\n    pass\n",
        )
        _write(self.root, "tests/test_b.py", "def test_2d_plot():\n    pass\n")
        argv = self._argv() + ["--label-pattern", r"^test_\d+[a-zA-Z]", "--json"]
        data = json.loads(_run(argv)[1])
        self.assertEqual(
            data["label_files"],
            [
                {"path": "tests/test_a.py", "set_aside": 1, "read": 2},
                {"path": "tests/test_b.py", "set_aside": 1, "read": 0},
            ],
        )
        rc, out = _run(self._argv() + ["--label-pattern", r"^test_\d+[a-zA-Z]", "--detail"])
        self.assertIn("HALF READ tests/test_a.py: 1 set aside, 2 read", out)

    def test_a_shadow_inside_the_label_space_is_still_charged(self) -> None:
        _write(self.root, "tests/test_a.py", LAW_WITH_SHADOW_INSIDE_LABELS)
        rc, out = _run(self._argv() + ["--label-pattern", r"^test_[1-5]\d\d_"])
        self.assertEqual(rc, 1, out)
        self.assertIn("overwrites the definition at", out)

    def test_a_second_pattern_is_measured_in_the_same_run(self) -> None:
        _write(self.root, "tests/test_a.py", LAW_WITH_ORDINAL_IN_ONE_SCOPE)
        _write(self.root, "tests/edge_test.py", LAW_WITH_SHADOW)
        rc, out = _run(self._argv() + ["--pattern", "test_*.py", "--pattern", "*_test.py"])
        self.assertEqual(rc, 1, out)
        self.assertIn("edge_test.py", out)

    def test_a_zero_names_the_sibling_convention(self) -> None:
        _write(self.root, "tests/edge_test.py", LAW_WITH_SHADOW)
        rc, out = _run(self._argv())
        self.assertEqual(rc, 2, out)
        self.assertIn("no file matches `test_*.py`", out)
        self.assertIn("1 file matches `*_test.py`", out)
        self.assertIn("add --pattern '*_test.py'", out)

    def test_files_outside_the_pattern_are_counted_not_swallowed(self) -> None:
        _write(self.root, "tests/test_a.py", LAW_WITH_SHARED_ORDINAL)
        _write(self.root, "tests/edge_test.py", LAW_WITH_SHADOW)
        rc, out = _run(self._argv())
        self.assertEqual(rc, 0, out)
        self.assertIn("note: 1 file matches `*_test.py` and were not read", out)
        rc, out = _run(self._argv() + ["--json"])
        data = json.loads(out)
        self.assertEqual(data["patterns"], ["test_*.py"])
        self.assertEqual(data["other_patterns"], {"*_test.py": ["tests/edge_test.py"]})

    def test_the_version_is_answerable_without_a_tree(self) -> None:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), self.assertRaises(SystemExit) as exit_:
            cli.main(["--version"])
        self.assertEqual(exit_.exception.code, 0)
        self.assertEqual(buf.getvalue().strip(), "test-ordinal-ratchet " + cli._VERSION)

    def test_a_baseline_never_absorbs_a_shadow(self) -> None:
        _write(self.root, "tests/test_a.py", LAW_WITH_SHADOW)
        rc, out = _run(self._argv() + ["--write-baseline"])
        self.assertEqual(rc, 1, out)
        self.assertIn("left out of the baseline", out)
        self.assertNotIn("shadow", json.loads(self.baseline.read_text("utf-8"))["debt"].get(
            "tests/test_a.py", {}))

        rc, out = _run(self._argv())
        self.assertEqual(rc, 1, out)
        self.assertIn("no baseline can absorb them", out)
        self.assertIn("overwrites the definition at", out)

    def test_shadow_debt_typed_into_the_baseline_by_hand_is_not_inherited(self) -> None:
        _write(self.root, "tests/test_a.py", LAW_WITH_SHADOW)
        self.baseline.write_text(
            json.dumps({"version": 1, "pattern": "test_*.py",
                        "debt": {"tests/test_a.py": {"shadow": 1, "ordinal": 0}}}),
            encoding="utf-8",
        )
        rc, out = _run(self._argv())
        self.assertEqual(rc, 1, out)
        self.assertIn("1 shadows", out)

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
            files, missing = cli._collect(["a/tests", "b/tests"], ["test_*.py"])
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
            files, _missing = cli._collect(["tests", "./tests", "tests/test_a.py"], ["test_*.py"])
        finally:
            os.chdir(here)
        self.assertEqual([key for key, _ in files], ["test_a.py"])


class ThePublishedIdentity(unittest.TestCase):
    """Two environments, both real: CI installs the package, so its metadata
    exists; a source checkout has none. Neither may answer with a number that is
    not the distribution's. A literal `0.1.0` sat in the module for four
    releases while `--version` said `0.2.5`, because nothing compared the two.
    """

    def _installed(self) -> str:
        try:
            return metadata.version("test-ordinal-ratchet")
        except metadata.PackageNotFoundError:
            return "0+unknown"

    def test_the_module_version_is_the_installed_one(self) -> None:
        self.assertEqual(ordinal_ratchet.__version__, self._installed())

    def test_the_cli_reports_the_module_version(self) -> None:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), self.assertRaises(SystemExit) as exit:
            cli.main(["--version"])
        self.assertEqual(exit.exception.code, 0)
        self.assertTrue(
            buffer.getvalue().strip().endswith(ordinal_ratchet.__version__),
            buffer.getvalue(),
        )


class TheCitationSurface(unittest.TestCase):
    """One fact, one value. A citation that names a different version than the
    distribution declares is the same defect that produced `v0.2.6`: a fact
    written in two places with nothing comparing them. Adding the citation
    surface adds a second place the version is written, so the reader that
    compares them ships in the same commit.
    """

    root = Path(__file__).resolve().parents[1]

    def _project_version(self) -> str:
        text = (self.root / "pyproject.toml").read_text(encoding="utf-8")
        match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
        self.assertIsNotNone(match, "pyproject.toml declares no version")
        return match.group(1)

    def _cff_scalar(self, key: str) -> str:
        text = (self.root / "CITATION.cff").read_text(encoding="utf-8")
        match = re.search(r"^%s:\s*(.+?)\s*$" % re.escape(key), text, re.MULTILINE)
        self.assertIsNotNone(match, "CITATION.cff has no `%s:`" % key)
        return match.group(1).strip().strip('"')

    def _zenodo(self) -> dict:
        return json.loads((self.root / ".zenodo.json").read_text(encoding="utf-8"))

    def test_the_citation_names_the_declared_version(self) -> None:
        declared = self._project_version()
        self.assertEqual(self._cff_scalar("version"), declared)
        self.assertEqual(self._zenodo()["version"], declared)

    def test_the_two_citation_surfaces_agree_on_the_title(self) -> None:
        self.assertEqual(self._cff_scalar("title"), self._zenodo()["title"])


if __name__ == "__main__":
    unittest.main()
