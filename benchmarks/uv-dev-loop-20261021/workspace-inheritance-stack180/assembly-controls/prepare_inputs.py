#!/usr/bin/env python3
"""Prepare final local evidence inputs only after both independent reviews finish."""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('inheritance_evidence_assembler', HERE / 'assemble.py')
assembly = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assembly)
ROOT = assembly.WORKSPACE
WORK = ROOT / 'work'
NATIVE_REVIEW = WORK / 'inheritance-raw-review/native-admission-closed'


def write(path, value):
    with path.open('x') as stream:
        stream.write(value if isinstance(value, str) else assembly.encoded(value).decode())


def table(reviews):
    rows = ['| Workflow / metric | Reduction | 99% paired interval | Sign p | Full gate |',
            '| --- | ---: | ---: | ---: | --- |']
    for phase in ('ir', 'native'):
        for row in reviews[phase]['completed']:
            label = 'Cargo Ir' if phase == 'ir' else 'native wall time'
            low, high = row['interval_99']
            rows.append(f"| {row['workflow']} / {label} | {100*row['reduction']:.4f}% | "
                        f"[{100*low:.4f}, {100*high:.4f}]% | {row['sign_p']:.10g} | "
                        + ('pass' if row['passes_gate'] else 'does not pass') + ' |')
    return '\n'.join(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-review-sha256', required=True)
    parser.add_argument('--native-transfer-manifest-sha256', required=True)
    args = parser.parse_args()
    output = HERE / 'final-inputs'
    assembly.need(not output.exists(), 'final input preparation must use its new reserved directory')
    controls = WORK / 'inheritance-measurement'
    captures = {
        'ir-failed': {'directory': str((controls / 'collections/ir-failed-postguard').relative_to(ROOT)),
                      'manifest_sha256': assembly.FAILED_IR},
        'ir-closed': {'directory': str((controls / 'collections/ir-closed-postguard').relative_to(ROOT)),
                      'manifest_sha256': assembly.IR_MANIFEST},
        'native': {'directory': str((controls / 'collections/native').relative_to(ROOT)),
                   'manifest_sha256': args.native_transfer_manifest_sha256},
    }
    review_inputs = {'ir': {'path': 'work/inheritance-raw-review/ir-transport-closed/review.json', 'sha256': assembly.IR_REVIEW},
                     'native': {'path': str((NATIVE_REVIEW / 'phase/review.json').relative_to(ROOT)),
                                'sha256': args.native_review_sha256}}
    reviews = {}
    for phase, row in review_inputs.items():
        source = ROOT / row['path']
        assembly.need(assembly.sha(source) == row['sha256'], 'final independent review identity differs')
        capture = captures['ir-closed' if phase == 'ir' else 'native']
        directory = ROOT / capture['directory']
        assembly.need(assembly.sha(directory / 'transfer-manifest.json') == capture['manifest_sha256'],
                      'final collection identity differs')
        reviews[phase] = assembly.review_phase(phase, source, assembly.read(directory / 'transfer-manifest.json'), directory)
    admission = NATIVE_REVIEW / 'native-admission-lineage.json'
    binding = NATIVE_REVIEW / 'review-binding.json'
    transport = NATIVE_REVIEW / 'phase/transport-resolution-review.json'
    assembly.verify_native_lineage(admission.read_bytes(), assembly.read(binding), assembly.read(transport),
        reviews['native'], args.native_review_sha256, args.native_transfer_manifest_sha256)

    # These are generated only from terminal, independently verified results.
    # No statistical calculations, workload calls, host access or publication occur.
    output.mkdir()
    final_table = table(reviews)
    native_passes = [row['workflow'] for row in reviews['native']['completed'] if row['passes_gate']]
    native_text = ('Both native workflows pass the predefined complete wall-time gate.' if len(native_passes) == 2 else
        'The complete native wall-time gate passes only for ' + ', '.join(native_passes) + '.' if native_passes else
        'Neither native workflow passes the complete wall-time gate; no native wall-time improvement is claimed.')
    native_text += ' Neither workflow establishes a significant native regression under the frozen rule.'
    limitations = ('Cargo Ir counts cover the instrumented Cargo process only, with compiler, linker and build-script '
        'children excluded. Instrumented elapsed time is not native wall time. The production pair uses all-static '
        'and ohm-defaults, ThinLTO and one codegen unit, without release PGO. The measured commands are warm, fresh '
        '`cargo check` and `cargo test --no-run`; no test program is executed. These results do not establish a cold-build speedup.')
    history = ('The original fixed IR observations are retained exactly. A post-integrity guard failure was followed '
        'by a metadata-only closure of the original analysis/gate tail. Its first launch stopped before staging; '
        'the retry completed remotely even though SSH returned 255. Both failed local receipts and authenticated '
        'successful remote finalization remain. The first native admission stopped before any Cargo call; exactly '
        'two remote metadata files and three local launch records were retained, after which the byte-identical '
        'original phase ran once. No measured observation was replaced, omitted, pooled or extended.')
    write(output / 'README.md', 'The candidate shares each workspace\'s immutable inherited dependency map through `Arc`, '
        'avoiding a deep clone for every member while preserving lookup and per-member processing. This is the '
        'fresh stack180 baseline versus the single inherited-dependency-map change.\n\n' + final_table + '\n\n'
        + native_text + '\n\n' + limitations + '\n\n' + history + '\n\n'
        'Both independent phase reviews completed all raw workflow checks before effects. IR uses 12 fixed pairs '
        'per workflow; native uses 30 pairs of eight-call sums. Each has two warmup pairs. The full gate requires '
        'at least 1% reduction, a positive 99% paired-bootstrap lower bound, exact two-sided sign p ≤ 0.01, and '
        'positive effects in both orders. All samples, profiles, logs and failures are retained.\n\n'
        'Verify SHA256SUMS, then use REPRODUCE.md. RAW-MANIFEST.json inventories the original archives and every '
        'raw payload. The complete original Callgrind profiles are included losslessly.\n')
    draft = (HERE / 'REPRODUCE.draft.md').read_text()
    ending = ('Final native findings and the exact final recovery/reviewer command are pending\n'
              'the terminal phase review. This draft is not an assembled publication artifact.\n')
    assembly.need(draft.count(ending) == 1, 'reproduction draft ending changed')
    command = ('The original independent native review used the preserved native-admission wrapper, after the final collection:\n\n'
        '```\ntaskset -c 8 /usr/bin/python3 -I -B work/inheritance-native-review/review.py \\\n'
        '  --source-freeze-sha256 ' + assembly.NATIVE_REVIEW_SOURCE + ' \\\n'
        '  --native-transfer-manifest-sha256 ' + args.native_transfer_manifest_sha256 + ' \\\n'
        '  --ir-review work/inheritance-raw-review/ir-transport-closed/review.json \\\n'
        '  --output work/inheritance-raw-review/native-admission-closed \\\n'
        '  --analyze-after-terminal\n```\n\n'
        'This historical command requires the retained task-owned control layout and a new output directory. '
        'To repeat its integrity review from a new prefix, restore the complete archived local lineage and '
        'collections into that layout and prospectively adapt only the local path bindings; preserve all raw bytes '
        'and hashes. Generic summary replay above works directly on disposable extracted workflow copies. '
        'Do not rerun the historical operational recovery or closure on a completed fixture.\n')
    write(output / 'REPRODUCE.md', draft.replace(ending, command))
    write(output / 'VALIDATION.md', 'The retained inheritance integration run passed all 28 selected cases under '
        'stock Rust 1.99 and the normal Cargo feature set. The exact candidate source CI completed successfully at '
        '`d81a093becb4321a975522624c2a383970f0d164`, tree '
        '`c4178b67e0b3a64a12b9b58f84b97323b99d734e`, parent '
        '`c40676e264501bc8a93095d3a273a1c300b80875`. Required jobs passed; the platform-specific APFS job was skipped.\n\n'
        'The measured production pair was built separately with the matched settings and paths recorded in '
        'its build, strip and independent cohort audits. Exact production commands passed the Ohm-enabled '
        'freshness and zero-child preflight. The normal-feature integration suite is not described as an '
        'exact production-feature test-suite pass.\n\n' + limitations + '\n\n' + history + '\n\n'
        'All source preparation failures, raw launch and transport outcomes, recovery requests/receipts and '
        'independent source/raw reviews remain in the local lineage or original collection archives.\n')

    selected = {}
    excluded = []
    def add(path, destination=None):
        path = Path(path)
        record = assembly.item(path)
        destination = destination or 'lineage/local/' + str(path.relative_to(WORK))
        storage = 'raw' if path.suffix in {'.tar', '.gz', '.bundle'} else 'readable'
        assembly.need(destination not in selected, 'duplicate evidence input destination')
        selected[destination] = {'source': str(path.relative_to(ROOT)), 'destination': destination,
                                 **record, 'storage': storage}
    def directory(path, excluded_paths=()):
        for member in sorted(path.rglob('*')):
            if any(member == skip or member.is_relative_to(skip) for skip in excluded_paths):
                continue
            assembly.need(not member.is_symlink(), 'symlink in local evidence lineage')
            if member.is_file():
                add(member)
            else:
                assembly.need(member.is_dir(), 'special file in evidence lineage')
    for name in ('inheritance-ir-closure', 'inheritance-ir-closure-retry', 'inheritance-native-admission',
                 'inheritance-native-review', 'inheritance-raw-review'):
        directory(WORK / name)
    directory(controls, (controls / 'collections', controls / 'delivery/payload.tar'))
    directory(controls / 'collections/setup')
    excluded.append({'path': str((controls / 'delivery/payload.tar').relative_to(ROOT)),
        'reason': 'Runtime and executable staging payload, not measurement observations; original delivery hashes and source/build/runtime identities are retained.'})
    candidate = WORK / 'workspace-inheritance-candidate'
    directory(candidate, (candidate / 'compiler-build',))
    production = WORK / 'production-build/host2-inheritance-stack180'
    binary_paths = tuple(production / 'results' / name for name in ('cargo-inheritance-stack180-baseline', 'cargo-inheritance-stack180-shared'))
    directory(production, binary_paths)
    for name, path in zip(('baseline', 'candidate'), binary_paths):
        excluded.append({'path': str(path.relative_to(ROOT)), 'sha256': assembly.EXPECTED[name],
                         'reason': 'Immutable production executable retained separately; complete build/strip/audit identities are included.'})
    for path in sorted((WORK / 'workspace-inheritance-publication').iterdir()):
        if path.is_file():
            add(path)
    for source, destination in ((admission, 'lineage/native-admission-final-review.json'),
                               (binding, 'lineage/native-admission-review-binding.json'),
                               (transport, 'lineage/native-transport-resolution-review.json')):
        add(source, destination)
    for name in ('README.md', 'REPRODUCE.md', 'VALIDATION.md'):
        add(output / name, name)
    for path in sorted(HERE.iterdir()):
        if path.is_file():
            add(path, 'assembly-controls/' + path.name)
    inputs = {'status': 'reviewed-ready', 'prepared_at': datetime.now(timezone.utc).isoformat(),
        'scope': 'All included comparisons are terminal and independently reviewed; no new statistics or host work.',
        'source_sha256': assembly.sha(HERE / 'assemble.py'), 'captures': captures, 'reviews': review_inputs,
        'lineage': list(selected.values()), 'excluded_nonmeasurement_payloads': excluded}
    write(output / 'inputs.json', inputs)
    print(json.dumps({'inputs': str(output / 'inputs.json'), 'sha256': assembly.sha(output / 'inputs.json'),
                      'lineage_files': len(selected), 'source_sha256': inputs['source_sha256']}, indent=2))


if __name__ == '__main__':
    main()
