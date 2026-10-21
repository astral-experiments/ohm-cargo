#!/usr/bin/env python3
"""Run the unchanged raw/statistical reviewer with the exact transport lineage adapter."""
import argparse
import importlib.util
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import transport_contract as transport


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=('ir', 'native'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--transport-source-freeze-sha256', required=True)
    parser.add_argument('--analyze-after-terminal', action='store_true')
    parser.add_argument('--ir-review', type=Path)
    args = parser.parse_args()
    before = transport.verify_collection(args.phase, args.transport_source_freeze_sha256)
    command = [str(transport.PACKAGE / 'reviewer/review.py'), '--controls', str(transport.CONTROLS),
               '--phase', args.phase, '--output', str(args.output)]
    if args.analyze_after_terminal:
        command.append('--analyze-after-terminal')
    if args.phase == 'native':
        transport.require(args.ir_review is not None, 'native requires the accepted IR review')
        prior = transport.read(args.ir_review.parent / 'transport-resolution-review.json')
        transport.require(prior['state'] == 'passed' and prior['qualifies'] is True and prior['phase'] == 'ir'
                          and prior['original_review_sha256'] == transport.sha(args.ir_review)
                          and prior['transport_source_freeze_sha256'] == args.transport_source_freeze_sha256
                          and prior['transport_lineage'] == transport.verify_collection('ir', args.transport_source_freeze_sha256),
                          'native requires an accepted IR review with unchanged transport lineage')
        command.extend(['--ir-review', str(args.ir_review)])
    # Only this lineage module is adapted. The original evidence/raw/statistical
    # modules remain at their exact frozen paths and are loaded unchanged.
    sys.path.insert(0, str(transport.PACKAGE / 'reviewer'))
    load('closure_binding', HERE / 'closure_binding.py')
    original = load('inheritance_original_terminal_reviewer', transport.PACKAGE / 'reviewer/review.py')
    previous = sys.argv
    try:
        sys.argv = command
        result = original.main()
    finally:
        sys.argv = previous
    after = transport.verify_collection(args.phase, args.transport_source_freeze_sha256)
    transport.require(before == after, 'transport lineage changed during original review')
    report = transport.read(args.output / 'review.json')
    transport.write(args.output / 'transport-resolution-review.json', {
        'state': 'passed' if result == 0 else 'invalid', 'phase': args.phase,
        'qualifies': report.get('qualifies', False), 'original_review_status': report['status'],
        'original_review_sha256': transport.sha(args.output / 'review.json'),
        'transport_source_freeze_sha256': args.transport_source_freeze_sha256,
        'effective_lineage_binding_sha256': transport.sha(HERE / 'closure_binding.py'),
        'transport_lineage': after, 'local_transport_returncode': 255, 'remote_process_exit_code': None,
        'scope': 'Unchanged raw/statistical review plus authenticated remote metadata completion after the exact failed SSH transport. No execution or remote analysis repeated.'})
    return result


if __name__ == '__main__':
    sys.exit(main())
