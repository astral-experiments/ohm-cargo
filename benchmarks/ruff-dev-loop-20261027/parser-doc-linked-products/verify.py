"""Compare each traced Wild output with the same Cargo artifact on the opposite source state."""

import argparse
import hashlib
import json
from pathlib import Path
import tarfile

here = Path(__file__).resolve().parent
cli = argparse.ArgumentParser(description=__doc__)
cli.add_argument('native_results', type=Path, nargs='?', default=here.parent / 'native-qualified-results')
cli.add_argument('--emit', action='store_true', help='Write the derived JSON to standard output.')
args = cli.parse_args()
archive_hashes = {
    'doc-build': '1b7278d62529a9cbcdee046614df8c587431a783105ab66ae0384dcfa4e1bd50',
    'doc-test': '38da3b01224d78418b5e6b01b5976883a68744953655d69ea95b59e89274c0bf',
    'parser-build': '28681e587b61d8b9c26b0678b7b073a63edd449cd77277d2db7af2fd4ceee6b4',
    'parser-test': '28e49c66a16a8f659bb7467462ee92d26bfac7390d3c00aea56a277594db10fa',
}
links = json.loads((here / 'link-outputs.json').read_bytes())
report = {}
for edit, digest in archive_hashes.items():
    archive = args.native_results / (edit + '.tar.gz')
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == digest
    counts = {'doc-build': 3, 'doc-test': 19, 'parser-build': 8, 'parser-test': 67}
    group = 'pairs-posobs4fmt-c3-' + edit
    result = {}
    with tarfile.open(archive) as tf:
        def get(tag, file):
            return json.load(tf.extractfile(f'{group}/{tag}/{file}.json'))

        for tag, original in [('candidate-verify-edit', 'candidate-before'), ('candidate-verify-final-edit', 'candidate-final-fresh')]:
            trace = links[edit][tag]
            published = {(f, h) for f, h, kind, _ in get(tag, 'physical-execs') if kind == 'wild'}
            assert {(e['trace'], e['sha256']) for e in trace['wild']} == published
            assert len(trace['wild']) == len(published) == counts[edit]
            products = {p['path']: p for p in trace['products']}
            before = get(original, 'receipt')
            after = get(tag, 'receipt')
            assert before['dataclass'] == after['dataclass']
            assert (before['parser_diagnostics'] != after['parser_diagnostics']) == edit.startswith('parser')
            assert set(before['elf']) == set(after['elf']) == set(products)
            assert len(products) == (15 if edit.endswith('build') else 110)
            left = get(original, 'sections')
            right = get(tag, 'sections')
            assert set(left) == set(right) == set(products)
            changed = {path for path, sha in before['elf'].items() if after['elf'][path] != sha}
            linked = {}
            for event in trace['wild']:
                out = event['linker_output']
                package, unit, folder, name = out.split('/')
                assert len(unit) == 16 and folder == 'out'
                choices = [path for path, p in products.items() if path == out or (p['crate'] == package and not p['test_profile'] and Path(path).name == name and Path(path).parent.as_posix() == 'ohm-whole-skips-20261027/native-target/debug')]
                assert len(choices) == 1, (edit, tag, out, choices)
                path, = choices
                assert path not in linked
                assert left[path]['raw_sha256'] == before['elf'][path] and right[path]['raw_sha256'] == after['elf'][path]
                a, b = left[path]['sections'], right[path]['sections']
                differences = {}
                for section in sorted(a.keys() | b.keys()):
                    if section not in a or section not in b:
                        differences[section] = ['presence']
                    else:
                        fields = sorted(k for k in a[section].keys() | b[section].keys() if a[section].get(k) != b[section].get(k))
                        if fields:
                            differences[section] = fields
                classification = 'byte-identical'
                if path in changed:
                    allowed = {'.note.gnu.build-id': {'digest'}, '.rodata': {'entsize'}}
                    classification = 'other-recorded-section-differences' if any(set(fields) - allowed.get(section, set()) for section, fields in differences.items()) else 'only-recorded-build-id-or-entry-size'
                else:
                    assert not differences
                linked[path] = {**products[path], 'linker_output': out, 'source_state_reference': original,
                                'original': before['elf'][path], 'edited': after['elf'][path],
                                'class': classification, 'section_fields': differences}
            assert changed <= set(linked), ('changed product outside linked set', edit, changed - set(linked))
            result[tag] = linked
    report[edit] = result

if args.emit:
    print(json.dumps(report, sort_keys=True, indent=2))
else:
    from collections import Counter
    expected_file = here / 'products.json'
    assert report == json.loads(expected_file.read_bytes())
    for edit, phases in report.items():
        same = []
        for label, rows in phases.items():
            counts = Counter(r['class'] for r in rows.values())
            same.append({r['path'] for r in rows.values() if r['class'] == 'byte-identical'})
            print(edit, label, dict(counts))
        print('  byte-identical in both', len(same[0] & same[1]))
