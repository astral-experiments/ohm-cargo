import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent))
import paired

class RawReceiptTests(unittest.TestCase):
    def command(self, code):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        out, err = root / 'stdout', root / 'stderr'
        argv = [sys.executable, '-I', '-B', '-c', code]
        result = paired.run_command(argv, root, dict(os.environ), out, err)
        receipt = json.loads((root / 'stdout.command.json').read_bytes())
        self.assertEqual(receipt['command'], argv)
        self.assertEqual(receipt['cwd'], str(root))
        self.assertEqual(receipt['result'], result)
        self.assertGreater(result['wall_ns'], 0)
        return root, result, receipt

    def test_success_before_decoder(self):
        root, result, receipt = self.command('print("not-json")')
        with self.assertRaises(json.JSONDecodeError):
            json.loads((root / 'stdout').read_text())
        self.assertEqual(receipt['result']['returncode'], 0)
        self.assertTrue((root / 'stdout.command.json').exists())

    def test_nonzero_exit_is_retained(self):
        root, result, receipt = self.command('import sys; print("out"); print("err",file=sys.stderr); sys.exit(7)')
        self.assertEqual(result['returncode'], 7)
        self.assertEqual((root / 'stdout').read_text(), 'out\n')
        self.assertEqual((root / 'stderr').read_text(), 'err\n')

    def test_existing_receipt_refuses_before_second_command(self):
        root, result, receipt = self.command('print("first")')
        original = (root / 'stdout.command.json').read_bytes()
        with self.assertRaises(ValueError):
            paired.run_command([sys.executable, '-c', 'print("second")'], root, dict(os.environ), root / 'stdout', root / 'stderr')
        self.assertEqual((root / 'stdout').read_text(), 'first\n')
        self.assertEqual((root / 'stdout.command.json').read_bytes(), original)

if __name__ == '__main__':
    unittest.main()
