#!/usr/bin/env python3
"""Verify retry lineage around the byte-identical independent raw reviewer."""
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
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--retry-source-freeze-sha256', required=True)
    parser.add_argument('--analyze-after-terminal', action='store_true')
    parser.add_argument('--ir-review', type=Path)
    args = parser.parse_args()
    before = evidence.verify(args.phase, args.retry_source_freeze_sha256)
    command = ['/usr/bin/python3', '-I', '-B', str(contract.PACKAGE / 'reviewer/review.py'),
               '--controls', str(contract.CONTROLS), '--phase', args.phase, '--output', str(args.output)]
    if args.analyze_after_terminal:
        command.append('--analyze-after-terminal')
    if args.phase == 'native':
        contract.require(args.ir_review is not None, 'native requires prior IR review')
        prior = contract.read(args.ir_review.parent / 'retry-review.json')
        contract.require(prior['state'] == 'passed' and prior['phase'] == 'ir' and prior['qualifies'] is True
                         and prior['original_review_sha256'] == contract.sha(args.ir_review)
                         and prior['retry_source_freeze_sha256'] == args.retry_source_freeze_sha256,
                         'native requires accepted IR review with the same retry lineage')
        contract.require(prior['retry_lineage'] == evidence.verify('ir', args.retry_source_freeze_sha256),
                         'prior IR retry lineage changed')
        command.extend(['--ir-review', str(args.ir_review)])
    result = subprocess.run(command)
    after = evidence.verify(args.phase, args.retry_source_freeze_sha256)
    contract.require(before == after, 'retry lineage changed during original review')
    original = contract.read(args.output / 'review.json')
    contract.write_new(args.output / 'retry-review.json', {
        'state': 'passed' if result.returncode == 0 else 'invalid', 'phase': args.phase,
        'retry_source_freeze_sha256': args.retry_source_freeze_sha256,
        'original_review_sha256': contract.sha(args.output / 'review.json'),
        'original_review_status': original['status'], 'qualifies': original.get('qualifies', False),
        'retry_lineage': after,
        'scope': 'Extra launch-history and absence-proof audit only. The original raw reviewer, both-workflow integrity ordering, statistics and gates are byte-identical.'})
    return result.returncode


if __name__ == '__main__':
    sys.exit(main())
