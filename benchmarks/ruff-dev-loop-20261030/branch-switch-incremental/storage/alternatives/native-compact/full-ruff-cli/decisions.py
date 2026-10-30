#!/usr/bin/env python3
"""Decode finalized incremental session checkout keys and compare the two packing predicates."""
import collections,hashlib,json,re,sys
from pathlib import Path
M=(1<<64)-1
def rot(x,i):return ((x<<i)|(x>>(64-i)))&M
def rounds(s):
    a,b,c,d=s;a=(a+b)&M;b=rot(b,13)^a;a=rot(a,32);c=(c+d)&M;d=rot(d,16)^c
    a=(a+d)&M;d=rot(d,21)^a;c=(c+b)&M;b=rot(b,17)^c;c=rot(c,32)
    return a,b,c,d
def hasher(data,stable128=False):
    """Match pinned std's zero-key DefaultHasher::write (SipHash-1-3)."""
    a,b,c,d=0x736f6d6570736575,0x646f72616e646f6d,0x6c7967656e657261,0x7465646279746573
    if stable128:b^=0xee
    chunks=[int.from_bytes(data[i:i+8],'little') for i in range(0,len(data)//8*8,8)]
    remainder=data[len(data)//8*8:];chunks.append(((len(data)&255)<<56)|int.from_bytes(remainder,'little'))
    for x in chunks:
        a,b,c,d=rounds((a,b,c,d^x));a^=x
    c^=0xee if stable128 else 255
    for i in range(3):a,b,c,d=rounds((a,b,c,d))
    return f'{a^b^c^d:016x}'
def stable_crate_directory(crate,metadata,ctype,version):
    # Hash64 is the first lane of stable SipHash-1-3-128. StableCrateId::new hashes
    # the string, all sorted/deduplicated metadata, crate kind, and full compiler version.
    q=crate.encode()+b'\xffmetadata'
    for token in sorted(set(metadata)):
        raw=token.encode();q+=len(raw).to_bytes(8,'little')+raw
    q+=b'exe' if 'bin' in ctype.split(',') else b'lib'
    val=int(hasher(q+version.encode(),stable128=True),16);key=''
    for _ in range(13):
        val,ii=divmod(val,36);key='0123456789abcdefghijklmnopqrstuvwxyz'[ii]+key
    assert val==0
    return crate+'-'+key
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):return json.loads(p.read_bytes())
def switches(args):
    out={}
    for i,v in enumerate(args):
        kv=args[i+1] if v=='-C' else v[2:] if v.startswith('-C') else ''
        for k in ['incremental','metadata','extra-filename']:
            if kv.startswith(k+'='):out[k]=kv[len(k)+1:]
    return out
def rustc_units(d,version):
    jobs=read(d/'physical-native.json');out={}
    for j in jobs:
        if j['role']!='SDK rustc':continue
        args=j['argv'];co=switches(args)
        if 'incremental' not in co:continue
        path=Path(co['incremental']);parts=path.parts
        if 'canonical' not in parts:continue
        ix=parts.index('canonical');logical='/'.join(parts[ix+1:])
        assert logical.startswith(('products/','shared/'))
        k=(j['crate'],co['metadata'],logical)
        assert k not in out,k
        ctype=next((v.split('=',1)[1] for v in args if v.startswith('--crate-type=')),None)
        if ctype is None and '--crate-type' in args:ctype=args[args.index('--crate-type')+1]
        metadata=[v[len('metadata='):] for i,v in enumerate(args) if i and args[i-1]=='-C' and v.startswith('metadata=')]
        assert metadata==[co['metadata']] and ctype,k
        out[k]=dict(crate=j['crate'],metadata=co['metadata'],incremental=logical,crate_type=ctype,crate_directory=stable_crate_directory(j['crate'],metadata,ctype,version))
    return out
def parsed(name):
    a=re.fullmatch(r's-([a-z0-9]+)-(_([0-9a-f]{16})_)?([a-z0-9]+)-([a-z0-9]+)',name)
    assert a,name
    return int(a[1],36),a[3]
def per_unit(ledger,unit):
    root=Path(unit['incremental']);out={}
    for name,typ in ledger['paths'].items():
        p=Path(name)
        if not p.is_relative_to(root):continue
        segs=p.relative_to(root).parts
        if len(segs)!=2 or segs[0]!=unit['crate_directory']:continue
        t,tag=parsed(segs[-1]);files={}
        for packed,allocated,size,aliases in ledger['inode_aliases']:
            for logical in aliases:
                a=Path(logical)
                if a.parent!=p:continue
                assert a.name not in files and size>0
                files[a.name]={'packed':packed,'bytes':size,'allocated':allocated,'names_of_inode':len(aliases)}
        assert files and set('packed' if a['packed'] else 'raw' for a in files.values())==set(typ)
        out[segs[-1]]={'crate_dir':segs[0],'timestamp_us':t,'checkout_key':tag,'tables':typ,'files':files}
    return out
def calculate(r):
    order=['empty-A','first-B','return-A','return-B','unchanged-B'];f=r/'runs/on-storage';labels={k:hasher(b'ref: refs/heads/'+n) for k,n in [('A',b'historical-parent'),('B',b'historical-feature')]}
    assert labels['A']!=labels['B']
    records={k:read(f/k/'result.json') for k in order};scans={k:read(f/k/'table-ledger.json') for k in order}
    version=(f/'rustc-version.txt').read_text().splitlines()[0].removeprefix('rustc ');assert version=='1.99.0-dev (9f8db07b6 2026-10-29) (ohm-ruff-lint-scout)'
    by_phase={k:rustc_units(f/k,version) for k in order}
    wanted=by_phase['first-B']
    assert len(wanted)==20 and all(set(by_phase[k])==set(wanted) for k in ['return-A','return-B'])
    assert not by_phase['unchanged-B'] and not records['unchanged-B']['physical']
    result=[]
    for key,unit in sorted(wanted.items()):
        assert key in by_phase['empty-A'],key
        stages={k:per_unit(scans[k],unit) for k in order}
        last={};rows=[]
        for phase in order:
            current=stages[phase];rev=phase.split('-')[-1]
            assert len({v['crate_dir'] for v in current.values()})==1,(phase,unit,current)
            newest=max(last.values(),key=lambda v:v['timestamp_us']) if last else None
            assert not last or len({v['timestamp_us'] for v in last.values()})==len(last)
            old=any(v['checkout_key'] is not None and v['checkout_key']!=labels[rev] for v in last.values())
            same_t=max((v['timestamp_us'] for v in last.values() if v['checkout_key'] in (None,labels[rev])),default=-1)
            other_t=max((v['timestamp_us'] for v in last.values() if v['checkout_key'] not in (None,labels[rev])),default=-1)
            new=bool(last) and other_t>same_t
            arrived=set(current)-set(last)
            transitioned=phase!='unchanged-B'
            if transitioned:
                assert len(arrived)==1 and current[next(iter(arrived))]['checkout_key']==labels[rev],(phase,unit,arrived)
                observed=current[next(iter(arrived))]['tables']
                assert (observed==['packed'])==old,(phase,unit,old,observed)
                if newest:assert current[next(iter(arrived))]['timestamp_us']>newest['timestamp_us']
            else:
                assert current==last and not arrived
            rows.append({'phase':phase,'active_checkout':rev,'rustc_ran':transitioned,'before':last,'after':current,'new_sessions':sorted(arrived),'previous_newest':newest,'older_policy_if_invoked':old,'switch_policy_if_invoked':new,'same_decision_exercised':old==new if transitioned else None})
            last=current
        result.append({'unit':unit,'stages':rows})
    return {'cfg_version':version,'rustc_version_receipt':sha(f/'rustc-version.txt'),'compiler_that_ran':'8ea2252344ba85e7406f4f04f979053e2bd191b1','counterfactual_compiler':'08d49cba6aacb0cac27a96eea335ed1c7439f483','checkout_keys':labels,'units':result,'source_blobs':{'8ea_fs':'fc9ebb14bf974ad9cd86371d926f59c62f2dfea9','08d49_fs':'2c9ba9c02cc657ef34c05b3fd88c215ce4c000fd','std_default_hasher':'b9c21ab2d6a650c00f9963eccb9207b3153bb08e','core_siphash':'bc74bd0e085ffc706994101256db461f86f7545f'},'row_sources':{k:{x:sha(f/k/x) for x in ['physical-native.json','table-ledger.json','result.json']} for k in order}}
if __name__=='__main__':print(json.dumps(calculate(Path(sys.argv[1])),sort_keys=True,separators=(',',':')))
