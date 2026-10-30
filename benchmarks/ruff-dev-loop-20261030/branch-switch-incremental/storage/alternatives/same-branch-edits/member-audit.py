#!/usr/bin/env python3
"""Read complete retained rlibs; compare each native object multiset with the independently empty sources."""
from collections import Counter
from pathlib import Path
import argparse
import gzip
import hashlib
import json

def sh(data):
    return hashlib.sha256(data).hexdigest()
def fingerprint(items):
    return sh(json.dumps(sorted(items),separators=(',',':')).encode())
def archive(path, expected):
    body=path.read_bytes();assert sh(body)==expected and body.startswith(b'!<arch>\n')
    members={};special=[];pos=8;names=b''
    while pos<len(body):
        head=body[pos:pos+60];assert len(head)==60 and head[-2:]==bytes([96,10])
        length=int(head[48:58]);name=head[:16].strip();chunk=body[pos+60:pos+60+length];assert len(chunk)==length
        pos+=60+length+length%2
        if name in (b'//',b'/',b'/SYM64/'):
            special.append([name.decode(),len(chunk),sh(chunk)])
            if name==b'//':names=chunk
            continue
        if name.startswith(b'/') and name[1:].isdigit():
            s=int(name[1:]);name=names[s:names.index(b'/\n',s)]
        elif name.startswith(b'#1/'):
            cut=int(name[3:]);name=chunk[:cut].rstrip(b'\0');chunk=chunk[cut:]
        else:name=name.rstrip(b'/')
        name=name.decode();assert name not in members
        members[name]=(len(chunk),sh(chunk))
    assert pos==len(body)
    meta={n:v for n,v in members.items() if n in ('lib.rmeta','lib.rmeta-link')}
    objects={n:v for n,v in members.items() if n.endswith('.rcgu.o')}
    assert len(meta)==2 and len(meta)+len(objects)==len(members)
    return {'bytes':len(body),'meta':meta,'cgu_count':len(objects),'cgu_names':fingerprint(objects.keys()),'cgu_payloads':fingerprint(objects.values()),'ar_tables':fingerprint(special),'all_members':fingerprint(members.values())}
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('raw_root',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args();root=args.raw_root.resolve();r=root/'independent'
    raw=(r/'results.json.gz').read_bytes();expect=json.loads((r/'verified.json').read_bytes());assert sh(raw)==expect['projection']
    full=json.loads(gzip.decompress(raw));cache={};phases=[]
    for state, entries in sorted(full['all_raw_rcu'].items()):
        refs=full['clean'][state]['rlibs']
        for entry in entries:
            role=entry['role']
            for crate, receipt in sorted(entry['members'].items()):
                h=receipt['sha']
                for hh in (h,*(ref[crate]['sha'] for ref in refs.values())):
                    if hh not in cache:cache[hh]=archive(root/'full-outputs'/hh,hh)
                current=cache[h];assert current['bytes']==receipt['bytes'] and current['all_members']==receipt['payload_multiset']
                choices={}
                for testrole, rr in refs.items():
                    other=rr[crate]['sha'];base=cache[other]
                    choices[testrole]={'same_raw':h==other,'same_cgu_payloads':base['cgu_payloads']==current['cgu_payloads'],'same_cgu_names':base['cgu_names']==current['cgu_names'],'changed_metadata':[n for n in current['meta'] if current['meta'][n]!=base['meta'][n]],'same_ar_tables':base['ar_tables']==current['ar_tables']}
                phases.append({'slot':entry['slot'],'role':role,'phase':entry['phase'],'source':state,'crate':crate,'sha':h,'objects':current['cgu_count'],'references':choices})
    assert len(phases)==130
    data={'compact_projection':expect['projection'],'verifier':sh(Path(__file__).read_bytes()),'physical_ar_files':cache,'entries':phases}
    body=json.dumps(data,sort_keys=True,separators=(',',':')).encode()
    assert all(p not in body for p in (b'/home/',b'/mnt/',b'/run/user/',b'.openai.org'))
    with args.output.open('xb') as f:f.write(gzip.compress(body,compresslevel=9,mtime=0))
    for k in ('ruff_python_ast','ruff_python_parser'):
        ds=[e for e in phases if e['crate']==k and e['slot'].startswith('pair-')]
        print(k,'phases',len(ds),'objects',sorted({e['objects'] for e in ds}),'all-native-same',sum(all(ref['same_cgu_payloads'] for ref in e['references'].values()) for e in ds),'same-names',sum(e['references']['P']['same_cgu_names'] for e in ds),'raw-same',sum(e['references']['P']['same_raw'] for e in ds),'metadata differences',Counter(tuple(e['references']['P']['changed_metadata']) for e in ds))
    print('verified',len(cache),'physical rlibs',sum(row['bytes'] for row in cache.values()),'bytes',sh(args.output.read_bytes()))
if __name__=='__main__':main()
