#!/usr/bin/env python3
"""Use the unchanged collector, then bind both local closure launch attempts."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import contract
import evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=('ir', 'native'), required=True)
    parser.add_argument('--retry-source-freeze-sha256', required=True)
    args = parser.parse_args()
    contract.verify_attempt(args.retry_source_freeze_sha256, complete=True)
    contract.load_original_binding().verify_failed_capture(contract.CONTROLS)
    # No collector flags, remote code, output selection or original receipt change.
    with (HERE / ('collect-' + args.phase + '.stdout')).open('xb') as stdout, (HERE / ('collect-' + args.phase + '.stderr')).open('xb') as stderr:
        result = subprocess.run(['/usr/bin/python3', '-I', '-B', str(contract.PACKAGE / 'collect_final.py'),
            '--phase', args.phase, '--source-freeze-sha256', contract.ORIGINAL_FREEZE], stdout=stdout, stderr=stderr)
    receipt = evidence.directory(args.phase) / 'receipt.json'
    contract.write_new(HERE / ('collect-' + args.phase + '.json'), {
        'phase': args.phase, 'returncode': result.returncode,
        'retry_source_freeze_sha256': args.retry_source_freeze_sha256,
        'stdout_sha256': contract.sha(HERE / ('collect-' + args.phase + '.stdout')),
        'stderr_sha256': contract.sha(HERE / ('collect-' + args.phase + '.stderr')),
        'original_collection_receipt_sha256': contract.sha(receipt) if receipt.is_file() else None})
    contract.require(result.returncode == 0, 'original collector failed; all outputs retained')
    report = evidence.attach(args.phase, args.retry_source_freeze_sha256)
    contract.load_original_binding().verify_failed_capture(contract.CONTROLS)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
