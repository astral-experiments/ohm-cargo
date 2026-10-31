"""Recompute the retired instruction and allocated-byte results from portable Ruff receipts."""
import argparse
from fractions import Fraction
import json
from pathlib import Path
import statistics
import sys
import tarfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import root_recount as r


class Packet:
    def __init__(self, header):
        self.header = header
        self.data = {}

    def add(self, name, contents):
        assert name not in self.data
        source_sha, digest, size = self.header['files'][name]
        assert len(contents) == size and r.sha(contents) == digest
        assert name.endswith('.gz') or source_sha == digest
        self.data[name] = contents

    def payload(self, name):
        return self.data[name]

    def has_verified_body(self, digest):
        # The full-program reader verified original ELF bytes on each boot. The portable
        # packet retains those digests and lengths along with every per-command verdict.
        b = self.header['native_bodies'][digest]
        return b['bytes'] > 4096 and len(b['zstd_sha256']) == 64


def finish(packet):
    h = packet.header
    assert set(packet.data) == set(h['files'])
    out = r.recount(packet, h['position'], h['run'], h['head'])
    p, = [p for p in packet.data if p.startswith('independent-') and p.endswith('.json')]
    reviewed = json.loads(packet.data[p])
    assert reviewed['boot'] == out['boot'] and reviewed['order'] == out['order']
    for arm in r.ARMS:
        for phase in r.PHASES:
            row = out['phases'][arm][phase]
            prior = reviewed['observations'][arm][phase]
            assert all(row[k] == prior[k] for k in ('instructions', 'allocated', 'typed', 'dirty', 'exit'))
        for branch in r.REVS:
            kernel = r.record(packet, f'clean/{arm}/{branch}/kernel-commits.json')
            assert kernel['waited_tasks'] >= kernel['installed_images'] >= 394 + 72
    out['original'] = h['original']['digest']
    return out


def load(path):
    rows, packet, registration = {}, None, None
    with tarfile.open(path, 'r|xz') as tar:
        for member in tar:
            assert member.isfile() and 0 <= member.size <= 32 << 20 and registration is None
            source = tar.extractfile(member).read()
            if member.name.endswith('/header.json') or member.name == 'registration.json':
                if packet is not None:
                    pos = packet.header['position']
                    assert pos not in rows
                    rows[pos] = finish(packet)
                    packet = None
                if member.name == 'registration.json':
                    registration = json.loads(source)
                else:
                    header = json.loads(source)
                    assert member.name == header['position'] + '/header.json'
                    packet = Packet(header)
            else:
                prefix = packet.header['position'] + '/payload/'
                assert member.name.startswith(prefix)
                packet.add(member.name[len(prefix):], source)
    assert registration and packet is None and sorted(rows) == registration['positions']
    assert all(row['plan'] == registration['plan'] for row in rows.values())
    if registration['mode'] == 'pilot':
        assert sorted(rows) == ['01', '02']
        return {'mode': 'pilot', 'positions': rows}
    assert registration['mode'] == 'confirmation' and len(registration['excluded_boots']) == len(set(registration['excluded_boots'])) == 41
    assert not set(registration['excluded_boots']).intersection(row['boot'] for row in rows.values())
    return {'mode': 'confirmation', 'positions': rows, 'distribution': r.population(rows)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--match', type=Path, help='compare every result with a full original-ZIP recount')
    parser.add_argument('--official', type=Path, help='check the independent source-bound confirmation score')
    args = parser.parse_args()
    result = load(args.archive)
    if args.match:
        assert result == json.loads(args.match.read_bytes())
    rows = result['positions']
    if args.official:
        official = json.loads(args.official.read_bytes())
        assert result['mode'] == 'confirmation' and official['included_boots'] == 12 and official['pilot_boots_included'] == 0
        for pos, row in rows.items():
            checked = official['positions'][pos]
            assert row['boot'] == checked['boot'] and row['order'] == checked['order'] and row['pairs'] == checked['raw_instruction_pairs']
        for name, estimates in result['distribution'].items():
            assert all(estimates[k] == official['distributions'][name][k] for k in ('rank2', 'median', 'rank11'))
    print(f'{len(rows)} hosts, {14 * len(rows)} whole commands, {12 * len(rows)} successful off-clock 96-test suites')
    for name in r.GROUPS:
        pairs = [row['pairs'][name] for row in rows.values()]
        values = [Fraction(a, b) for a, b in pairs]
        line = f'{name:26} off {statistics.median(a for a, _ in pairs) / 1e9:9.3f}B  on {statistics.median(b for _, b in pairs) / 1e9:9.3f}B  median ratio {float(statistics.median(values)):.6f}'
        if result['mode'] == 'confirmation' and name in ('return-A', 'return-B', 'return_sum'):
            vals = result['distribution'][name]
            line += '  ranks 2 and 11 ' + ', '.join(f'{float(Fraction(*vals[k])):.6f}' for k in ('rank2', 'rank11'))
        print(line)
    for phase in ('first-B', 'unchanged-B', 'repair'):
        extra = [(row['phases']['Fon'][phase]['allocated'] - row['phases']['Foff'][phase]['allocated']) / 2**20 for row in rows.values()]
        print(f'{phase:26} median extra after exit {statistics.median(extra):.2f} MiB')
    for arm in r.ARMS:
        maxima = [max(item['allocated'] for item in row['phases'][arm].values()) / 2**30 for row in rows.values()]
        print(f'{arm:26} largest visit-end allocation on each host {min(maxima):.3f} to {max(maxima):.3f} GiB')
    if result['mode'] == 'confirmation':
        primary = ('return-A', 'return-B', 'return_sum')
        passes = all(Fraction(*result['distribution'][name]['rank2']) > 2 for name in primary)
        miss = Fraction(2 * (1 + 12), 2**12)
        print(f'Three lower bounds strictly above 2: {passes}. Marginal coverage {float(1-miss):.9%}, simultaneous coverage at least {float(1-3*miss):.9%}.')
        for name in primary:
            print(name, 'distinct ratios', result['distribution'][name]['distinct'])
            for arm in r.ARMS:
                group = [Fraction(*row['pairs'][name]) for row in rows.values() if row['order'][0] == arm]
                assert len(group) == 6
                print(f'  {arm} first: {len(group)} hosts, median {float(statistics.median(group)):.6f}')


if __name__ == '__main__':
    main()
