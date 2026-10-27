"""Archive the successful compiler and native linker calls and check them against each Cargo roster."""
import argparse
from collections import Counter
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile


def classify(line):
    call = re.match(rb'execve\("([^"]+)", (.*)', line)
    if not call or not line.rstrip().endswith(b'= 0'):
        return None
    exe = Path(call[1].decode())
    if exe.name == 'ld.bfd' and exe.parent.name == 'wild-ld':
        return ('wild', '')
    crate = re.search(rb'"--crate-name", "([^" ]+)"', call[2])
    if exe.name != 'rustc' or not crate or crate[1] == b'___':
        return None
    is_link_only = re.search(rb'"(?:-Z)?link-only"', call[2])
    return ('rustc_link_only' if is_link_only else 'rustc_full', crate[1].decode())


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def append(tar, name, data):
    entry = tarfile.TarInfo(name)
    entry.size = len(data)
    tar.addfile(entry, io.BytesIO(data))


def reduce_archive(path):
    mode, arm = path.name.split('-', 2)[:2]
    assert mode in ('build', 'test') and arm in ('parent', 'candidate')
    output = path.with_name(f'{mode}-{arm}-execs.tar.gz')
    report = {}
    counters, crates, receipts, rosters = {}, {}, {}, {}
    with tarfile.open(path) as src, output.open('wb') as compressed, gzip.GzipFile(fileobj=compressed, mode='wb', mtime=0) as zipfile, tarfile.open(fileobj=zipfile, mode='w|') as dest:
        for member in src:
            name = Path(member.name)
            assert member.isfile() and member.size < 16_000_000 and '..' not in name.parts
            assert name.parts[0] == f'results-revision-native-66815c41574c-{mode}'
            if len(name.parts) == 2:
                assert name.name in ('plan.json', 'complete.json')
                append(dest, str(name), src.extractfile(member).read())
                continue
            assert len(name.parts) == 3
            phase = name.parts[1]
            assert phase in (f'{arm}-verify-edit', f'{arm}-verify-final-edit')
            if name.name.startswith('exec.'):
                assert re.fullmatch(r'exec\.\d+',name.name)
                lines = []
                for line in src.extractfile(member):
                    event = classify(line)
                    if event:
                        kind, crate = event
                        counters.setdefault(phase, Counter())[kind] += 1
                        if crate:
                            crates.setdefault(phase, []).append([kind, crate])
                        lines.append(line)
                if lines:
                    append(dest, str(name), b''.join(lines))
            else:
                assert name.name in ('stdout', 'stderr', 'receipt.json')
                data = src.extractfile(member).read()
                if name.name == 'receipt.json':
                    receipts[phase] = json.loads(data)
                elif name.name == 'stdout':
                    rows = [json.loads(s) for s in data.splitlines() if s.startswith(b'{')]
                    arts = [r for r in rows if r['reason'] == 'compiler-artifact']
                    assert rows[-1]['success'] and len(arts) == (501 if mode == 'build' else 619)
                    roster = sorted((r['package_id'],r['target']['name'],','.join(r['target']['kind']),r['profile']['test']) for r in arts)
                    rosters[phase] = hashlib.sha256(json.dumps(roster).encode()).hexdigest()
                append(dest, str(name), data)
    for phase, r in receipts.items():
        assert counters[phase] == r['processes'] and sorted(crates[phase]) == r['crates']
        assert rosters[phase] == r['roster_sha']
        report[phase] = {'processes': dict(counters[phase]), 'roster_sha': rosters[phase]}
    assert len(report) == 2
    return {'original_sha256': sha(path), 'original_bytes': path.stat().st_size, 'retained_sha256': sha(output),
            'retained_bytes': output.stat().st_size, 'phases': report}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archives', nargs=4, type=Path)
    args = parser.parse_args()
    print(json.dumps({p.name: reduce_archive(p) for p in args.archives}, sort_keys=True, indent=2))
