#!/usr/bin/env python3
"""Reconstruct the four cross-pair instruction ratios from the verified installation ledger."""
from decimal import Decimal, localcontext
from pathlib import Path
import csv
import hashlib
import subprocess
import sys

root = Path(__file__).resolve().parent
if not (len(sys.argv) == 2 and sys.argv[1] == '--derive'):
    subprocess.run(['sha256sum', '--check', '--quiet', 'SHA256SUMS'], cwd=root, check=True)
    assert hashlib.sha256((root / 'portable' / 'SHA256SUMS').read_bytes()).hexdigest() == '5529154a73504b5ba2923217107b279fc5b648970b3e0628898b8da37aabae84'
    subprocess.run([sys.executable, '-IB', 'verify.py'], cwd=root / 'portable', check=True, stdout=subprocess.DEVNULL)
rows = list(csv.DictReader((root / 'portable' / 'instruction-counts.tsv').read_text().splitlines(), delimiter='\t'))
header = 'workflow\treturn\tparent_total_Ir\tguarded_total_Ir\tparent_over_guarded\tpair_1_ratio\tpair_2_ratio'
lines = [header]
with localcontext() as ctx:
    ctx.prec = 40
    for workflow in ('check', 'test'):
        for branch in ('A', 'B'):
            matches = [r for r in rows if (r['verb'], r['return_branch'], r['compiler']) == (workflow, branch, 'sum')]
            assert [r['pair'] for r in matches] == ['1', '2']
            p = sum(int(r['parent_Ir']) for r in matches)
            q = sum(int(r['guarded_Ir']) for r in matches)
            per_pair = [Decimal(r['parent_Ir']) / Decimal(r['guarded_Ir']) for r in matches]
            lines.append('\t'.join([workflow, branch, str(p), str(q), f'{Decimal(p) / Decimal(q):.9f}', *(f'{v:.9f}' for v in per_pair)]))
content = '\n'.join(lines) + '\n'
if len(sys.argv) == 2 and sys.argv[1] == '--derive':
    with (root / 'four-ratios.tsv').open('x') as out:
        out.write(content)
else:
    assert len(sys.argv) == 1 and (root / 'four-ratios.tsv').read_text() == content
    print(content, end='')
