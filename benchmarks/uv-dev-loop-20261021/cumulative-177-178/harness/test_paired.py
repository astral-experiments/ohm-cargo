import argparse
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from paired import analyze, exact_sign_test, install_variant, make_plan, paired_count_statistics, paired_statistics, read_callgrind_summary, run, substitute


class PairedStatisticsTests(unittest.TestCase):
    def test_balanced_reproducible_order(self):
        plan = make_plan(30, 42)
        self.assertEqual(plan, make_plan(30, 42))
        self.assertEqual(plan.count(("baseline", "candidate")), 15)
        self.assertEqual(plan.count(("candidate", "baseline")), 15)
        self.assertNotEqual(plan, make_plan(30, 43))

    def test_known_constant_effect(self):
        pairs = [{"baseline": 1.1, "candidate": 1, "order": "AB" if i % 2 else "BA"} for i in range(30)]
        result = paired_statistics(pairs, resamples=200)
        self.assertAlmostEqual(result["paired_geometric_mean_speedup"], 1.1)
        self.assertAlmostEqual(result["paired_geometric_mean_time_reduction"], 1 / 11)
        for endpoint in result["bootstrap_speedup_interval"]:
            self.assertAlmostEqual(endpoint, 1.1)
        self.assertEqual(result["wins"], 30)
        self.assertAlmostEqual(result["exact_two_sided_sign_p"], 2 / 2**30)

    def test_balanced_null(self):
        pairs = [{"baseline": 2, "candidate": 1}, {"baseline": 1, "candidate": 2}] * 15
        result = paired_statistics(pairs, resamples=2000)
        self.assertAlmostEqual(result["paired_geometric_mean_speedup"], 1)
        self.assertLess(result["bootstrap_speedup_interval"][0], 1)
        self.assertGreater(result["bootstrap_speedup_interval"][1], 1)
        self.assertEqual(result["exact_two_sided_sign_p"], 1)

    def test_sign_ties(self):
        self.assertEqual(exact_sign_test(0, 0), 1)
        self.assertEqual(exact_sign_test(5, 0), 0.0625)
        self.assertEqual(exact_sign_test(0, 5), 0.0625)

    def test_order_effect_is_visible(self):
        pairs = [{"baseline": 2, "candidate": 1, "order": "AB"}, {"baseline": 1, "candidate": 2, "order": "BA"}] * 15
        result = paired_statistics(pairs, resamples=200)
        self.assertAlmostEqual(result["order"]["AB"]["geometric_mean_speedup"], 2)
        self.assertAlmostEqual(result["order"]["BA"]["geometric_mean_speedup"], 0.5)

    def test_substitution_leaves_code_braces(self):
        self.assertEqual(substitute("print({'a': 1}); {cargo}", {"cargo": "/tmp/cargo"}), "print({'a': 1}); /tmp/cargo")

    def test_count_statistics_are_not_labeled_as_time(self):
        result = paired_count_statistics([{"baseline": 120, "candidate": 100, "order": "AB"}], resamples=200)
        self.assertEqual(result["baseline_median_count"], 120)
        self.assertAlmostEqual(result["paired_geometric_mean_ratio"], 1.2)
        self.assertAlmostEqual(result["order"]["AB"]["geometric_mean_ratio"], 1.2)
        self.assertFalse(any("seconds" in key or "time_reduction" in key for key in result))


class CallgrindParserTests(unittest.TestCase):
    def parse(self, content, event="Ir"):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "callgrind.out"
            path.write_text(content)
            return read_callgrind_summary(path, event)

    def test_single_event_summary(self):
        self.assertEqual(self.parse("events: Ir\nsummary: 215838\n"), 215838)

    def test_event_column_index(self):
        self.assertEqual(self.parse("events: Dr Ir Dw\nsummary: 12 1234567890 3\n"), 1234567890)
        self.assertEqual(self.parse("events: Dr Ir Dw\nsummary: 12 1234567890 3\n", "Dw"), 3)

    def test_missing_summary_fails(self):
        with self.assertRaises(ValueError):
            self.parse("events: Ir\ntotals: 100\n")

    def test_missing_event_fails(self):
        with self.assertRaises(ValueError):
            self.parse("events: Dr Dw\nsummary: 1 2\n")

    def test_multipart_or_mismatched_summary_fails(self):
        for content in ("events: Ir\nsummary: 1\nsummary: 2\n", "events: Ir Dr\nsummary: 1\n"):
            with self.subTest(content=content), self.assertRaises(ValueError):
                self.parse(content)


class RunnerContractTests(unittest.TestCase):
    def configure(self, directory):
        variants = {}
        for name in ("baseline", "candidate"):
            path = directory / name
            path.write_text(name)
            path.chmod(0o755)
            variants[name] = str(path)
        configuration = directory / "config.json"
        configuration.write_text(json.dumps({
            "cwd": str(directory),
            "canonical_executable": str(directory / "active" / "cargo"),
            "variants": variants,
            "command": ["{cargo}", "check"],
            "env": {"CARGO_TARGET_DIR": str(directory / "targets" / "{variant}")},
        }))
        return argparse.Namespace(config=str(configuration), output=str(directory / "results"), phase="exploratory", pairs=2, warmup_pairs=1, seed=123)

    @staticmethod
    def fake_command(command, cwd, environment, stdout_path, stderr_path):
        stdout_path.write_text("synthetic runner validation\n")
        stderr_path.write_text("")
        return {"returncode": 0, "wall_ns": 1000000, "user_seconds": 0, "system_seconds": 0,
                "stdout": str(stdout_path), "stderr": str(stderr_path)}

    def test_records_every_pair_and_uses_one_executable_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            arguments = self.configure(directory)
            with mock.patch("paired.run_command", side_effect=self.fake_command) as command, contextlib.redirect_stdout(io.StringIO()):
                run(arguments)
            self.assertEqual(command.call_count, 6)
            self.assertEqual({call.args[0][0] for call in command.call_args_list}, {str(directory / "active" / "cargo")})
            manifest = json.loads((directory / "results" / "manifest.json").read_text())
            self.assertEqual(manifest["state"], "complete")
            self.assertEqual(manifest["sample_count"], 6)
            samples = json.loads((directory / "results" / "samples.json").read_text())
            self.assertEqual(sum(sample["stage"] == "measurement" for sample in samples), 4)
            self.assertTrue(all("{variant}" not in sample["configured_environment"]["CARGO_TARGET_DIR"] for sample in samples))
            self.assertTrue(all(sample["executable_unchanged"] for sample in samples))

    def test_failure_is_retained(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            arguments = self.configure(directory)
            def fail(*args):
                return self.fake_command(*args) | {"returncode": 1}
            with mock.patch("paired.run_command", side_effect=fail), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(RuntimeError):
                    run(arguments)
            manifest = json.loads((directory / "results" / "manifest.json").read_text())
            self.assertEqual(manifest["state"], "failed")
            self.assertEqual(manifest["sample_count"], 1)
            self.assertEqual(len((directory / "results" / "samples.jsonl").read_text().splitlines()), 1)

    def test_cleanup_runs_after_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            arguments = self.configure(directory)
            configuration_path = Path(arguments.config)
            configuration = json.loads(configuration_path.read_text())
            configuration["cleanup_command"] = ["restore-fixture"]
            configuration_path.write_text(json.dumps(configuration))
            def fail_build(command, *args):
                result = self.fake_command(command, *args)
                return result | {"returncode": 0 if command == ["restore-fixture"] else 1}
            with mock.patch("paired.run_command", side_effect=fail_build) as command, contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(RuntimeError):
                    run(arguments)
            self.assertEqual(command.call_args_list[-1].args[0], ["restore-fixture"])
            manifest = json.loads((directory / "results" / "manifest.json").read_text())
            self.assertEqual(manifest["cleanup"]["returncode"], 0)
            self.assertEqual(manifest["state"], "failed")

    def test_symlink_destination_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source = directory / "source"
            source.write_text("source")
            target = directory / "target"
            target.write_text("unchanged")
            destination = directory / "cargo"
            destination.symlink_to(target)
            with self.assertRaises(ValueError):
                install_variant(source, destination)
            self.assertEqual(target.read_text(), "unchanged")

    def test_missing_metric_file_fails_and_retains_sample(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            arguments = self.configure(directory)
            configuration_path = Path(arguments.config)
            configuration = json.loads(configuration_path.read_text())
            configuration["command"].append("--trace-children=no")
            configuration["metric_files"] = {
                "cargo_ir": {"format": "callgrind", "event": "Ir", "path": "{output}/callgrind-{stage}-{pair}-{variant}.out"},
            }
            configuration_path.write_text(json.dumps(configuration))
            with mock.patch("paired.run_command", side_effect=self.fake_command), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(RuntimeError, "missing or invalid metric"):
                    run(arguments)
            manifest = json.loads((directory / "results" / "manifest.json").read_text())
            self.assertEqual(manifest["state"], "failed")
            samples = json.loads((directory / "results" / "samples.json").read_text())
            self.assertEqual(len(samples), 1)
            self.assertIn("cargo_ir", samples[0]["metric_errors"])

    def test_records_metric_count_and_csv_column(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            arguments = self.configure(directory)
            configuration_path = Path(arguments.config)
            configuration = json.loads(configuration_path.read_text())
            configuration["command"].append("--trace-children=no")
            configuration["metric_files"] = {
                "cargo_ir": {"format": "callgrind", "event": "Ir", "path": "{output}/callgrind-{stage}-{pair}-{variant}.out"},
            }
            configuration_path.write_text(json.dumps(configuration))
            def command_with_counts(command, cwd, environment, stdout_path, stderr_path):
                metric = Path(environment["OHM_BENCH_OUTPUT"]) / f"callgrind-{environment['OHM_BENCH_STAGE']}-{environment['OHM_BENCH_PAIR']}-{environment['OHM_BENCH_VARIANT']}.out"
                metric.write_text("events: Dr Ir\nsummary: 2 1234\n")
                return self.fake_command(command, cwd, environment, stdout_path, stderr_path)
            with mock.patch("paired.run_command", side_effect=command_with_counts), contextlib.redirect_stdout(io.StringIO()):
                run(arguments)
            samples = json.loads((directory / "results" / "samples.json").read_text())
            self.assertTrue(all(sample["metrics"]["cargo_ir"] == 1234 for sample in samples))
            self.assertIn("metric_cargo_ir", (directory / "results" / "samples.csv").read_text().splitlines()[0])
            with contextlib.redirect_stdout(io.StringIO()):
                analyze(argparse.Namespace(directory=arguments.output, confidence=0.99, resamples=200, seed=1, minimum_pairs=30, minimum_improvement=0.01))
            analysis = json.loads((directory / "results" / "analysis.json").read_text())
            self.assertEqual(analysis["metrics"]["cargo_ir"]["statistics"]["baseline_median_count"], 1234)
            self.assertTrue(analysis["metrics"]["cargo_ir"]["acceptance"].startswith("No acceptance decision"))
            self.assertEqual(analysis["screen"]["measurement_kind"], "instrumented wall time")


if __name__ == "__main__":
    unittest.main()
