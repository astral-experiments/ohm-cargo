"""Check declared worker hashes and unchanged preregistered analysis inputs."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parent
registered = root / 'registered'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


assert sha(registered / 'SHA256SUMS') == '467090560adc9c413466e40f2b80770ab781245f0fa8af3ad7839a94829b10a6'
subprocess.run(['sha256sum', '--quiet', '-c', 'SHA256SUMS'], cwd=registered, check=True)
assert (root / 'native-order-random-order.json').read_bytes() == (registered / 'order.json').read_bytes()
order = json.loads((registered / 'order.json').read_bytes())
for host in ('primary', 'independent'):
    for batch in order[host]['batches']:
        assert len(batch) == 48
        for off in range(0, 48, 8):
            assert sorted(batch[off:off + 8]) == ['AB'] * 4 + ['BA'] * 4
    assert len(order[host]['plain']) == 16
assert len(order['primary']['edit_and_repeat']) == 12
bindings = {
    'native-order-live-v4.py': '9a54e14116a1ad7a66274d4a772fd59f149e647920d3ee85f870b43c31d0e8e5',
    'native-order-rss-v4.py': 'd60e4802fb93ff9e89cf126076eaa166741538cb0246e93d4619a2cc0242e3c0',
    'native-order-args-v4.py': '8f114ec372cd419e94a5f7e38f40b4667d69d8d04bd826d9b46bdde1c676d9c0',
    'native-order-primary-v4.py': 'ab724484def80ccdf10d34d6d4128776567a7403bbb13c36a83cf9a3cacfe62a',
    'native-order-qualification-v4.py': '46404aac5b1e610a520d8658e119e235ef66cd152df8ba2bfd01bde0844de442',
    'native-order-product-roster.json': '27875afe1aa700922fbb5f0916e943ac75199efb4d756c5d2c22cdf65f7f628e',
    'native-order-admit-clock-v4.py': 'e73e10a68a4c7f93444ec86643694f14970b3e6f953cd5fb4fbde11226664526',
    'native-order-clock-v4.py': 'bf46e005b3bfa877abf8d26e8f15e2413ffd1f41c74865cb1ab8cb167633b719',
    'native-order-secondary-results.py': 'dc872768bd4807681d69df3ca13fe69a79d224f47f9366547b18de61e5bf1fd0',
}
for filename, expected in bindings.items():
    path = root / filename
    assert sha(path) == expected, filename
    if path.suffix == '.py':
        ast.parse(path.read_bytes())
roster = json.loads((root / 'native-order-product-roster.json').read_bytes())['native_output']
assert len(set(roster['repeat'])) == 50 and len(set(roster['transition'])) == 52
print('Verified worker pins, physical native rosters, registered primary analysis, per-host order and held-out workload sizes.')
