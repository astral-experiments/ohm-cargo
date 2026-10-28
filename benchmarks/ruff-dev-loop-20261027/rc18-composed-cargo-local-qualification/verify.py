"""Independently reopen native programs, Cargo events, raw Make files, process traces, and source commitments."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parent
HEAD = '7181bfa6256f94da142f80fd6af09cee02ec2c78'
TREE = '5386201eedb3970d3cc74521f12bd644cdf33396'
SHIPPED = '4e4065390403afbf4fb77b2f41fbc21c59afe3dda2337a5bbe29fda29a47dbb3'
EARLIER = '0aa04df8023984b83ef676d1494d43e482472e1b2bccdb82a4d0bd390578a322'
SUBJECTS = {'dev':'1c328d9c2e078019989b2c677acd666820caa093f4993ca8c606d141cf8574e4',
            'pgo':'cfc66a7ceee5cad8f8939245d359e4db0d2b6f2abb5760c7cbefa6c9a1d454f8'}
PR260 = ('early_native_integration_tests_default_and_fallback','early_native_integration_tests_warm_evidence_and_fallback')
TESTS = (*PR260, 'generate_good_d_files', 'ohm_defaults_reexpand_derive_after_native_input_changes')
M = b'ohm-foreign-span-bytes'
sha = lambda b: hashlib.sha256(b).hexdigest()

def actual_execs(blob):
    pending = {}
    for line in blob.decode().splitlines():
        m = re.match(r'(\d+) +(.+)', line)
        if not m:
            continue
        pid, op = m.groups()
        if op.endswith('<unfinished ...>'):
            if op.startswith('execve('):
                assert pid not in pending
                pending[pid] = op.removesuffix('<unfinished ...>')
            continue
        if op.startswith('<... execve resumed>'):
            op = pending.pop(pid) + op.removeprefix('<... execve resumed>')
        if op.startswith('execve(') and op.endswith('= 0'):
            executable = re.match(r'execve\("([^"]+)"', op)[1]
            yield int(pid), executable, op
    assert not pending

def cargo_events(blob):
    rows = [json.loads(l) for l in blob.splitlines()]
    assert rows[-1]['reason'] == 'build-finished'
    return rows, {a['target']['name']: a['fresh'] for a in rows if a['reason'] == 'compiler-artifact'}

def with_trace(raw):
    rows = list(actual_execs(raw))
    full = []
    link = []
    for pid, executable, call in rows:
        if executable.endswith('/rustup/toolchains/ohm/bin/rustc') and '"--out-dir",' in call:
            m=re.search(r'"--crate-name", "([^"]+)"',call)
            if m and m[1]!='___':
                full.append(m[1])
        if Path(executable).name in ('wild','ld','ld.bfd','collect2'):
            link.append(executable)
    return full, link

def verify(arm):
    with tarfile.open(ROOT/(arm+'.tar.gz')) as archive:
        entries={m.name:archive.extractfile(m).read() for m in archive if m.isfile()}
    b=entries.__getitem__;j=lambda n:json.loads(b(n));h=lambda n:sha(b(n))
    subject=j('subjects.json');effective=SUBJECTS[arm]
    assert subject['mode']==arm and subject['cargo']==effective
    assert subject['frontend']=='7ec5263869aed2fc9272ea7212aabbe7b272a4685f1b79af75c123daff09c02c'
    assert subject['driver']=='618ebac16b7d4ec01a2af89661d25b8f26ff347edbb69c6dcaa78f10115914a7'
    if arm=='pgo':
        image=j('build/pgo-source.json')
        assert image['candidate']==effective and image['head']==HEAD and image['tree']==TREE and image['post_check'] and image['leaves']==3108
    include_jobs={}
    for kind in ('include-bytes','include-str','tracked-file'):
        for stamp in ('current','preserved'):
            k=kind+'-'+stamp
            base='includes/trained-'+k+'/'
            origin=j(base+'report.json')
            assert origin['kind']==kind and origin['trained'] and origin['stamp']==stamp
            a,z=origin['before'],origin['after']
            assert a['size']==z['size'] and a['sha256']!=z['sha256']
            assert (a['mtime']==z['mtime'])==(stamp=='preserved')
            assert origin['rows']['again']['all_fresh'] and origin['rows']['again']['initially_complete']
            assert origin['rows']['again']['value']==17 and origin['rows']['clean']['value']==29
            for phase,value in [('official-again',17),('official-empty',29)]:
                rows,arts=cargo_events(b(base+phase+'/cargo.jsonl'))
                assert rows[-1]['success'] and (all(arts.values())==(phase=='official-again'))
                assert b'revision=2' in b(base+phase+'/program').splitlines()
                assert b'sample='+str(value).encode() in b(base+phase+'/program').splitlines()
            include_jobs[k]={}
            for phase in ('before','first','second','empty'):
                stem=base+phase+'/'
                row=j(stem+'row.json')
                old=phase=='before'; required=17 if old else 29
                events,arts=cargo_events(b(stem+'cargo.jsonl'))
                assert events[-1]['success'] and arts==row['fresh'] and row['cargo_rc']==0
                assert row['value']==required and row['cargo']==(SHIPPED if old else effective)
                assert re.findall(rb'^sample=(\d+)$',b(stem+'program'),re.M)==[str(required).encode()]
                assert arts['hold_direct']==old and row['complete']==old
                fp=b(stem+'encoded.bin')
                assert sha(fp)==row['active_fp_sha256'] and fp[-41:-37]==b'OBS1' and bool(fp[-33])==old
                if old:
                    assert h(stem+'encoded.bin')==origin['rows']['again']['fingerprint']
                    assert row['elf_sha256']==origin['rows']['again']['exe']
                else:
                    assert M in b(stem+'rustc.d')
                full,links=with_trace(b(stem+'exec'))
                assert (not full and not links) if old else full.count('hold_direct')==1
                if phase=='second':assert full==['hold_direct']
                include_jobs[k][phase]=full
            for loc in ('actual-warm','actual-empty'):
                assert M in b(base+loc+'/hold_direct.d')
    types={}
    for stamp in ('current','preserved'):
        pre='typed/'+stamp+'/'
        obj=j(pre+'complete.json')
        assert obj['case']=='rmeta' and obj['timestamp']==stamp and obj['old_token_before_replacement']==17
        assert obj['rmeta_roots']['old']==obj['rmeta_roots']['new']
        assert obj['old']['sha256']==h(pre+'original-product')!=h(pre+'replacement')==obj['replacement']['sha256']
        assert (obj['old']['mtime_ns']==obj['replacement']['mtime_ns'])==(stamp=='preserved')
        assert obj['observed_old_maps']
        for phase in ('initial','repeat','again','clean'):
            stem=pre+phase+'/';r=j(stem+'result.json')
            assert r==obj['rows'][phase]
            events,_=cargo_events(b(stem+'stdout'))
            diags=[(e['message']['code']['code'], e['message']['message']) for e in events if e['reason']=='compiler-message' and e['message'].get('code')]
            expected=[] if phase=='initial' else [('E0308','mismatched types')]
            assert diags==expected and [(v['code'],v['message']) for v in r['diagnostics']]==expected
            assert events[-1]['success']==(phase=='initial') and r['exit']==(0 if phase=='initial' else 101)
        types[stamp]=obj['rmeta_roots']['old']
    for name,old in [('direct',None),('from17',SHIPPED),('from261',EARLIER)]:
        pre='derive/'+name+'/'
        obj=j(pre+'complete.json')
        assert obj['cargo']==(old or effective) and obj['frontend']==subject['frontend'] and obj['driver']==subject['driver']
        assert not obj['observed_seed'] and obj['no_user_binary_writes_or_timestamp_changes']
        assert obj['same_output_path'] and obj['old_dso']!=obj['new_dso']
        s,z=obj['sections']
        assert s['.rustc']==z['.rustc'] and s['.dynsym']==z['.dynsym'] and s['.text']!=z['.text']
        phases=('seed','seed-repeat','first-edit','next','again','empty') if not old else ('seed','seed-repeat','first-edit','upgrade','upgrade-repeat','downgrade','up-again','empty')
        assert set(phases)==set(obj['rows'])
        for phase in phases:
            stem=pre+phase+'/';r=j(stem+'row.json')
            assert r==obj['rows'][phase] and r['rc']==0
            ev,arts=cargo_events(b(stem+'out'));assert ev[-1]['success'] and arts==r['fresh']
            actual='17/0' if phase.startswith('seed') else ('17/29' if old and phase=='first-edit' else '29/29')
            assert r['stdout']==actual and r['marker']==(M in b(stem+'rustc.d'))
            assert h(stem+'rustc.d')==r['d_sha'] and h(stem+'encoded.bin')==r['fp_sha']
            assert all(v.startswith('registry+') for k,v in r['package_ids'].items() if k.startswith('managed_'))
            if actual=='29/29' and phase!='downgrade':assert r['calls']==['29']
            elif actual=='17/29':assert not r['calls']
            traces=j(stem+'physical.json')
            assert all(r['logs'][k]==v for k,v in traces['trace_file_sha256'].items())
            if old:
                actual_cargo=(old if phase in ('seed','seed-repeat','first-edit','downgrade') else effective)
                assert b(stem+'cargo.sha').decode().split()[0]==actual_cargo==b(stem+'expected-cargo').decode()
    scheduler={}
    for name in TESTS:
        assert b('suite/'+name+'.exit').strip()==b'0' and b'1 passed; 0 failed' in b('suite/'+name+'.out')
        if name not in PR260:continue
        obj=j('suite/'+name+'.trace.json');assert obj['exact_cargo_sha256']==effective and obj['exact_rustc_sha256']==subject['frontend']
        assert len(obj['cargo_processes'])==(14 if name==PR260[0] else 41)
        assert len({r['pid'] for r in obj['cargo_processes']})==len(obj['cargo_processes'])
        for case,procs in obj['rust_cases'].items():
            for proc in procs:
                line=proc['line']
                assert 'rustup/toolchains/ohm/bin/rustc"' in line and '"tests/integration.rs"' in line
                assert '"--crate-name", "integration"' in line and '/'+name+'/'+case+'/target/' in line and line.endswith('= 0')
        scheduler[name]={k:len(v) for k,v in obj['rust_cases'].items()}
    assert scheduler[PR260[0]]=={'built-library':1,'conflicting-proof':2,'denied-warning':1,'malformed-proof':2,'missing-proof':2,'opt-out':1,'producer-error':1,'serial':1,'unused':1,'used':2}
    assert len(scheduler[PR260[1]])==17
    # One metadata-only check between two test commands is expected for this case.
    checked=j('suite/'+PR260[1]+'.trace.json')['rust_cases']['checked-unused']
    assert sum('"--emit=dep-info,metadata"' in p['line'] for p in checked)==1 and len(checked)==3
    output=None
    for name in ('qc','rc'):
        elf=None
        for phase in ('built','regenerated','unchanged'):
            pre='depfiles/'+name+'/'+phase+'/';row=j(pre+'row.json');now=b(pre+'consumer.d')
            if output is None:output=now
            if elf is None:elf=row['elf']
            assert sha(now)==row['raw'] and now==output and row['elf']==elf
            assert now.count(rb'/tracked\ file')==1 and b'/src/../asset' in now and b'/src/main.rs' in now
            ev,arts=cargo_events(b(pre+'cargo.jsonl'));assert ev[-1]['success'] and arts==row['fresh']
            full,links=with_trace(b(pre+'exec'))
            if phase=='built':assert 'consumer' in full and links
            else:assert all(arts.values()) and not full and not links
    if arm=='dev':
        assert b'9 passed; 0 failed' in b('build/lib-depinfo-exact.out') and b'0 passed; 0 failed' in b('build/lib-depinfo.out')
        lock=b('build/lock-fork.raw')
        assert re.search(rb'op=6\nparent child=\d+\nchild holds inherited fd\npid=\d+ op=8\n',lock)
        assert b'1 passed; 0 failed' in b('build/lock-fork.out')
        for p in ('released','composed'):
            assert b('build/pty-'+p+'.exit').strip()==b'0' and b'1 passed; 0 failed' in b('build/pty-'+p+'.out')
        assert b'101' in b('build/terminal_cancellation_restores_the_shell_and_stops_descendants.exit') and b'did not stop' in b('build/terminal_cancellation_restores_the_shell_and_stops_descendants.out')
        assert b'AssertionError' in b('earlier/public-dep.out')
        for p in ('0','1'):
            assert b'AssertionError' in b('earlier/historic-slot-'+p+'/worker.stderr')
    return {'cargo':effective,'include_units':include_jobs,'typed_roots':types,'scheduler_physical_counts':scheduler,'canonical_depfile':sha(output)}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--cargo-git',type=Path);p=parser.parse_args()
    sums={name:digest for digest,name in (line.split('  ',1) for line in (ROOT/'SHA256SUMS').read_text().splitlines())}
    assert set(sums)=={str(f.relative_to(ROOT)) for f in ROOT.rglob('*') if f.is_file() and f.name!='SHA256SUMS'}
    assert all(sha((ROOT/n).read_bytes())==h for n,h in sums.items())
    projection=json.loads((ROOT/'projection.json').read_bytes());assert projection['tree']==TREE and projection['final']==HEAD
    if p.cargo_git:
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'projection.json'
            subprocess.run([sys.executable,'-IB',str(ROOT/'project.py'),str(p.cargo_git),str(out)],check=True,stdout=subprocess.DEVNULL)
            assert json.loads(out.read_bytes())==projection
    print(json.dumps({name:verify(name) for name in SUBJECTS},indent=2,sort_keys=True))
if __name__=='__main__':main()
