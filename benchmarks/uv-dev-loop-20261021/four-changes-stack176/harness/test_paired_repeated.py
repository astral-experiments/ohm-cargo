import contextlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import paired_repeated as repeated


class RepeatedRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        variants = {}
        for variant in ("baseline", "candidate"):
            binary = self.root / variant
            binary.write_text("#!/bin/sh\nexit 0\n")
            binary.chmod(0o755)
            variants[variant] = str(binary)
        self.configuration = {
            "cwd": str(self.root), "canonical_executable": str(self.root / "active" / "cargo"),
            "variants": variants, "command": ["{cargo}", "check"],
            "prepare_command": ["prepare-once"], "repetitions": 3, "repeatable_workload": "noop",
        }
        self.configuration_path = self.root / "config.json"
        self.configuration_path.write_text(json.dumps(self.configuration))
        self.output = self.root / "results"
        self.arguments = SimpleNamespace(config=str(self.configuration_path), output=str(self.output), phase="exploratory", pairs=2, warmup_pairs=0, seed=5)

    def tearDown(self):
        self.temporary.cleanup()

    @staticmethod
    def fake_command(command, cwd, environment, stdout, stderr):
        stdout.write_text("")
        stderr.write_text("    Finished dev profile\n")
        duration = 120 if environment.get("OHM_BENCH_VARIANT") == "baseline" else 100
        return {
            "returncode": 0, "wall_ns": duration,
            "user_seconds": duration / 1e6, "system_seconds": 1e-6,
            "minor_faults": 1, "major_faults": 0, "voluntary_context_switches": 1,
            "involuntary_context_switches": 0, "stdout": str(stdout), "stderr": str(stderr),
        }

    def test_groups_preserve_raw_subruns_without_pseudoreplication(self):
        with mock.patch.object(repeated.core, "run_command", side_effect=self.fake_command) as command, contextlib.redirect_stdout(io.StringIO()):
            repeated.run(self.arguments)
        samples = json.loads((self.output / "samples.json").read_text())
        subruns = json.loads((self.output / "subruns.json").read_text())
        self.assertEqual(command.call_count, 16)  # Four preparations + twelve timed commands.
        self.assertEqual(len(samples), 4)
        self.assertEqual(len(subruns), 12)
        self.assertEqual(len((self.output / "subruns.jsonl").read_text().splitlines()), 12)
        for sample in samples:
            self.assertEqual(sample["repetitions_completed"], 3)
            self.assertEqual(sample["wall_ns"], 360 if sample["variant"] == "baseline" else 300)
        analyze = SimpleNamespace(directory=str(self.output), confidence=.99, resamples=100, seed=1701, minimum_pairs=30, minimum_improvement=.01)
        with contextlib.redirect_stdout(io.StringIO()):
            repeated.analyze(analyze)
        result = json.loads((self.output / "analysis.json").read_text())
        self.assertEqual(result["pairs"], 2)
        self.assertEqual(result["grouping"]["measurement_group_pairs"], 2)
        self.assertEqual(result["grouping"]["measurement_subruns"], 12)
        self.assertEqual(result["exact_two_sided_sign_p"], .5)
        self.assertFalse(result["screen"]["passes"])
        self.assertEqual(len(result["repetition_position_seconds"]), 3)

    def test_failed_subrun_retains_partial_group(self):
        timed = 0
        def fail_second(command, cwd, environment, stdout, stderr):
            nonlocal timed
            result = self.fake_command(command, cwd, environment, stdout, stderr)
            if command != ["prepare-once"]:
                timed += 1
                if timed == 2:
                    result["returncode"] = 7
            return result
        with mock.patch.object(repeated.core, "run_command", side_effect=fail_second), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, "command failed"):
                repeated.run(self.arguments)
        samples = json.loads((self.output / "samples.json").read_text())
        self.assertEqual(samples[0]["repetitions_completed"], 2)
        self.assertEqual(samples[0]["returncode"], 7)
        self.assertEqual(len(json.loads((self.output / "subruns.json").read_text())), 2)
        self.assertEqual(json.loads((self.output / "manifest.json").read_text())["state"], "failed")

    def test_unexpected_rebuild_fails_and_preserves_evidence(self):
        def rebuilding(command, cwd, environment, stdout, stderr):
            result = self.fake_command(command, cwd, environment, stdout, stderr)
            stderr.write_text("    Checking uv v0.1 (/workspace)\n")
            return result
        with mock.patch.object(repeated.core, "run_command", side_effect=rebuilding), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, "expected a no-op"):
                repeated.run(self.arguments)
        subruns = json.loads((self.output / "subruns.json").read_text())
        self.assertEqual(len(subruns), 1)
        self.assertEqual(subruns[0]["compiled_packages"], ["uv"])

    def test_configuration_rejects_incompatible_workloads(self):
        invalid = [
            {"repetitions": True},
            {"repetitions": 0},
            {"repetitions": 8},
            {"repetitions": 8, "repeatable_workload": "noop", "prepare_command": ["python3", "dirty_fixture.py"]},
            {"metric_files": {"Ir": {}}},
        ]
        for configuration in invalid:
            with self.subTest(configuration=configuration), self.assertRaises(ValueError):
                repeated.configuration_repetitions(configuration)


if __name__ == "__main__":
    unittest.main()
