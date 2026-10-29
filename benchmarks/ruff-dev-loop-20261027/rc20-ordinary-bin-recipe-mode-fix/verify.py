"""Check raw-trace commitments, command roles, Cargo verdicts, and both stable-path upgrades."""
from collections import Counter
import copy
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parent
FIXED='6d0449d4eb0aa490e04aa553bab278c7818efe2c7d529b1d5c9536f01ef90168'
SUBJECTS={
    'fixed':FIXED,
    'released':'789c2f116732ed642565d0f92c500838f8cd53664fbe60f205a5621c43cbecf1',
    'original_282':'ad893345f66ade1c886309b0fc2f98ec5b225d206c176e356531f0e3467eff81',
    'original_284':'8c1717fa9786e16d3bec0c3181c02c1803484ed857d262580ce88d54056504c5',
}
H=lambda b:hashlib.sha256(b).hexdigest()
D=lambda f:H(f.read_bytes())
HASH=re.compile('[0-9a-f]{64}').fullmatch
def check(rows,metadata):
    assert metadata['cargo']==FIXED and metadata['cargo_bytes']==43342056
    assert metadata['cargo_source']=='e2fa457aa7e8e99275a69bbf2e72856f4b767d0d' and metadata['cargo_tree']=='da9c1246f3ad023da25fb60979a5e486863233e2'
    assert metadata['rustc']=='5694abe50767a22cebeccb767143f7404d5e81c4b1760cff4426466bf410e511'
    assert metadata['driver']=='f772b49abec18759edbd9cb7f9f2930097d6ba64d9a2b82837edf4451acc3014'
    assert metadata['wild']=='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'
    assert metadata['older_results_sha256']=='2ea3d01d54760ac50e00902f83cf638678e0ee320e65d37334aaa80507ec9db7'
    assert metadata['pgo']=='481ada8a40c70dad11b3c7e8871e9a52207d78447ca5e8ace06fc4aec2d2b5a7'
    assert metadata['diagnostic_source_unchanged_in_upgrade'] and metadata['extra']['diagnostic_original']==D(ROOT/'qualify-relink-collection-verdict.py') and metadata['extra']['diagnostic_at_acquisition']==D(ROOT/'h8-verdict.py') and metadata['extra']['upgrade_at_acquisition']==D(ROOT/'h8-upgrade.py')
    original=(ROOT/'qualify-relink-collection-verdict.py').read_bytes()
    assert original.replace(b'> 45*2**30 + 600*2**20',b'> 24*2**30 + 600*2**20')==(ROOT/'h8-verdict.py').read_bytes()
    assert 'commit-hash: '+metadata['cargo_source'] in metadata['matrix_versions']['cargo'] and 'commit-hash: '+metadata['rustc_source'] in metadata['matrix_versions']['rustc']
    swaps=metadata['upgrade_swaps'];assert [s['label']for s in swaps]==['released','released','fixed','original_282','original_284','fixed']
    assert all(s['cargo']==SUBJECTS[s['label']] for s in swaps)
    assert len(rows)==47 and Counter(r['study']for r in rows)=={'matrix':14,'diagnostic':15,'upgrade':18}
    by={(r['study'],r['arm'],r['phase']):r for r in rows};assert len(by)==len(rows)
    original_probe=(ROOT/'fixture/probe/src/main.rs').read_bytes()
    source_hash=H(original_probe);edit_hash=H(original_probe+b'fn force_real_build() -> bool { true }\n')
    mwords={'default':17,'no':29}
    melves={m:by['matrix',m,'initial']['elf_sha256'] for m in mwords}
    assert len(set(melves.values()))==2
    verdict_elf=by['diagnostic','implicit','start']['elf_sha256']
    assert len({*melves.values(),verdict_elf})==3
    full_totals=Counter()
    cargo_path_by_study={}
    def visit(study,arm,phase,mode,which,compiler_names,native,rc,value,elf):
        r=by.pop((study,arm,phase));assert r['mode']==mode and r['cargo']==which and r['exit']==rc and r['success']==(rc==0) and r['runtime']==value and r['elf_sha256']==elf
        assert all(HASH(x) for x in [r['stdout_sha256'],r['stderr_sha256']])
        ts=r['trace_files'];assert ts and len({t['file']for t in ts})==len(ts) and all(t['size']>=0 and HASH(t['sha256'])and t['file'].startswith('exec.')for t in ts)
        names={t['file']:t['recorded_execs'] for t in ts};es=r['execs'];cnt=Counter(e['file']for e in es);assert all(cnt[x]==v for x,v in names.items())and set(cnt)<=set(names)
        for e in es:
            assert e['argc']>0 and all(HASH(e[f])for f in ['argv_nul_sha256','exe_spelling_sha256','execve_line_sha256'])
        c=Counter(e['kind']for e in es);full_totals.update(c)
        assert c['wild']==c['cc']==c['collect2']==native and c['cargo']==c['cargo-proxy']==1
        cpath=next(e['exe_spelling_sha256']for e in es if e['kind']=='cargo');assert cpath==cargo_path_by_study.setdefault(study,cpath)
        cs=[e for e in es if e['kind']=='rustc'];assert Counter(e['crate']for e in cs)==Counter(compiler_names)
        root='probe' if study=='matrix' else 'consumer'
        for e in cs:
            if e['crate']==root:
                assert e['recipe']==(mode!='no') and e['temps_dir']==(mode!='no') and e['externs']==['facade','facade'] and len(e['source_args'])==1 and e['source_args'][0].endswith('src/main.rs')
        arts=r['artifacts'];assert len(set(a['name']for a in arts))==len(arts)
        expected_roster={'facade',root,'origin'if study=='matrix'else'report'}-({root} if rc else set())
        assert {a['name']for a in arts}==expected_roster and {a['name']for a in arts if not a['fresh']}==set(compiler_names)-({root}if rc else set())
        for a in arts:
            expected='bin'if a['name']==root else 'lib'if a['name']=='facade'else'proc-macro'
            assert a['kind']==a['crate_types']==[expected]
        if rc: assert r['errors']==[{'message':'link recipe was not requested','code':None,'primary':[['consumer/src/main.rs',1,28]]}]
        else: assert not r['errors'] and HASH(elf)
        if study=='matrix':assert r['source_sha256']==(edit_hash if phase=='edit'else source_hash)
        else:assert not r['evicted_short_fingerprint']
    for first,second in [('default','no'),('no','default')]:
        for ix,phase in enumerate(['initial','initial-repeat','switch','switch-repeat','edit','restore','restore-repeat']):
            m=first if ix<2 else second
            comp=['origin','facade','probe'] if ix==0 else ['probe']if ix in (2,4,5)else []
            visit('matrix',first,phase,m,'fixed',comp,2 if ix==0 else int(bool(comp)),0,mwords[m],melves[m])
    for arm,m in [('implicit','default'),('explicit','yes')]:
        for phase,mode,comp,native,rc in [('start',m,['report','facade','consumer'],2,0),('unchanged',m,[],0,0),('switch','no',['consumer'],0,101),('switch-repeat','no',['consumer'],0,101),('restore',m,['consumer'],1,0),('restore-repeat',m,[],0,0)]:
            visit('diagnostic',arm,phase,mode,'fixed',comp,native,rc,None if rc else 17,None if rc else verdict_elf)
    for phase,mode,comp,native,rc in [('no','no',['report','facade','consumer'],1,101),('repeat','no',['consumer'],0,101),('recover','default',['consumer'],1,0)]:
        visit('diagnostic','empty',phase,mode,'fixed',comp,native,rc,None if rc else 17,None if rc else verdict_elf)
    for arm,old in [('direct','released'),('development','original_282')]:
        for phase,m,comp,native in [('seed','default',['report','facade','consumer'],2),('seed-fresh','default',[],0),('false-success','no',[],0),('false-success-repeat','no',[],0)]:
            visit('upgrade',arm,phase,m,old,comp,native,0,17,verdict_elf)
        if arm=='development':visit('upgrade',arm,'different-cargo-same-old-key','no','original_284',[],0,0,17,verdict_elf)
        for phase in ['upgrade-detects-error','error-repeat']:visit('upgrade',arm,phase,'no','fixed',['consumer'],0,101,None,None)
        visit('upgrade',arm,'recover','default','fixed',['consumer'],1,0,17,verdict_elf)
        visit('upgrade',arm,'recover-fresh','default','fixed',[],0,0,17,verdict_elf)
    visit('upgrade','empty','clean','no','fixed',['report','facade','consumer'],1,101,None,None)
    assert not by and sum(len(r['trace_files'])for r in rows)==1513 and full_totals=={'cargo-proxy':47,'cargo':47,'rustc-query':48,'rustc':44,'cc':25,'collect2':25,'wild':25}

def main():
    files={p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if p.is_file() and p.name!='SHA256SUMS'}
    sums={line[66:]:line[:64] for line in (ROOT/'SHA256SUMS').read_text().splitlines()};assert set(sums)==files and all(D(ROOT/n)==v for n,v in sums.items())
    subjects=json.loads((ROOT/'subjects.json').read_bytes());rows=json.loads(gzip.decompress((ROOT/'evidence.json.gz').read_bytes()));check(rows,subjects)
    if '--self-test'in sys.argv:
        variants=[('matrix','default','switch','runtime',17),('matrix','no','switch-repeat','elf_sha256','0'*64),('diagnostic','implicit','switch','exit',0),('upgrade','direct','upgrade-detects-error','errors',[]),('upgrade','development','different-cargo-same-old-key','cargo','fixed'),('upgrade','empty','clean','execs',[])]
        for study,arm,phase,k,v in variants:
            m=copy.deepcopy(rows);r=next(x for x in m if (x['study'],x['arm'],x['phase'])==(study,arm,phase));r[k]=v
            try:check(m,subjects)
            except (AssertionError,StopIteration):continue
            raise AssertionError('accepted mutation '+str((study,arm,phase,k)))
    print('Verified 47 Cargo commands, 1,513 trace files, 261 successful execve calls, 44 crate compilers and 25 stock Wild runs.')

if __name__=='__main__':main()
