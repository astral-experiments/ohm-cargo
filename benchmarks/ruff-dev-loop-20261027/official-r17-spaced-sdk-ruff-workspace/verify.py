"""Offline checks for the published Linux package and the native runner's selected observations."""
from pathlib import Path
import collections,hashlib,json,re,sys,tarfile

p=Path(__file__).resolve().parent; data=p/'observations.tar.gz' if len(sys.argv)==1 else Path(sys.argv[1]); H=lambda d:hashlib.sha256(d).hexdigest()
with tarfile.open(data) as f:
    def datafile(name):return f.extractfile(name).read()
    def j(name):return json.loads(datafile(name))
    paths=f.getnames();assert len(paths)==len(set(paths)) and all('..' not in Path(s).parts and not Path(s).is_absolute() for s in paths)
    valid=lambda s:isinstance(s,str) and re.fullmatch(r'[a-f0-9]{64}',s)
    tag='ohm-1.99.0-17';stem=tag+'-x86_64-unknown-linux-gnu';rel=j('release.json');prov=j('package/provenance.json');manifest=j('package/manifest.json');installed=j('installed.json')
    assert rel['tag']==tag and rel['published_at'] and rel['workflow']==40609224340 and rel['head']=='fdf90406638cacb725178ee17e67957f7bd662ca'
    assert prov['target']=='x86_64-unknown-linux-gnu' and prov['coordinator']['revision']==rel['head'] and prov['manifest']['sha256']==H(datafile('package/manifest.json'))==rel['manifest_sha256']
    assert rel['rust']==prov['sources']['rust']['revision']==manifest['sources']['rust']['revision']=='bfa236f639034f61ec884c15bd1f4e0b75e508ac'
    assert rel['cargo']==prov['sources']['cargo']['revision']==manifest['sources']['cargo']['revision']=='a0c7d08c898d3fdff992f2f431dec57d2486add2'
    sums={n:h for h,n in [s.split() for s in datafile('package/published.SHA256SUMS').decode().splitlines()]}
    actual={a['id'] for a in rel['assets'].values()};assert len(actual)==len(rel['assets'])==6
    for name,entry in rel['assets'].items():
        assert entry['state']=='uploaded' and entry['size']>0 and entry['digest'].startswith('sha256:') and valid(entry['digest'][7:]);
        if name in sums:assert entry['digest'][7:]==sums[name]
    assert H(datafile('package/published.SHA256SUMS'))==rel['assets']['SHA256SUMS']['digest'][7:]
    assert H(datafile('package/provenance.json'))==sums[stem+'-provenance.json'] and H(datafile('package/linux.sha256'))==rel['assets'][stem+'.tar.gz.sha256']['digest'][7:]
    assert datafile('package/linux.sha256').decode().strip().split()==[installed['archive'],stem+'.tar.gz'] and installed['archive']==sums[stem+'.tar.gz']
    assert installed['installer']==sums['ohm-installer.sh'] and rel['cargo'] in installed['versions']['cargo'] and rel['rust'] in installed['versions']['rustc'] and installed['versions']['sysroot_basename']=='Ohm SDK'
    assert set(installed['elf'])=={'rustc','wild','cargo','driver','llvm'} and all(valid(v['sha256']) and v['bytes']>0 for v in installed['elf'].values())
    assert installed['elf']['wild']['sha256']=='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'
    assert j('source.json')['commit']=='93526150df078af7dd8fc4226cdcc469539d2001' and j('installed_global_alias_before_after_equal.json') and j('scored_commands.json')==0
    reg=j('registry-inputs.json');assert len(reg)==957 and len([n for n in reg if n.startswith('crate/')])==498 and len([n for n in reg if n.startswith('sparse/')])==458
    assert all(valid(v) for v in reg.values()) and H(json.dumps(reg,sort_keys=True,separators=(',',':')).encode())==j('registry.json')
    source=j('runner-files.json')
    with tarfile.open(fileobj=f.extractfile('reproducer/unicode/observations.tar.gz')) as fixtures:
        assert {n:H(fixtures.extractfile(n).read()) for n in fixtures.getnames()}==j('reproducer/unicode/source-files.json')
    assert all(H(datafile(s))==source['bin/'+s.removeprefix('reproducer/')] for s in paths if s.startswith('reproducer/'))
    small=j('small.json');o=small['ordinary'];assert o['build']['initial']['program']==o['build']['unchanged']['program']==17
    assert o['build']['unchanged']['fresh']==o['check']['unchanged']['fresh']==[True] and o['build']['changed']['fresh']==[False]
    assert o['build']['changed']['program']==o['build']['clean']['program']==29
    assert o['check']['changed']['code']==o['check']['clean']['code']==101 and o['check']['changed']['errors']==o['check']['clean']['errors']==['E0308']
    assert small['ordinary_format']['build']['cargo_depinfo'] and small['ordinary_format']['build']['raw_depinfo']
    for k,x in small['unicode'].items():
        phases=x['phases'];assert phases['unchanged']['fresh']==(k=='b') and phases['changed']['exit']==phases['empty']['exit']==101 and phases['changed']['diagnostics']==phases['empty']['diagnostics']==['E0308'] and valid(x['diagnostic'])
    assert set(small['unicode'])=={'ab','ba','b'} and all(all(valid(v) for v in j('small-raw/'+x+'.json').values()) for x in ('ordinary','unicode-ab','unicode-ba','unicode-b'))
    fix=j('postprocess_recovery.json')
    assert fix['old_exit']==1 and fix['cold_reexecutions']==0 and fix['all_110_original_cold_elf_bytes_rechecked'] and fix['all_original_process_traces_rechecked']
    assert fix['old_runner']==H(datafile('runner-files.json')) and fix['resumed_runner']==H(datafile('recovery/resume.py')) and fix['source_excerpt']==H(datafile('recovery/cargo-format-contract.txt'))
    assert fix['original_commitments']['receipts/phase-0/ron.d']==j('phase-0/observer.json')['depfile_sha256'] and fix['original_commitments']['receipts/phase-0/ron-encoded']==j('phase-0/observer.json')['cargo_record_sha256']
    assert j('phase-0/observer.json')['cargo_version']==2 and not j('phase-0/observer.json')['complete']
    by_phase=[];previous=None;previous_order=None;baseline=None;last_list=None;seen_fresh=0
    for n in range(len([s for s in paths if s.endswith('/cargo-rows.json')])):
        pr=f'phase-{n}/';summary=j(pr+'summary.json'); rows=j(pr+'cargo-rows.json');elf=j(pr+'elf.json');exes=j(pr+'executables.json'); ps=j(pr+'native-processes.json'); obs=j(pr+'observer.json');tr=j(pr+'trace-files.json'); raw=j(pr+'raw.json')
        assert len(rows)==summary['units']==619 and sum(x[6] for x in rows)==summary['fresh']
        assert len(elf)==summary['native']==110 and len(exes)==summary['executables']==102
        assert set(exes)<=elf.keys() and all(v['bytes']>0 and valid(v['raw']) and valid(v['except_registered_wild_fields']) for v in elf.values())
        assert collections.Counter(x[5] for x in rows if x[7])=={True:84,False:18}
        order=sorted(json.dumps(x[:6]+x[7:]) for x in rows);assert previous_order is None or previous_order==order
        previous_order=order
        lists={k:H(datafile(pr+k+'.list')) for k in ['e2e','stdlib']};assert not last_list or lists==last_list
        for k,num in [('e2e',200),('stdlib',4)]:assert sum(s.endswith(b': test') for s in datafile(pr+k+'.list').splitlines())==num and summary['listed'][k]=={'registered':num,'sha256':lists[k]}
        last_list=lists;assert b'inlay_hints::default_inlay_hints: test' in datafile(pr+'e2e.list') and b'identifiers::tests::migration_name: test' in datafile(pr+'stdlib.list')
        assert len(ps['cargo'])==1 and all(valid(sig) and isinstance(rc,int) and 'exec.'+str(pid) in tr for pid,crate,kind,rc,sig in ps['jobs'])
        assert all(valid(sig) and isinstance(rc,int) and 'exec.'+str(pid) in tr for pid,kind,dest,rc,sig,image in ps['linkers'])
        counted={'rustc':dict(collections.Counter(x[2] for x in ps['jobs'])),'wild':sum(x[1]=='wild' for x in ps['linkers']),'system':sum(x[1]=='system' for x in ps['linkers']),'queries':len(ps['rustc_queries'])}
        assert counted==summary['real_jobs']==ps['counts'];assert raw['stdout']==summary['stdout_sha'] and raw['stderr']==summary['stderr_sha'] and raw['elf.json']==summary['raw_elf_sha']
        assert summary['cargo_depinfo_format']==obs['cargo_version']==(4 if summary['checksums'] else 2) and bool(obs['complete'])==summary['ron_complete'] and obs['wire']=='OBS1'
        assert obs['depfile_sha256']==summary['depinfo_sha']==raw['ron.d'] and obs['cargo_record_sha256']==summary['proof_sha']==raw['ron-encoded'] and len(obs['checksum_line_sha256'])==summary['checksums']
        if obs['complete']:assert obs['raw_checksum_header'] and obs['sdk_path_checksum_rows']>0
        if n==0:assert summary['fresh']==0 and counted['rustc']['full']>600 and counted['wild']>0
        if baseline is None:baseline=summary
        else:
            assert sorted(elf)==sorted(previous) and summary['roster']==baseline['roster'] and summary['diagnostics']==baseline['diagnostics']
            diff=[(k,v['raw'],previous[k]['raw']) for k,v in elf.items() if v['raw']!=previous[k]['raw']];assert len(diff)==110-summary['raw_native_matches']
            assert sorted((Path(k).name,cur,prev) for k,cur,prev in diff)==sorted((w['name'],w['current'],w['previous']) for w in summary['prior_native_differences'])
            if summary['fresh']==619:assert not counted['rustc'] and counted['wild']==counted['system']==0 and not diff and obs['complete'];seen_fresh+=1
            else:seen_fresh=0
        by_phase.append({'phase':n,'units':619,'fresh':summary['fresh'],'elf':110,'exec':102,'listed':[200,4],**counted,'observer_inputs':summary['checksums']});previous=elf
    assert 3<=len(by_phase)<=6 and seen_fresh==2 and fix['unchanged_commands']==len(by_phase)-1
print(json.dumps({'release':tag,'cargo':rel['cargo'],'rust':rel['rust'],'archive':installed['archive'],'runner':H(json.dumps(source,sort_keys=True,indent=2).encode()+b'\n'),'phases':by_phase,'small_cases':5,'scored':0},sort_keys=True,indent=2))
