#!/usr/bin/env python3
"""Verify admission lineage, then invoke the exact frozen terminal native reviewer."""
import argparse
import importlib.util
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lineage


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-freeze-sha256', required=True)
    parser.add_argument('--native-transfer-manifest-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--ir-review', type=Path, required=True)
    parser.add_argument('--analyze-after-terminal', action='store_true')
    args = parser.parse_args()
    lineage.verify_source(args.source_freeze_sha256)
    lineage.common.need(lineage.common.sha(args.ir_review) == lineage.common.IR_REVIEW, 'accepted independent IR review differs')
    lineage.common.need(not args.output.exists(), 'new independent review directory required')
    before = lineage.verify(args.source_freeze_sha256, args.native_transfer_manifest_sha256)
    args.output.mkdir()
    lineage.common.write(args.output / 'native-admission-lineage.json', before)
    original_path = lineage.TRANSPORT / 'review.py'
    sys.path.insert(0, str(lineage.TRANSPORT))
    spec = importlib.util.spec_from_file_location('unchanged_inheritance_transport_reviewer', original_path)
    original = importlib.util.module_from_spec(spec);spec.loader.exec_module(original)
    command = [str(original_path), '--phase', 'native', '--output', str(args.output / 'phase'),
               '--transport-source-freeze-sha256', lineage.TRANSPORT_SOURCE, '--ir-review', str(args.ir_review)]
    if args.analyze_after_terminal:
        command.append('--analyze-after-terminal')
    previous = sys.argv
    try:
        sys.argv = command
        result = original.main()
    finally:
        sys.argv = previous
    after = lineage.verify(args.source_freeze_sha256, args.native_transfer_manifest_sha256)
    lineage.common.need(before == after, 'native admission/retention evidence changed during original review')
    report = lineage.common.read(args.output / 'phase/review.json')
    lineage.common.write(args.output / 'review-binding.json', {
        'status': 'passed' if result == 0 else 'invalid', 'original_returncode': result,
        'source_freeze_sha256': args.source_freeze_sha256,
        'lineage_before_effects_sha256': lineage.common.sha(args.output / 'native-admission-lineage.json'),
        'original_review_sha256': lineage.common.sha(args.output / 'phase/review.json'),
        'original_review_status': report['status'], 'qualifies': report.get('qualifies', False),
        'lineage_unchanged_after_review': True, 'sampling_or_analysis_driver_changed': False})
    return result


if __name__ == '__main__':
    sys.exit(main())
