"""Functional guard and corruption probes. Never used for paired wall scoring."""
import struct
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import os
from paired import ARM, MARK, FILE, Study, getargs, log_json

def full(r): return {x['crate'] for x in r['roster'] if x['mode']=='full'}
def mid(r): return {x['crate'] for x in r['roster'] if x['capture']}
def decode(data):
    count=struct.unpack_from('<I',data,6)[0];pos=10
    rows=[]
    def size():
        nonlocal pos
        value=struct.unpack_from('<I',data,pos)[0];pos+=4;return value
    for i in range(count):
        start=pos; pos+=1; length=size(); path=data[pos:pos+length];pos+=length
        flag=pos; chk=data[pos];pos+=1
        if chk:
            pos+=8;length=size();pos+=length
        rows.append((path,start,flag,pos))
    return rows,pos

def controls(s):
    s.references()
    watchers={'hold_bridge','hold_direct'}
    arm=s.init('inherit')
    for stage,who,want in [('fill-old','P',None),('inherit-old','C',watchers),('discover','C',watchers),('confirm','C',set()),('downgrade','P',watchers),('recover-old','C',watchers),('retrain','C',watchers),('recover-noop','C',set())]:
        r=s.run(arm,who,stage,trace=True);s.equivalent(r,s.gold[False])
        if want is not None: assert full(r)==want,(stage,full(r),want)
        if stage in ('discover','retrain'): assert mid(r)==watchers
    orig=arm/'src'/FILE; oldtime=orig.stat().st_mtime_ns
    # Test a real, backdated producer before data flow can be publicly unchanged.
    s.edit(arm,True);os.utime(orig,ns=(oldtime,oldtime))
    r=s.run(arm,'C','backdated-producer-now',trace=True);s.equivalent(r,s.gold[True])
    assert watchers <= full(r)
    s.edit(arm,False)
    r=s.run(arm,'C','earlier-producer',trace=True,packages=('hold_shapes',),check_product=False)
    assert full(r)=={'hold_shapes'}
    r=s.run(arm,'C','after-standalone-producer',trace=True);s.equivalent(r,s.gold[False])
    assert watchers<=full(r)
    # Only the contents of one reader's private receipt change in each test.
    for kind in ('missing-checksum','invalid-trailer','missing-receipt','legacy-trailer','corrupt-pending'):
        steady=s.run(arm,'C',kind+'-steady',trace=True)
        assert not steady['roster']
        fp=next(arm/path for path in steady['readers'] if path.endswith('dep-lib-hold_bridge'))
        data=fp.read_bytes();rows,pos=decode(data)
        if kind=='missing-checksum':
            _,_,flag,end=next(row for row in rows if b'libhold_shapes-' in row[0] and row[0].endswith(b'.rmeta'))
            fp.write_bytes(data[:flag]+bytes([0])+data[end:])
        elif kind=='invalid-trailer': fp.write_bytes(data[:-3])
        elif kind=='missing-receipt': fp.unlink()
        elif kind=='legacy-trailer': fp.write_bytes(data[:data.rindex(b'OBS1')])
        elif kind=='corrupt-pending':
            i=data.rindex(b'OBS1')+8; fp.write_bytes(data[:i]+bytes([0])+data[i+1:])
        first=s.run(arm,'C',kind+'-first',trace=True)
        assert full(first)=={'hold_bridge'},(kind, first['roster'])
        s.equivalent(first,s.gold[False])
        for i in range(2):
            last=s.run(arm,'C',kind+f'-restore-{i}',trace=True)
        assert not last['roster']
    # Real option change, opaque executable wrapper with no trusted runner semantics.
    arm=s.init('wrapped')
    wrapper=arm/'src'/'wrap';wrapper.write_text('#!/bin/sh\nexec "$@"\n');wrapper.chmod(0o755)
    env={'RUSTC_WRAPPER':str(s.active/'src/wrap')}
    for i in range(3):
        r=s.run(arm,'C',f'wrapper-{i}',trace=True,envadd=env)
        s.equivalent(r,s.gold[False])
        if i: assert watchers<=full(r) and not mid(r)
    # Use standard source mtimes for freshness. Marker still enables strict hashes on the readers.
    arm=s.init('mtime')
    extra=('-Zohm-worktree-seeds=no',)
    for i in range(3): r=s.run(arm,'C',f'mtime-{i}',extra=extra,trace=True)
    assert not r['roster']
    s.edit(arm,True)
    r=s.run(arm,'C','mtime-real-edit',extra=extra,trace=True)
    assert watchers<=full(r);s.equivalent(r,s.gold[True],require_elf=False)
    # Compile a unit whose two observed-run inputs are stable but whose command may check metadata only.
    arm=s.init('check-only')
    for i in range(4): r=s.run(arm,'C',f'check-{i}',mode='check',trace=True,check_product=False)
    assert not r['roster']
    s.edit(arm,True)
    r=s.run(arm,'C','check-real-edit',mode='check',trace=True,check_product=False)
    assert watchers<=full(r)
    arm=s.init('test-no-run')
    for i in range(4): r=s.run(arm,'C',f'test-no-run-{i}',mode='test --no-run',trace=True,check_product=False)
    assert not r['roster']
    s.edit(arm,True)
    r=s.run(arm,'C','test-no-run-real-edit',mode='test --no-run',trace=True,check_product=False)
    assert watchers<=full(r)
    log_json(s.logs/'controls-passed.json',{'passed':list(s.results),'subjects':s.digest})
if __name__=='__main__':
    controls(Study(getargs()))
