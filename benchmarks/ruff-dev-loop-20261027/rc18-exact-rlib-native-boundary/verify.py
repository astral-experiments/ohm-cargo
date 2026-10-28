"""Independently check the actual archived bytes, positive and missing native lookups and both homes."""
import hashlib, json, sys, tarfile
from pathlib import Path
h=lambda b:hashlib.sha256(b).hexdigest()
d=Path(__file__).resolve().parent
pack=d/'h2-native-selected.tar.gz'
assert h(pack.read_bytes())=='d44c799ddcf62f1f466646a550ca1582375b2e4e2e99a8b72cae2d938214d941'
src=json.loads((d/'source.json').read_bytes())
with tarfile.open(pack) as t:
    names=t.getnames();assert len(names)==347==len(set(names))
    b=lambda name:t.extractfile(name).read()
    j=lambda n:json.loads(b(n))
    r=lambda a,n:j(a+'/reports/'+n)
    archive=j('evidence-export/raw-trace-sha256.json')
    for n in names:
        if n in archive:assert h(b(n))==archive[n]
    for variant,expected in [('v1',1),('v2',0),('v3',0),('v4',0)]:
        subject=j(variant+'.terminal.json')
        assert subject['status']==expected and (subject['actual']['driver'],subject['actual']['cargo'])==(src['rustc_driver_sha256'],src['cargo_sha256'])
    assets={}
    for v in ('v2','v3','v4'):
        rows=r(v,'all.json')
        assert r(v,'verified.json')['pass']
        assert len(rows)==(11 if v=='v2' else 12)
        for phase,row in rows.items():
            dir=v+'/reports/'+phase+'/'
            recorded=j(dir+'row.json');assert recorded==row
            assert row['actual']==f"native-value={row['wanted']}"==b(dir+'native.txt').decode().strip()
            for k,file in [('rlib','libleaf.rlib'),('separate_rmeta','libleaf.rmeta')]:
                assert h(b(dir+file))==row['files'][k]['sha256']
            processes=j(dir+'processes.json')
            assert all(x['exit']=='+++ exited with 0 +++' for x in processes)
            if not phase.endswith('-empty') and phase!='original':
                assert [(p['type'],p['unit']) for p in processes if p['type'] in ('full','link-only')]==[('full','leaf'),('link-only','reader')]
                assert row['wild']==row['collect2']==1
            if phase.endswith('-empty'):
                warm=rows[phase.removesuffix('-empty')]['files']['executable']
                assert warm==row['files']['executable'],phase
                assert ('full','reader') in [(p['type'],p['unit']) for p in processes]
        warm=[v for k,v in rows.items() if k not in ('private-body','private-body-empty')]
        for typ in ('rlib','separate_rmeta'):
            assert len({e['files'][typ]['sha256'] for e in warm})==1
        assert rows['original']['files']['rlib']['sha256']!=rows['private-body']['files']['rlib']['sha256']
        if v=='v4':
            for phase in rows:
                prefix=v+'/reports/'+phase+'/'
                assert h(b(prefix+'reader.rlink'))==dict(rows[phase]['rlinks'])[next(iter(dict(rows[phase]['rlinks'])))]
            before,after=[r(v,x+'/native-observations.json') for x in ('repeat','earlier-provider')]
            assert before['native_sha256']==after['native_sha256']==src['stock_wild_sha256']
            assert all(row['rlinks']==rows['repeat']['rlinks'] for row in [rows['earlier-provider'],rows['same-size-time-native']])
            old,new=[f['positive_literal_objects_after_link'] for f in (before,after)]
            assert {p:v for p,v in old.items() if v}=={p:v for p,v in new.items() if v}
            assert sum(p.endswith('.rlib') for p in old)==22 and sum(v is not None for v in old.values())==35
            assert len(old)==len(new)==36
            def selected(m,k):
                path=m['selected_new_archive']['path']
                label='repeat' if m is before else 'earlier-provider'
                lines=[v for v in m['lookups'] if path in v['text']]
                assert lines
                for x in lines:
                    original=b(f"v4/reports/{label}/exec.{x['tid']}").decode().splitlines()
                    assert x['text']==original[x['line']-1]
                return any(k in x['text'] for x in lines)
            assert selected(before,'ENOENT') and selected(after,'O_RDONLY|O_CLOEXEC) = ')
            for n in ('native-tamper.json','output-tamper.json'):
                m=r(v,n)
                assert m['before']['size']==m['after']['size'] and m['before']['mtime_ns']==m['after']['mtime_ns'] and m['before']['sha256']!=m['after']['sha256']
            assert r(v,'output-tamper.json')['after']['stdout']=='stale!-value=83\n'
            for n,i in ((41,'same-provider-baseline'),(83,'earlier-provider')):
                assert h(b(f'evidence-export/{n}/libutil.a'))==rows[i]['files']['actual_out_dir_libutil']['sha256']
            assert h(b('v4/target/debug/reader'))==rows['private-body']['files']['executable']['sha256']
        assets[v]=rows['original']['files']['rlib']['sha256']
    earlier=r('v1','all.json')
    assert len({e['files']['rlib']['sha256'] for e in earlier.values()})>1
ruff=json.loads((d/'actual-ruff.json').read_bytes())['phases']
for key,values in ruff.items():
    assert len(values)==50
    assert sum(bool(v['ron_rlib']) for v in values.values())==35
    assert all('-lutil' in v['named_libraries'] and 'psm' in v['cargo_build_output_search'] for v in values.values())
    assert sum('zstd-sys' in v['cargo_build_output_search'] for v in values.values())==34
    assert sum(v['old_elf_sha256']['unchanged']!=v['old_elf_sha256']['edited'] for v in values.values())==24
assert set(ruff['unchanged'])==set(ruff['final-unchanged'])
print(json.dumps({'verified':True,'archive_members':len(names),'v1_scope':'incremental workspace raw rlib varied','warm_and_empty_commands':35,'in_scope_hashes':assets,'surviving_native_literals':35,'missing_temporary_literals':1,'matched_cold_native_executables':12,'actual_Ruff_Wilds_per_unchanged_phase':50,'actual_Ruff_forced_full_edited_reference':'separate official C5 gate'},sort_keys=True))
