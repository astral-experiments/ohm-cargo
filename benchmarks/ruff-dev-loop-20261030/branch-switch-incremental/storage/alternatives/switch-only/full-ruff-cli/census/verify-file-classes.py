"""Verify all physical namespace listings without access to the acquisition host."""
from pathlib import Path
import collections,gzip,hashlib,importlib.util,json,os,re,stat,sys
C=Path(__file__).resolve().parent
sp=importlib.util.spec_from_file_location('category_reader',C/'meter.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
def one(path,expected,phase):
    compressed=path.read_bytes();assert hashlib.sha256(compressed).hexdigest()==expected['compressed_sha256']
    raw=gzip.decompress(compressed);assert hashlib.sha256(raw).hexdigest()==expected['raw_sha256']
    rows=[json.loads(v) for v in raw.splitlines()]
    assert len(rows)==expected['unique_inodes'] and len(rows)==len({(r['device'],r['ino']) for r in rows})
    names={};inc=both=all_bytes=0
    for r in rows:
        sig=tuple(r['signature']);assert len(sig)==8 and sig[0:2]==(r['device'],r['ino']) and sig[4]>=0 and sig[5]>=0
        ty=m.KIND.get(stat.S_IFMT(sig[2]),'other-special');assert ty==r['kind']
        paths=r['names'];assert paths
        for n,cls in paths:
            f=Path(n);assert n not in names and not f.is_absolute() and '..' not in f.parts and f.parts[0] in ('products','shared')
            assert m.classify(f.parts,r['format'],r['kind'])==cls
            names[n]=sig
        charged=sig[5]*512;all_bytes+=charged
        im=any('incremental' in Path(n).parts for n,_ in paths)
        if im:inc+=charged
        if {Path(n).parts[0] for n,_ in paths}=={'products','shared'}:both+=charged
    hh=hashlib.sha256()
    for nm in sorted(names,key=lambda f:tuple(os.fsencode(n) for n in Path(f).parts)):
        hh.update(os.fsencode(nm)+b'\0'+str(names[nm]).encode()+b'\n')
    assert hh.hexdigest()==expected['physical_ledger_sha256']==phase['whole_ledger'] and len(names)==expected['source_paths']==phase['paths']
    result=m.summarize(rows)
    assert all(result[v]==expected[v] for v in ['classes','slices','regular_with_unseen_nlink']) and expected['all_checks']
    assert (all_bytes,inc,both)==tuple(phase['settled'][k] for k in ('all','all_incremental','both_roots_same_inode'))
    for k,cat in [('packed','packed-query-and-dep-tables'),('raw','raw-query-and-dep-tables')]:
        rr=[r for r in rows if any(n==cat for _,n in r['names'])]
        assert len(rr)==phase['tables'][k]['unique_inodes'] and sum(r['signature'][5]*512 for r in rr)==phase['tables'][k]['allocated']
    return result
def verify(p):
    valid={};unsup={}
    for slot,arm in p['slots'].items():
        for tag,phase in arm['phase'].items():
            if 'category_error' in phase:unsup[slot+'/'+tag]=phase['category_error'];continue
            key=slot+'--'+tag
            valid[key]=one(C/'classes'/(key+'.jsonl.gz'),phase['category'],phase)
    assert set(p.name for p in (C/'classes').iterdir())==set(k+'.jsonl.gz' for k in valid)
    return valid,unsup
if __name__=='__main__':
    p=json.loads((C/'observations.json').read_bytes());v,e=verify(p);print(json.dumps({'settled_visits':len(v),'failures':e},sort_keys=True))
