import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import loader_fixture as fixture


class LoaderFixtureTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.base_patch = mock.patch.object(fixture, "BASE", self.root / "fixtures")
        self.base_patch.start()
        self.source_patch = mock.patch.object(
            fixture, "source_identity",
            return_value={"revision": "fixture", "tracked_files": 1, "sha256": "source"},
        )
        self.source_patch.start()
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.cache = self.root / "existing-package-cache"
        (self.cache / "registry" / "cache").mkdir(parents=True)
        (self.cache / "registry" / "cache" / "package.crate").write_bytes(b"cached source")
        (self.cache / "credentials.toml").write_text("must never be copied")
        self.template = self.root / "template.json"
        self.template.write_text(json.dumps({
            "cwd": str(self.workspace),
            "canonical_executable": str(self.root / "must-not-touch"),
            "variants": {"baseline": "/bin/true", "candidate": "/bin/true"},
            "command": ["{cargo}", "-Zohm-defaults=yes", "check", "--offline", "--locked"],
            "env": {"CARGO_HOME": str(self.cache), "RUSTC": "/bin/true"},
            "record_files": [],
        }))
        self.manifest = fixture.initialize(
            "test", self.template, "/bin/true", copy_mode="copy"
        )
        self.state = fixture.fixture_root("test")
        self.environment = fixture.make_environment(self.manifest)
        self.original = b"native library content"

    def tearDown(self):
        self.source_patch.stop()
        self.base_patch.stop()
        self.temporary.cleanup()

    def fake_seed(self, command, cwd, environment, stdout, stderr):
        target = Path(environment["CARGO_TARGET_DIR"])
        shared = Path(environment["CARGO_BUILD_BUILD_DIR"])
        (target / "library.rlib").write_bytes(self.original)
        os.link(target / "library.rlib", shared / "library.rlib")
        (target / "shared-link").symlink_to(shared / "library.rlib")
        stdout.write_text(json.dumps({
            "reason": "compiler-artifact", "package_id": "fixture#0.1.0",
            "target": {"name": "fixture", "kind": ["lib"]}, "profile": {"test": False},
            "fresh": False, "filenames": [str(target / "library.rlib")], "executable": None,
        }) + "\n")
        stderr.write_text("   Compiling fixture v0.1.0\n"
                          f"     Running {chr(96)}/fake/rustc --crate-name fixture --emit=dep-info,metadata,link{chr(96)}\n")
        return {"returncode": 0, "stdout": str(stdout), "stderr": str(stderr), "wall_ns": 1}

    def seed(self, variant="baseline"):
        with mock.patch.object(fixture, "run_command", side_effect=self.fake_seed):
            return fixture.seed("test", variant)

    def prepare(self, variant="baseline"):
        return fixture.prepare(
            "test", variant, self.root / "results", "measurement", 0, 0, self.environment
        )

    def test_private_paths_and_package_cache(self):
        self.seed()
        self.assertFalse((self.root / "must-not-touch").exists())
        self.assertEqual((self.cache / "registry/cache/package.crate").read_bytes(), b"cached source")
        self.assertEqual(
            (self.state / "package-home/registry/cache/package.crate").read_bytes(), b"cached source"
        )
        self.assertFalse((self.state / "package-home/credentials.toml").exists())
        self.assertEqual(self.manifest["seed_command"].count("--no-run"), 1)
        self.assertIn("test", self.manifest["seed_command"])

    def test_restore_removes_check_state_and_preserves_native_links(self):
        record = self.seed()
        live = self.state / "live"
        (live / "target" / "check-only.rmeta").write_bytes(b"must not leak")
        (live / "target" / "library.rlib").write_bytes(b"changed by a measured command")
        prepared = self.prepare()
        self.assertFalse((live / "target" / "check-only.rmeta").exists())
        self.assertEqual((live / "target" / "library.rlib").read_bytes(), self.original)
        self.assertEqual(
            (live / "target" / "library.rlib").stat().st_ino,
            (live / "shared" / "library.rlib").stat().st_ino,
        )
        snapshot_file = self.state / "snapshots/baseline/tree/target/library.rlib"
        self.assertNotEqual(snapshot_file.stat().st_ino, (live / "target/library.rlib").stat().st_ino)
        self.assertEqual(prepared["inventory_sha256"], record["inventory_sha256"])
        self.assertTrue((live / "target/shared-link").is_symlink())

    def test_internal_symlink_never_deletes_external_target(self):
        self.seed()
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "keep").write_text("safe")
        (self.state / "live" / "escape").symlink_to(outside, target_is_directory=True)
        self.prepare()
        self.assertEqual((outside / "keep").read_text(), "safe")

    def test_live_symlink_is_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "keep").write_text("safe")
        (self.state / "live").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "plain descendant"):
            fixture.remove_live(self.state)
        self.assertEqual((outside / "keep").read_text(), "safe")

    def test_tampered_snapshot_content_fails_full_verification(self):
        self.seed()
        path = self.state / "snapshots/baseline/tree/target/library.rlib"
        old = path.stat()
        path.write_bytes(b"X" * len(self.original))
        os.utime(path, ns=(old.st_atime_ns, old.st_mtime_ns))
        with self.assertRaisesRegex(ValueError, "differs from its sealed snapshot"):
            self.prepare()

    def test_wrong_environment_and_unowned_root_are_rejected(self):
        self.seed()
        environment = {**self.environment, "CARGO_TARGET_DIR": str(self.root / "outside")}
        with self.assertRaisesRegex(ValueError, "environment differs"):
            fixture.prepare("test", "baseline", self.root, "measurement", 0, 0, environment)
        marker = self.state / "fixture.json"
        data = json.loads(marker.read_text())
        data["root"] = str(self.root)
        marker.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "does not own"):
            fixture.remove_live(self.state)

    def test_path_traversal_and_mounts_are_rejected(self):
        with self.assertRaises(ValueError):
            fixture.fixture_root("../elsewhere")
        self.seed()
        with mock.patch.object(fixture, "reject_mounts", side_effect=ValueError("mounted directory")):
            with self.assertRaisesRegex(ValueError, "mounted"):
                fixture.remove_live(self.state)
        self.assertTrue((self.state / "live/target/library.rlib").exists())

    def test_metadata_only_seed_is_rejected(self):
        def fake_check(*args, **kwargs):
            result = self.fake_seed(*args, **kwargs)
            Path(result["stderr"]).write_text(
                "Checking fixture v0.1.0\n"
                f"Running {chr(96)}/fake/rustc --crate-name fixture --emit=dep-info,metadata{chr(96)}\n"
            )
            return result
        with mock.patch.object(fixture, "run_command", side_effect=fake_check):
            with self.assertRaisesRegex(ValueError, "metadata-only"):
                fixture.seed("test", "baseline")
        self.assertFalse((self.state / "snapshots/baseline/manifest.json").exists())

    def test_runlist_distinguishes_script_output_from_script_execution(self):
        stdout, stderr = self.root / "stdout", self.root / "stderr"
        stdout.write_text(json.dumps({
            "reason": "build-script-executed", "package_id": "fixture#0.1.0",
            "out_dir": "/fixture/out",
        }) + "\n")
        stderr.write_text("")
        cached = fixture.runlist(stdout, stderr)
        self.assertEqual(len(cached["build_script_outputs"]), 1)
        self.assertEqual(cached["other_invocations"], [])
        stderr.write_text("     Running `/fixture/build-script-build`\n")
        executed = fixture.runlist(stdout, stderr)
        self.assertEqual(executed["build_script_outputs"], cached["build_script_outputs"])
        self.assertEqual(executed["other_invocations"], [["/fixture/build-script-build"]])

    def test_existing_snapshot_cannot_be_overwritten(self):
        self.seed()
        with self.assertRaisesRegex(ValueError, "snapshot already exists"):
            self.seed()

    def test_variants_restore_their_own_state_at_identical_paths(self):
        self.seed("baseline")
        baseline = self.original
        self.original = b"candidate-produced native content"
        self.seed("candidate")
        first = self.prepare("baseline")
        live_file = self.state / "live/target/library.rlib"
        self.assertEqual(live_file.read_bytes(), baseline)
        second = fixture.prepare(
            "test", "candidate", self.root / "results", "measurement", 0, 1, self.environment
        )
        self.assertEqual(live_file.read_bytes(), self.original)
        for key in ("canonical_executable", "target", "shared"):
            self.assertEqual(first[key], second[key])

    def test_verifier_requires_matching_restore_and_timed_command(self):
        self.seed("baseline")
        self.seed("candidate")
        results = self.root / "results"
        results.mkdir()
        samples = []
        for position, variant in enumerate(fixture.VARIANTS):
            fixture.prepare("test", variant, results, "measurement", 0, position, self.environment)
            stdout, stderr = results / f"{variant}.stdout", results / f"{variant}.stderr"
            stdout.write_text("")
            stderr.write_text("Checking fixture v0.1.0\n")
            samples.append({
                "stage": "measurement", "pair": 0, "position": position, "variant": variant,
                "returncode": 0, "installed_sha256": self.manifest["variant_sha256"][variant],
                "stdout": str(stdout), "stderr": str(stderr),
                "command": [
                    self.manifest["canonical_executable"] if value == "{cargo}" else value
                    for value in self.manifest["check_command"]
                ],
            })
        (results / "manifest.json").write_text(json.dumps({"state": "complete"}))
        (results / "samples.json").write_text(json.dumps(samples))
        self.assertTrue(fixture.verify("test", results)["valid"])
        samples[0]["command"] = ["/bin/true"]
        (results / "samples.json").write_text(json.dumps(samples))
        with self.assertRaisesRegex(ValueError, "timed command differs"):
            fixture.verify("test", results)


if __name__ == "__main__":
    unittest.main()
