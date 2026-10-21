import os
from pathlib import Path
import shutil
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import loader_fixture_delta as fixture
import loader_fixture as original_fixture
import test_loader_fixture as inherited

class DeltaLoaderFixtureTests(inherited.LoaderFixtureTests):
    def setUp(self):
        # Re-run inherited tests without changing other modules' test selection.
        self.helper_patch = mock.patch.object(inherited, "fixture", fixture)
        self.helper_patch.start()
        self.addCleanup(self.helper_patch.stop)
        super().setUp()

    def test_inventory_hashes_each_inode_once_and_preserves_rows(self):
        directory = self.root / "inventory"
        directory.mkdir()
        first = directory / "first"
        first.write_bytes(b"one native inode")
        os.link(first, directory / "second")
        with mock.patch.object(fixture, "sha256", wraps=fixture.sha256) as digest:
            rows = fixture.inventory(directory)
        self.assertEqual(digest.call_count, 1)
        self.assertEqual(rows, original_fixture.inventory(directory))

    def test_inventory_rejects_file_changes_during_hashing(self):
        directory = self.root / "inventory"
        directory.mkdir()
        path = directory / "first"
        path.write_bytes(b"native inode")
        original_digest = fixture.sha256

        def change_after_hash(file):
            result = original_digest(file)
            file.write_bytes(b"changed native inode")
            return result

        with mock.patch.object(fixture, "sha256", side_effect=change_after_hash):
            with self.assertRaisesRegex(ValueError, "changed during inventory"):
                fixture.inventory(directory)

    def test_same_size_same_mtime_corruption_is_repaired(self):
        self.seed()
        path = self.state / "live/target/library.rlib"
        metadata = path.stat()
        path.write_bytes(b"X" * len(self.original))
        os.utime(path, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
        entry = self.prepare()
        self.assertEqual(path.read_bytes(), self.original)
        self.assertEqual(entry["restoration"]["method"], "rsync-checksum")

    def test_external_hardlink_forces_independent_copy_before_metadata_updates(self):
        self.seed()
        source = self.state / "snapshots/baseline/tree/target/library.rlib"
        before = fixture.inventory_bytes(fixture.inventory(self.state / "snapshots/baseline/tree"))
        destination = self.state / "live/target/library.rlib"
        destination.unlink()
        os.link(source, destination)
        entry = self.prepare()
        self.assertEqual(entry["restoration"]["method"], "full-copy")
        self.assertEqual(entry["restoration"]["fallback"], "live tree has hardlinks outside itself")
        self.assertNotEqual(source.stat().st_ino, destination.stat().st_ino)
        self.assertEqual(before, fixture.inventory_bytes(fixture.inventory(self.state / "snapshots/baseline/tree")))

    def test_surplus_internal_hardlinks_are_removed(self):
        original_seed = self.fake_seed

        def extra_files(*args, **kwargs):
            result = original_seed(*args, **kwargs)
            for name in ("separate-a", "separate-b"):
                path = self.state / "live/target" / name
                path.write_bytes(b"identical independent native files")
                os.utime(path, ns=(1700000000123456789, 1700000000123456789))
            return result

        self.fake_seed = extra_files
        self.seed()
        first = self.state / "live/target/separate-a"
        second = self.state / "live/target/separate-b"
        second.unlink()
        os.link(first, second)
        self.prepare()
        self.assertNotEqual(first.stat().st_ino, second.stat().st_ino)
        self.assertEqual(first.stat().st_mtime_ns, 1700000000123456789)

    def test_existing_file_symlink_never_modifies_external_target(self):
        self.seed()
        outside = self.root / "outside-file"
        outside.write_bytes(b"outside content")
        old = outside.stat()
        destination = self.state / "live/target/library.rlib"
        destination.unlink()
        destination.symlink_to(outside)
        self.prepare()
        self.assertEqual(outside.read_bytes(), b"outside content")
        self.assertEqual(outside.stat().st_mtime_ns, old.st_mtime_ns)
        self.assertEqual(destination.read_bytes(), self.original)
        self.assertFalse(destination.is_symlink())

    def test_existing_directory_symlink_never_modifies_external_tree(self):
        self.seed()
        outside = self.root / "outside-directory"
        outside.mkdir()
        (outside / "keep").write_bytes(b"outside content")
        target = self.state / "live/target"
        shutil.rmtree(target)
        target.symlink_to(outside, target_is_directory=True)
        self.prepare()
        self.assertEqual((outside / "keep").read_bytes(), b"outside content")
        self.assertEqual(list(outside.iterdir()), [outside / "keep"])
        self.assertFalse(target.is_symlink())


if __name__ == "__main__":
    unittest.main()
