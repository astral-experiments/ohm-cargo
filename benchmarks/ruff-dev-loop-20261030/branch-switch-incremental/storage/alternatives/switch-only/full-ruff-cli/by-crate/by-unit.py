"""Group the already measured final incremental bytes by rustc crate directory."""
import argparse,collections,gzip,hashlib,json,re
from pathlib import Path

def hash_file(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def read_case(packet,arm,phase):
    raw=packet/'classes'/(arm+'-storage--unchanged-B.jsonl.gz')
    assert hash_file(raw)==phase['category']['compressed_sha256']
    by={c:collections.Counter() for c in ('native-object','rust-metadata','other-regular')}
    remainder=collections.Counter()
    with gzip.open(raw,'rb') as f:
        for line in f:
            row=json.loads(line);classes={c for _,c in row['names']}
            if len(classes)!=1 or not classes<=by.keys():continue
            c=classes.pop();owners=set();base=set();has_inc=False
            for n,_ in row['names']:
                parts=Path(n).parts
                if 'incremental' not in parts:continue
                has_inc=True
                tail=parts[parts.index('incremental')+1:]
                if len(tail)<2:continue
                if re.fullmatch('[0-9a-f]{16}',tail[0]) and (m:=re.fullmatch(r'([A-Za-z0-9_]+)-[a-z0-9]{7,24}',tail[1])):
                    owners.add(m[1])
                base.add(tail[-1].removeprefix('ohm-build-'))
            if not owners:owners={'unknown-incremental' if has_inc else 'outside-incremental'}
            # Crates with multiple units retain one displayed crate name. Mixed names stay explicit.
            amount=row['signature'][5]*512
            by[c]['+'.join(sorted(owners))]+=amount
            if c=='other-regular':remainder['+'.join(sorted(base)) if base else 'outside-incremental']+=amount
    for c,series in by.items():assert sum(series.values())==phase['category']['classes'][c]['bytes']
    assert sum(remainder.values())==sum(by['other-regular'].values())
    return {**by,'other-regular-by-basename':remainder}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('packet',type=Path);args=p.parse_args();packet=args.packet
    assert hash_file(packet/'SHA256SUMS')=='f0299ce8b1d2cf598f35aef59f460e99b428e2a01873e2ca9623a293d24e52f0'
    assert hash_file(packet/'observations.json')=='ea5cc3119114d559d781c75abd76c43e7fd88a2e2dbf443a470a61e4335af651'
    obs=json.loads((packet/'observations.json').read_bytes());row={m:read_case(packet,m,obs['slots'][m+'-storage']['phase']['unchanged-B']) for m in ('off','on')}
    out={}
    for category in row['off']:
        off,on=(row[m][category] for m in ('off','on'))
        out[category]=sorted([{'name':k,'off':off[k],'on':on[k],'delta':on[k]-off[k]} for k in off.keys()|on.keys() if on[k]!=off[k]],key=lambda x:(-abs(x['delta']),x['name']))
        assert sum(x['delta'] for x in out[category])==sum(on.values())-sum(off.values())
    print(json.dumps(out,sort_keys=True,indent=2))
if __name__=='__main__':main()
