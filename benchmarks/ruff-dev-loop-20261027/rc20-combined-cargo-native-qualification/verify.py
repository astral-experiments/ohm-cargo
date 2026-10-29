"""Verify the 81 native qualifications and exercise fail-closed mutations of the projected result."""
from collections import Counter
import copy
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys

P=Path(__file__).resolve().parent
digest=lambda b:hashlib.sha256(b).hexdigest()
sha=lambda p:digest(p.read_bytes())
is_hash=re.compile('[0-9a-f]{64}').fullmatch
fixed='967f5f1db2938847fac22d78dc222054cbb143a5fabcffcad0bd15f8929b47e9'
released='02a86ebd2d9e4f237b33f212102b81ed145eb77fae090d67e379cb6f1d70a573'
r19='5694abe50767a22cebeccb767143f7404d5e81c4b1760cff4426466bf410e511'
r18='c6ab483d6698f68eebb49d74b27361f3e02ede55452dc0416c3fdec9a45b7f60'
wild='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'

def verify(m,assembly,w,b):
    im=b['image']
    assert im['binary_sha256']==fixed and im['size']==43361392 and im['commit']=='2fe90823d8eadc95de56c2cde8d41e0082aac0eb' and im['tree']=='99f8de907ed0bfe7ccab4b22cbebd74b25bb010d'
    assert im['profile_sha256']=='481ada8a40c70dad11b3c7e8871e9a52207d78447ca5e8ace06fc4aec2d2b5a7' and im['git_parent']=='8dc33c9cc641e2b641c5b8e7075652a3e9e1f70b'
    assert b['sdk19']['rustc']==r19 and b['sdk18']['rustc']==r18 and b['sdk18']['cargo']==released
    assert b['sdk18']['wild']==b['sdk19']['wild']==wild
    for n in ('18','19'):
        assert all(b['sdk'+n][k]==v for k,v in b['runtimes'][n].items())
    assert 'commit-hash: '+im['commit'] in b['versions']['mode19']['cargo']
    assert all(r['exit']==0 for r in b['raw_host_receipts']['rows'])
    assert len(m)==46 and len(assembly)==18 and sum(len(row['phases'])for row in w.values())==17
    assert sum(len(r['trace_files']) for r in m)==1522
    inputs={(r['study'],r['arm'],r['phase']):r for r in m};assert len(inputs)==46
    orig=(P/'fixture/probe/src/main.rs').read_bytes()
    modes={'default':17,'no':29};elves={k:inputs['matrix',k,'initial']['elf_sha256']for k in modes};assert len(set(elves.values()))==2
    totals=Counter()
    def case(study,arm,phase,mode,roots,native,rc,runtime,elf,evicted=False):
        row=inputs.pop((study,arm,phase));assert row['mode']==mode and row['exit']==rc and row['success']==(rc==0) and row['runtime']==runtime and row['elf_sha256']==elf
        assert row['cargo']==('shipped18' if study=='diagnostic18'else 'combined')
        assert is_hash(row['stdout_sha256'])and is_hash(row['stderr_sha256'])
        if study!='matrix':
            assert row['evicted_short_fingerprint']==evicted and bool(row['evicted_sha256'])==evicted
            if evicted:assert is_hash(row['evicted_sha256'])
        else:assert row['source_sha256']==digest(orig+(b'fn force_real_build() -> bool { true }\n' if phase=='edit' else b''))
        root='probe' if study=='matrix'else'consumer';others={'origin','facade'}if study=='matrix'else{'report','facade'}
        es=row['execs'];kinds=Counter(e['kind']for e in es);totals.update(kinds)
        seen=Counter(e['file']for e in es);traces=row['trace_files']
        assert set(seen)<={t['file']for t in traces}and len({t['file']for t in traces})==len(traces) and all(is_hash(t['sha256']) and t['recorded_execs']==seen[t['file']] for t in traces)
        assert all(is_hash(e['execve_line_sha256'])and is_hash(e['argv_nul_sha256'])and e['argc']>0 for e in es)
        assert kinds['cargo']==kinds['cargo-proxy']==1 and kinds['cc']==kinds['collect2']==kinds['wild']==native
        actual=[e for e in es if e['kind']=='rustc'];assert Counter(e['crate']for e in actual)==Counter(roots)
        for e in actual:
            if e['crate']==root:assert e['recipe']==(mode!='no') and e['temps_dir']==(mode!='no') and set(e['externs'])=={'facade'} and e['source_args']==[root+'/src/main.rs']
        arts=row['artifacts'];assert {a['name']for a in arts}==others|({root}if not rc else set()) and {a['name']for a in arts if not a['fresh']}==set(roots)-({root}if rc else set())
        assert row['errors']==([{'message':'link recipe was not requested','code':None,'primary':[['consumer/src/main.rs',1,28]]}]if rc else [])
        if rc:assert elf is None and runtime is None
        else:assert is_hash(elf)
    for f,o in [('default','no'),('no','default')]:
        for n,ph in enumerate(['initial','initial-repeat','switch','switch-repeat','edit','restore','restore-repeat']):
            mode=f if n<2 else o;cs=['origin','facade','probe'] if n==0 else ['probe']if n in (2,4,5)else[]
            case('matrix',f,ph,mode,cs,2 if n==0 else int(bool(cs)),0,modes[mode],elves[mode])
    for fam in ('diagnostic19','diagnostic18'):
        okelf=inputs[fam,'implicit','start']['elf_sha256']
        for arm,base in [('implicit','default'),('explicit','yes')]:
            case(fam,arm,'start',base,['report','facade','consumer'],2,0,17,okelf);case(fam,arm,'unchanged',base,[],0,0,17,okelf)
            for ph in ('switch','switch-repeat'):
                if fam=='diagnostic18':case(fam,arm,ph,'no',[],0,0,17,okelf)
                else:case(fam,arm,ph,'no',['consumer'],0,101,None,None)
            if fam=='diagnostic18':case(fam,arm,'evict-cargo-fingerprint','no',['consumer'],0,101,None,None,True)
            case(fam,arm,'restore',base,['consumer'],1,0,17,okelf);case(fam,arm,'restore-repeat',base,[],0,0,17,okelf)
        case(fam,'empty','no','no',['report','facade','consumer'],1,101,None,None);case(fam,'empty','repeat','no',['consumer'],0,101,None,None);case(fam,'empty','recover','default',['consumer'],1,0,17,okelf)
    assert not inputs and totals=={'cargo':46,'cargo-proxy':46,'rustc':44,'rustc-query':48,'cc':26,'collect2':26,'wild':26}
    ars={(r['arm'],r['phase']):r for r in assembly};assert len(ars)==18
    original=ars['default','01-cold'];changed=ars['default','04-independent-clean'];assert original['elf']!=changed['elf'] and original['source']!=changed['source']
    phases=['01-cold','02-unchanged','03-edit-and-new-asset','04-independent-clean','05-forced-full-keep-incremental','07-source-restore-missing-asset','08-independent-missing','09-forced-same-missing','10-recovered']
    for arm in ['default','explicit-yes']:
        for ix,ph in enumerate(phases):
            r=ars.pop((arm,ph));real=r['real_processes'];units=[e for e in real if e['type']=='rustc'and e['unit']=='reader'];ls=[e for e in real if e['type']=='linker'];bad=arm=='explicit-yes' and ix in (2,5)
            success=ix not in (5,6,7) or bad;missing=ix in (5,6,7)
            native=(17 if ix in (0,1,8)or bad and ix==2 else 29)if success else None;rust=(10 if ix in (2,3,4)else 6)if success else None
            assert (r['status'],r['native'],r['rust'],r['tests_passed'])==(0 if success else 101,native,rust,1 if success else None)
            assert r['target_source']==original['target_source'] and r['source']==(changed['source']if ix in (2,3,4)else original['source'])
            assert r['asset']==(None if missing else digest(bytes([29 if ix in (2,3,4)else 17])))
            assert r['empty']==(ix in (0,3,6)) and r['typed'] and all(is_hash(x)for x in r['raw'].values())
            obs=r['opens']
            if ix==1: assert not real and not obs and all(f for _,f in r['typed'])
            elif bad: assert len(units)==1 and all(e['link_only']for e in units) and len(ls)==1 and not obs
            else:
                assert units and all(not u['link_only']and not u['incremental']for u in units)
                assert obs and all(o['nearest_compiler']=='reader' and o['missing']==missing and o['open_successful']!=missing and is_hash(o['line'])for o in obs)
                assert bool(ls)==success
            assert all(e['exe']==(r19 if e['type']=='rustc' else wild) and is_hash(e['line'])and is_hash(e['argv_nul_sha256'])for e in real)
            assert all(not x['mentions_payload'] for x in r['depinfo'])
            if not success:assert r['diagnostic_mentions_incbin']and not r['elf']
            elif bad:assert is_hash(r['elf'])and r['elf']not in (original['elf'],changed['elf'])
            else:assert r['elf']==(changed['elf']if ix in (2,3,4)else original['elf'])
    assert not ars and sum(len([f for f in r['raw']if f.startswith('trace.')])for r in assembly)==741
    assert set(w)=={'public-api','resolve','provenance','check-hint','manifest'}
    for n,j in w.items():
        js=j['received'];phases=j['phases'];assert j['raw']['exit']==0 and all(is_hash(j['raw'][key])for key in ('stdout','stderr','result_sha256'))
        if n=='manifest':rs=js;expect=['cold','during','before']
        elif n in ('resolve','public-api'):
            rs=js['records'];expect=['cold','changed','repeat']
            assert js['before_sha']==js['after_sha'] and js['inode_preserved']and not js['sentinel_replaced']and not js['cache_symlink']
        else:rs=js['rows'];expect=['cold','during','before','repeat']
        assert [r['phase']for r in rs]==expect
        for ix,r in enumerate(rs):
            ph=r['phase'];saved=phases[ph];sent=saved['sentinel'];assert sent['phase']==ph and sent['is_regular']and sent['size']>0 and is_hash(sent['sentinel'])
            if n!='manifest':assert js['cargo']==fixed and js['compiler']==r19
            if n=='manifest':assert r['program']==[17,29,31][ix]and r['sentinel_sha256_before']==r['sentinel_sha256_after']==sent['sentinel']and not r['sentinel_replaced']and not r['manifest_is_symlink']
            elif n in ('public-api','resolve'):assert r['value']==[17,29,29][ix]and js['after_sha']==sent['sentinel']
            else:assert r['verdict']==('checked'if n=='check-hint'else[17,29,31,31][ix])and not r['changed'] and r['inode_preserved']and not r['record_is_symlink'] and r['prior']==r['after']==sent['sentinel'] and is_hash(r['record_sha'])
            if ph=='repeat':assert all(v for _,v in saved['typed'])
def main():
    manifest={r[66:]:r[:64]for r in (P/'SHA256SUMS').read_text().splitlines()};files={f.relative_to(P).as_posix() for f in P.rglob('*')if f.is_file() and f.name!='SHA256SUMS'}
    assert files==set(manifest) and all(sha(P/n)==v for n,v in manifest.items())
    read=lambda f:json.loads((P/f).read_bytes());unzip=lambda f:json.loads(gzip.decompress((P/f).read_bytes()))
    m=unzip('macro.json.gz');a=unzip('assembler.json.gz');w=read('writers.json');b=read('subjects.json');verify(m,a,w,b)
    if '--self-test' in sys.argv:
        mutations=[(m,'exit',101),(m,'runtime',29),(a,'source','0'*64),(a,'elf','0'*64),(w,'writer',None)]
        for data,key,val in mutations:
            mm,aa,ww=copy.deepcopy((m,a,w))
            if data is w:ww['provenance']['received']['rows'][1]['inode_preserved']=False
            else:(mm if data is m else aa)[0][key]=val
            try:verify(mm,aa,ww,b)
            except AssertionError:continue
            raise AssertionError('accepted mutation '+key)
        aa=copy.deepcopy(a);row=next(r for r in aa if r['arm']=='explicit-yes'and r['phase'].startswith('07-'));row['opens']=[{'missing':True}]
        try:verify(m,aa,w,b)
        except AssertionError:pass
        else:raise AssertionError('accepted a fabricated lookup on the stale link-only result')
    print('Verified 81 commands: 14 value, 15 fixed diagnostics, 17 shipped diagnostics, 18 assembler, 17 generated writer checks.')
if __name__=='__main__':main()
