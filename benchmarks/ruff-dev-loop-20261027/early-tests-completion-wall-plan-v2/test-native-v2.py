"""Resume the pre-timing ELF checks against the original cold files and finish the remaining arm."""
from pathlib import Path
import hashlib
import importlib.util
import json
import mmap
import os
import shutil
import struct
import tempfile
import traceback

p=Path('/mnt/devbox-scratch/dev-user/ohm-early-completion-20261027')
prior=p/'run-native-v1/run.py'
def sha(b):return hashlib.sha256(b).hexdigest()
def load(f):return json.loads(f.read_bytes())
def normalize(path):
    with path.open('rb') as s,mmap.mmap(s.fileno(),0,access=mmap.ACCESS_READ) as b:
        assert b[:6]==b'\x7fELF\x02\x01'
        sh=struct.unpack_from('<Q',b,40)[0];size,num,idx=struct.unpack_from('<HHH',b,58);assert size==64 and num>idx
        entries=[struct.unpack_from('<IIQQQQIIQQ',b,sh+size*i) for i in range(num)];strings=entries[idx][4];limit=strings+entries[idx][5]
        sections={}
        for i,k in enumerate(entries):
            start=strings+k[0];end=b.find(b'\0',start,limit)
            assert strings<=start<=end<limit
            sections[b[start:end].decode()]=(i,k)
        i,ro=sections['.rodata'];_,note=sections['.note.gnu.build-id'];off=note[4];n,ds,kind=struct.unpack_from('<III',b,off)
        assert note[1]==7 and n==4 and kind==3 and b[off+12:off+16]==b'GNU\x00' and 8<=ds<=64
        assert ro[9] in (0,1,2,4,8,16,32,64,128,256)
        h=hashlib.sha256();lo=0
        for start,length in sorted([(off+16,ds),(sh+i*size+56,8)]):
            assert start>=lo and start+length<=len(b)
            h.update(memoryview(b)[lo:start]);h.update(bytes(length));lo=start+length
        h.update(memoryview(b)[lo:])
        return dict(bytes=len(b),normalized=h.hexdigest(),build_id=b[off+16:off+16+ds].hex(),rodata_entsize=ro[9])

def selftest():
    src=Path('/bin/true');raw=src.read_bytes();sh=struct.unpack_from('<Q',raw,40)[0]
    size,num,idx=struct.unpack_from('<HHH',raw,58);heads=[struct.unpack_from('<IIQQQQIIQQ',raw,sh+size*i) for i in range(num)]
    names=heads[idx][4];sections={raw[names+k[0]:raw.index(0,names+k[0])].decode():(i,k) for i,k in enumerate(heads)}
    old=normalize(src);idx,head=sections['.rodata'];_,note=sections['.note.gnu.build-id'];_,code=sections['.text']
    with tempfile.TemporaryDirectory() as tmp:
        f=Path(tmp)/'copy';m=bytearray(raw)
        m[note[4]+16]^=1;struct.pack_into('<Q',m,sh+size*idx+56,0 if head[9] else 8);f.write_bytes(m)
        narrow=normalize(f);assert narrow['normalized']==old['normalized'] and narrow['build_id']!=old['build_id'] and narrow['rodata_entsize']!=old['rodata_entsize']
        m[code[4]]^=1;f.write_bytes(m);assert normalize(f)['normalized']!=old['normalized']
    return {'identical_control':True,'two_permitted_fields':True,'different_text_rejected':True}

if __name__=='__main__' and __import__('sys').argv[1:]==['selftest']:
    print(json.dumps(selftest()));raise SystemExit(0)
assert sha(prior.read_bytes())=='b25c84e668536de89cc63972faef368afb0e3e8f213381cc100807ab490fb703'
spec=importlib.util.spec_from_file_location('previous',prior);old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
old.normalize=normalize
q=old.q;roles=old.roles;executables=old.executables;compare=old.compare;list_test=old.list_test;special=old.special
o=p/'matching-scheduler-native-v2'

def main():
    assert (p/'run-native-v1/exit').read_text()=='1' and "has no attribute 'index'" in (old.o/'failure.txt').read_text()
    assert not (old.o/'cold-C').exists() and not (old.o/'cold-state-C').exists() and not (old.o/'complete.json').exists()
    assert not o.exists() and shutil.disk_usage(p).free>75*2**30
    assert (p/'run-ruff-v1/exit').read_text()=='0' and {k:q.sha(v) for k,v in executables.items()}==roles
    os.sched_setaffinity(0,set(range(16)));q.source_gate();o.mkdir(mode=0o700)
    q.put(o/'selftest.json',selftest());oldprogress=load(old.o/'progress.json');assert set(oldprogress['results']['selection'])==set('ABC') and set(oldprogress['results']['cold'])=={'A'}
    # Every preceding native command and published output is reused in place.
    for w in ('selection','cold'):
        for a in 'ABC':
            if w=='cold' and a=='C':continue
            for state in ('','-state'):
                n=w+state+'-'+a
                src=q.lab/('official-selection-control' if state else 'official-selection') if n in ('selection-A','selection-state-A') else old.o/n
                assert src.is_dir();(o/n).symlink_to(src,target_is_directory=True)
    results=oldprogress['results'];comparisons=oldprogress['comparisons']
    inputs={'original_failure':q.sha(old.o/'failure.txt'),'previous_progress':q.sha(old.o/'progress.json'),'reused':{}}
    for w,a in (('selection','A'),('selection','B'),('selection','C'),('cold','A'),('cold','B')):
        d=o/(w+'-'+a);assert (d/'product.json').is_file() and (d/'physical.json').is_file()
        inputs['reused'][w+'-'+a]={k:q.sha(d/k) for k in ('command.json','product.json','physical.json','stdout','stderr','test-list.stdout','test-list.stderr')}
    q.put(o/'continuation.json',inputs)
    base=load(o/'cold-A/product.json')
    for arm in 'BC':
        t=o/('cold-state-'+arm);out=o/('cold-'+arm)
        if arm=='B':
            print('checking existing cold parent ELF bytes',flush=True)
            r=load(out/'product.json');v=load(out/'physical.json')
            test_list=dict(stdout=q.sha(out/'test-list.stdout'),stderr=q.sha(out/'test-list.stderr'),exit=0)
        else:
            print('cold C',flush=True);q.state(t);r=q.run(t,executables[arm],q.select,out,trace=True)
            v=old.audit(out);test_list=list_test(t,executables[arm],r,out,None)
        for name,h in r['native'].items():assert q.sha(q.printed(t,name))==h
        assert len(r['dirty'])==619 and not r['ty_server']['fresh']
        own=r['ty_server'];calls=v['integration'][special];links=v['target_link_groups'][r['e2e'][0]]
        assert len(calls) in (1,2) and all(len(g['ty_extern'])==1 and Path(g['ty_extern'][0].split('=',1)[1]).name==Path(own['path']).name for g in calls)
        comparisons['cold/'+arm]=compare(base,r,o/'cold-state-A',t)
        assert results['cold']['A']['test_list']==test_list
        results['cold'][arm]=dict(physical=dict(compiles=v['rustc'],count=v['total'],distinct=v['distinct'],wild=v['actual_wild'],distinct_wild=v['distinct_wild'],
            duplicated_sources=sorted(g[0]['source'] for g in v['repeated'].values())),test_list=test_list,e2e_calls=calls,e2e_links=links,
            product=q.sha(out/'product.json'),roster=r['roster'],e2e=r['native'][r['e2e'][0]],ty_server=own)
        q.put(o/'progress.json',dict(results=results,comparisons=comparisons))
    b=results['cold']['B']['physical'];c=results['cold']['C']['physical']
    assert b['distinct']==c['distinct'] and b['distinct_wild']==c['distinct_wild'] and b['count']>c['count'] and b['wild']>c['wild']
    assert all(results['selection'][a]['e2e']!=results['cold'][a]['e2e'] for a in 'ABC')
    for key,files in inputs['reused'].items():assert all(q.sha(o/key/name)==h for name,h in files.items())
    q.source_gate();q.put(o/'complete.json',dict(results=results,comparisons=comparisons,all_tests_executed_during_build=0,
        continuation=q.sha(o/'continuation.json'),selftest=q.sha(o/'selftest.json')))
    print('all six native comparisons passed',flush=True)

if __name__=='__main__':
    try:main()
    except BaseException:
        if o.is_dir():(o/'failure.txt').write_text(traceback.format_exc())
        raise
