"""Verify every observed native command, package, compiler argv, consumed DSO and in-place migration."""
import argparse, hashlib, io, json, os, re, subprocess, tarfile, tempfile, tomllib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sha=lambda blob:hashlib.sha256(blob).hexdigest()
ARMS={'official':'4e4065390403afbf4fb77b2f41fbc21c59afe3dda2337a5bbe29fda29a47dbb3','off':'4e4065390403afbf4fb77b2f41fbc21c59afe3dda2337a5bbe29fda29a47dbb3','261':'0aa04df8023984b83ef676d1494d43e482472e1b2bccdb82a4d0bd390578a322','known':'583b85bda8785951173a00ab3d0f8abb7cb3b7c8fe8f15518f057f46e6c50956','v2':'5e37d20fa6f79cfcc5a273fb7a95eb19f7239ba750c8a3d1aeaedb90171cdd36'}
RUST={'frontend':'7ec5263869aed2fc9272ea7212aabbe7b272a4685f1b79af75c123daff09c02c','driver':'618ebac16b7d4ec01a2af89661d25b8f26ff347edbb69c6dcaa78f10115914a7'}
PATCHES={'known':'4350d34f8f950cb3cf1f3ba5038d088cdb24ff741506bc2feee971d0ae209cb2','v2':'434aa578f350ef13f2135add343baa623c87e36020d82b2e91d4daaba8790a49'}
F=['seed','seed-repeat','first-edit','next','again','empty'];M=['seed','seed-repeat','first-edit','upgrade','upgrade-repeat','downgrade','up-again','empty']
for line in (ROOT/'SHA256SUMS').read_text().splitlines():h,p=line.split('  ',1);assert sha((ROOT/p).read_bytes())==h,p
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--run-programs',action='store_true');a=ap.parse_args()
with tarfile.open(ROOT/'native.tar.gz') as t:raw={m.name:t.extractfile(m).read() for m in t if m.isfile()}
for key,source in [('known','known-observer-v1.patch'),('v2','uncertified-default-v2.patch')]:
    assert sha((ROOT/'workers'/source).read_bytes())==PATCHES[key]
    for name in (('guard-inputs.sha','derive-guard.sha','derive-guard.exit') if key=='known' else ('v2-guard-inputs.sha','default-guard.sha','default-guard.exit')):
        b=raw['build/'+name];assert (PATCHES[key] in b.decode() if 'inputs' in name else ARMS[key] in b.decode() if name.endswith('sha') else b.strip()==b'0')
count=0;validated_execs=0
for experiment in ('synchronized','natural','migration'):
    group=ARMS.keys() if experiment!='migration' else ('official','261')
    for arm in group:
        prefix=f'{experiment}/{arm}/';get=lambda key:raw[prefix+key];j=json.loads(get('complete.json'));assert j['cargo']==ARMS[arm] and all(j[k]==v for k,v in RUST.items())
        assert j['source']==[sha((ROOT/'workers'/f).read_bytes()) for f in ['original.rs','edited.rs']]
        assert (ROOT/'workers/original.rs').read_bytes().replace(b'Foo::VALUE,0',b'Foo::VALUE,managed_api::inspect_value!(sample)')==(ROOT/'workers/edited.rs').read_bytes()
        pkgs=json.loads(get('packages.json'));assert pkgs==j['packages'] and set(pkgs)=={'managed-macro','managed-tokens','managed-api'}
        lock={p['name']:p for p in tomllib.loads(get('Cargo.lock').decode())['package']}
        for pkg,expected in pkgs.items():
            stem=pkg+'-0.1.0';arc=get(stem+'.crate');assert sha(arc)==expected['package']==lock[pkg]['checksum'] and lock[pkg]['source'].startswith('registry+') and json.loads(get('checksums/'+stem+'.json'))==expected
            with tarfile.open(fileobj=io.BytesIO(arc)) as t:files={m.name[len(stem)+1:]:t.extractfile(m).read() for m in t if m.isfile()}
            assert {name:sha(b) for name,b in files.items()}==expected['files'];source={'managed-macro':'macro.rs','managed-tokens':'tokens.rs','managed-api':'api.rs'}[pkg];assert files['src/lib.rs']==(ROOT/'workers'/source).read_bytes()
            if pkg=='managed-macro':assert files['build.rs']==(ROOT/'workers/build.rs').read_bytes()
        seq=M if experiment=='migration' else F;seq=(['old-precursor','new-precursor']+seq if experiment=='synchronized' else seq);assert set(j['rows'])==set(seq)
        assert get('calls').decode().splitlines()==[x for n in seq for x in j['rows'][n]['calls']]
        if experiment=='synchronized':assert any(v['program']=='rustc' and ' r-xp ' in v['map'] and str(j['old_and_new_inode'][0]) in v['map'] for v in j['observed_old_maps']) and j['old_and_new_inode'][0]!=j['old_and_new_inode'][1] and j['initial_dso']!=j['replacement_dso']
        else:assert j['no_user_binary_writes_or_timestamp_changes'] and j['same_output_path'] and j['old_dso']!=j['new_dso']
        assert all((j['sections'][0][q]==j['sections'][1][q])==(q!='.text') for q in ('.dynsym','.rustc','.text'))
        if experiment=='natural':
            for i,state in enumerate(['old','new']):assert {sec:sha(get('elf/'+state+sec)) for sec in ['.dynsym','.rustc','.text']}==j['sections'][i]
        for phase in seq:
            rr=j['rows'][phase];row_prefix=prefix+phase+'/';count+=1;assert rr['rc']==0
            for n,digest in rr['logs'].items():assert sha(raw[row_prefix+n])==digest,(experiment,arm,phase,n)
            events=[json.loads(l) for l in raw[row_prefix+'out'].splitlines()];assert events[-1]=={'reason':'build-finished','success':True};arts=[r for r in events if r.get('reason')=='compiler-artifact'];assert {r['target']['name']:r['fresh'] for r in arts}==rr['fresh']
            assert all(r['package_id'].startswith('registry+') for r in arts if r['target']['name'].startswith('managed_'));traces=[];commands=[]
            for n in rr['logs']:
                if not n.startswith('exec.'):continue
                for line in raw[row_prefix+n].decode().splitlines():
                    if not line.startswith('execve(') or not line.endswith(' = 0'):continue
                    commands.append(line)
                    if '"--crate-name",' not in line:continue
                    name=re.search(r'"--crate-name", "([^"]+)"',line)[1]
                    if name!='___':traces.append((name,sha(line.encode()),re.findall(r'"(-Zcache-proc-macros(?:=no|=yes)?)"',line)))
            assert sorted(traces)==sorted((r['unit'],r['argv_sha'],r['cache_flags']) for r in rr['rustc']);validated_execs+=len(commands)
            if 'precursor' in phase:assert rr['stdout'] is None;continue
            raw_d=raw[row_prefix+'rustc.d'];fp=raw[row_prefix+'encoded.bin'];assert sha(raw_d)==rr['d_sha'] and sha(fp)==rr['fp_sha'];assert rr['marker']==(b'ohm-foreign-span-bytes' in raw_d)==(b'OBS1' in fp)
            cli=[r for r in rr['rustc'] if r['unit']=='cli'];assert len(cli)==int(not rr['fresh']['cli']);assert all(r['full'] for r in cli)
            if phase in ('seed','seed-repeat'):want='17/0';calls=['17'] if phase=='seed' else [];assert not rr['marker']
            else:
                assert rr['marker'];wrong=(phase=='first-edit' and arm not in ('v2','off')) or (experiment!='migration' and arm=='261' and phase in ('next','again'));want='17/29' if wrong else '29/29';calls=[] if wrong or not cli else ['29']
            assert rr['stdout']==want and rr['calls']==calls,(experiment,arm,phase,rr['stdout'],rr['calls'],want,calls)
            if experiment=='migration':
                who='v2' if phase in ('upgrade','upgrade-repeat','up-again','empty') else arm;assert raw[row_prefix+'cargo.sha'].decode().split()[0]==ARMS[who] and raw[row_prefix+'expected-cargo'].decode()==ARMS[who]
                if cli:assert (cli[0]['cache_flags']==[])==(who=='v2')
            elif cli:
                if arm=='v2':assert cli[0]['cache_flags']==[]
                if arm=='off':assert cli[0]['cache_flags'][-1]=='-Zcache-proc-macros=no'
                if arm=='known' and phase in ('next','again'):assert cli[0]['cache_flags'][-1]=='-Zcache-proc-macros=no'
            if experiment in ('natural','migration') and phase=='first-edit':
                assert any(x['reason']=='build-script-executed' and x['package_id'].startswith('registry+') for x in events);assert any('"cc", "-fPIC", "-c", "native.c", "-o", "choice.o"' in l for l in commands);assert any('"--crate-name", "managed_macro"' in l and 'choice.o' in l for l in commands);assert rr['fresh']['managed_macro'] is False
assert count==86
for arm in ('official','261'):
    for case in ('first','upgrade'):assert raw['rejected/'+case+'-'+arm+'.exit'].strip()==b'1'
    assert b'AssertionError' in raw['rejected/first-'+arm+'.err'] and b'No permissions to create new namespace' in raw['rejected/upgrade-'+arm+'.err']
if a.run_programs:
    with tempfile.TemporaryDirectory() as d:
        for arm in ('261','v2'):
            for k in ('warm','empty'):
                p=Path(d)/(arm+'-'+k);p.write_bytes(raw['natural/'+arm+'/programs/'+k]);p.chmod(0o700);assert subprocess.check_output([p]).strip()==(b'17/29' if (arm,k)==('261','warm') else b'29/29')
print(f'Verified {count} Cargo results and {validated_execs} successful exec records, 10 first uses, both physical Cargo upgrades, 4 rejected harness starts and 4 saved x86-64 programs.')
