"""Independently reopen the original 126 physical ledgers and six held-out triplets."""
import collections
import gzip
import hashlib
import itertools
import json
from pathlib import Path
import statistics
import subprocess

HERE = Path(__file__).resolve().parent
ARMS = ('Off', 'Full', 'Packed')
PHASES = ('empty-A','first-B','return-A','return-B','unchanged-B','invalid','repair')
GATED = ('first-B','return-A','return-B','unchanged-B')
MIB = 2**20


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def stream(label, manifest):
    path = HERE / (label+'.zst')
    expected = manifest[label]
    require(path.stat().st_size == expected['zst_bytes'] and digest(path.read_bytes()) == expected['zst_sha256'], label+' archive')
    seen = set()
    with subprocess.Popen(['zstd', '-qdc', '--long=26', str(path)], stdout=subprocess.PIPE) as proc:
        for header in proc.stdout:
            name, length = header.rstrip(b'\n').split(b'\t')
            key = name.decode()
            data = proc.stdout.read(int(length))
            require(key not in seen and expected['raw_members'][key] == [len(data),digest(data)], key+' member hash')
            seen.add(key)
            yield key, json.loads(data)
        require(proc.wait()==0 and seen==expected['raw_members'].keys(), label+' membership')


def allocation(ledger, recorded, readers):
    unique = {}
    by_root = collections.defaultdict(set)
    for name, (dev, ino, count, mode, blocks, size) in ledger.items():
        key = (dev,ino)
        root = name.partition('/')[0]
        require(root in ('build','target') and blocks >= 0 and size >= 0, name)
        by_root[root].add(key)
        require(unique.setdefault(key,blocks) == blocks, name+' alias')
    def allocated(nodes):
        return 512*sum(unique[node] for node in nodes)
    common = by_root['target'] & by_root['build']
    total = allocated(unique)
    require(total == recorded['allocated'] == readers['du_bytes'] == readers['find_bytes'] == readers['python_bytes'], 'independent physical readers')
    require(len(ledger)==recorded['all_names'] and len(unique)==recorded['all_inodes']==readers['find_inodes']==readers['python_inodes'], 'physical counts')
    require(recorded['roots'] == {k:allocated(v) for k,v in by_root.items()}, 'per-root allocations')
    require(allocated(common)==recorded['bytes_aliased_between_roots'] and len(common)==recorded['shared_inodes'], 'cross-root deduplication')
    return total


def main():
    manifest=json.loads(gzip.decompress((HERE/'members.json.gz').read_bytes()))
    custody=json.loads((HERE/'confirm-custody.json').read_bytes())
    require(manifest['confirmation_zip_sha256']==custody['sha256']=='e9fcdd65d0244f5a03f115a3b1640a1c79386b06722b082959f87ec0f8c47518','source ZIP')
    observations=dict(stream('observations',manifest))
    amounts={}
    orders=observations['orders.json']
    require(set(map(tuple,orders))==set(itertools.permutations(ARMS)) and len(orders)==6, 'counterbalance')
    for name, ledger in stream('ledgers',manifest):
        group, phase, leaf=name.split('/')
        amounts[group,phase]=allocation(ledger,observations[f'{group}/{phase}/storage.json'],observations[f'{group}/{phase}/allocation-readers.json'])
    require(len(amounts)==126,'complete ledger count')
    contrasts=observations['result.json']['contrasts']
    same_role={}
    for i,order in enumerate(orders,1):
        for arm in order:
            group=f'triplet-{i:02}-{arm}'
            require(observations[group+'/sdk.json']['role']==('P' if arm=='Full' else 'C'),'source role')
            for phase in PHASES:
                visit=observations[group+'/complete.json'][phase]
                total=amounts[group,phase]
                if phase=='invalid':
                    require(visit=={'invalid':True} and observations[group+'/'+phase+'/cargo.json.gz']['exit']==101,'invalid Cargo')
                    continue
                row=observations[group+'/'+phase+'/visit.json']
                native=observations[group+'/'+phase+'/native.json.gz']
                require(visit==row and row['allocation']==total and row['artifact_count']==375,'successful Cargo')
                key=(arm,row['branch']); signatures=(row['cli'],row['reader'],row['behavior'],native['typed'])
                require(same_role.setdefault(key,signatures)==signatures,'native or behavior changed within role and branch')
                require(bool(row['packed_count']) == (arm=='Packed' and phase!='empty-A'),'wrong object pack mode')
                if phase=='unchanged-B':
                    require(row['dirty']==0 and row['actual_execs']=={'native_cargo':1,'rustcs':[],'wild':0},'unchanged Cargo')
        for phase in GATED:
            row=contrasts[phase][i-1]
            measured={arm:amounts[f'triplet-{i:02}-{arm}',phase] for arm in ARMS}
            saved=measured['Full']-measured['Packed']
            require(row['absolute_bytes']==measured and row['saved_vs_full_bytes']==saved and saved>=32*MIB and 100*saved>=measured['Full'] and row['meets_gate'],'registered contrast')
    for phase in PHASES:
        medians=[statistics.median(amounts[f'triplet-{i:02}-{arm}',phase] for i in range(1,7))/MIB for arm in ARMS]
        print(phase,*(f'{value:.3f}' for value in medians))
    print('6 triplets, 126 physical ledgers, 108 native visits, 18 invalid builds, 24 registered comparisons')


if __name__=='__main__':
    main()
