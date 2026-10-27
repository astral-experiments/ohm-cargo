"""Map archived Wild `-o` operands to the Cargo artifact records from the same command."""

import hashlib
import json
from pathlib import Path
import re

root = Path.home() / '.cache/ohm-233-position-qualified-20261027'
assert (root / 'qualification-posobs4fmt-c3/complete.json').is_file()
report = {}
for name in ('doc-build', 'doc-test', 'parser-build', 'parser-test'):
    traces = root / ('pairs-posobs4fmt-c3-' + name)
    assert (traces / 'complete.json').is_file()
    report[name] = {}
    for tag in ('candidate-verify-edit', 'candidate-verify-final-edit'):
        d = traces / tag
        r = json.loads((d / 'receipt.json').read_bytes())
        rows = []
        for log in sorted(d.glob('exec.*')):
            for row in log.read_bytes().splitlines():
                linker = re.match(rb'execve\("([^"]+/wild-ld/ld\.bfd)", ', row)
                if not linker or not re.search(rb'\)\s+= 0$', row):
                    continue
                out = re.search(rb'"-o", "([^"]+)"', row)
                assert out, log.name
                rows.append({'trace': log.name, 'sha256': hashlib.sha256(row).hexdigest(),
                             'linker_output': '/'.join(Path(out[1].decode()).parts[-4:])})
        assert len(rows) == r['processes']['wild'] and len({z['linker_output'] for z in rows}) == len(rows)
        products = []
        for line in (d / 'stdout').read_bytes().splitlines():
            if not line.startswith(b'{'):
                continue
            a = json.loads(line)
            if a.get('reason') != 'compiler-artifact' or not a['package_id'].startswith('path+'):
                continue
            package = a['package_id'].split('#')[0].rsplit('/', 1)[-1]
            for filename in a['filenames']:
                token = '/'.join(Path(filename).parts[-4:])
                if token in r['elf']:
                    products.append({'path': token, 'crate': package, 'target': a['target']['name'],
                                     'kind': a['target']['kind'], 'test_profile': a['profile']['test']})
        assert {z['path'] for z in products} == set(r['elf']), (name, tag, len(products))
        report[name][tag] = {'wild': rows, 'products': products}
print(json.dumps(report, sort_keys=True, separators=(',', ':')))
