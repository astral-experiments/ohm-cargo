from pathlib import Path
import hashlib,json,tarfile
r=Path(__file__).resolve().parent
with tarfile.open(r/'records.tar.gz') as t:
    j=lambda n:json.load(t.extractfile(n))
    f=j('failure.json');assert f['failed'] and f['full_workspace_wall_rows']==0 and f['no_admission_published']
    assert f['registered_native_verifier_sha256']==hashlib.sha256((r/'frozen-processes.py').read_bytes()).hexdigest()
    assert f['runtime_sha256sums']=='14d20e62691c4b124f52e106c66bc9926f3b92ecf6bf77ff017f264e1504c7e2'
    n=0;complete=0;summary={}
    for a,d in f['phases'].items():
        phases=['cold'] if a=='B' else ['cold','first','settled','settled2'];assert set(d)==set(phases)
        for ph in phases:
            k=f'{a}/{ph}/';v=d[ph];u=j(k+'cargo.json');raw=j(k+'raw.json')
            assert len(u)==v['unit_count']==619 and sum(x['fresh'] for x in u)==v['fresh'] and sum(bool(x['executable']) for x in u)==v['declared_executables']==102
            assert v['elapsed_ns'] is None and v['cargo_rc']==0 and v['instrumented'] and raw['raw_trace_files']
            assert len(raw['stdout'])==len(raw['stderr'])==64 and v['completed_native_verifier']==(a!='B');n+=1
            if a=='B':
                assert ph=='cold' and v['fresh']==0
                for name,part in f['incomplete_traces'].items():
                    assert raw['raw_trace_files'][name]==part['complete_trace_file_sha256']
                    assert [x['event'] for x in part['events']]==['exec unfinished','exited 0']
                    assert part['open_exec_line_sha256']==part['events'][0]['raw_line_sha256']
                continue
            complete+=1;procs=j(k+'processes.json');counts=v['counts'];elf=j(k+'raw-elf.json')
            assert not procs['rustc_queries'] if ph!='cold' else len(procs['rustc_queries'])==36
            assert len(elf)==v['actual_elf_count']==110 and all(len(h)==64 for h in elf.values())
            if ph=='cold':assert v['fresh']==0 and counts['rustc']=={'full':636}
            if ph=='first':
                assert v['fresh']==(619 if a=='C' else 563) and counts['rustc']==({} if a=='C' else {'full':1,'link-only':50}) and counts['wild']==(0 if a=='C' else 50)
            if ph in ('settled','settled2'):assert v['fresh']==619 and not counts['rustc'] and counts['wild']==0 and elf==j(a+'/first/raw-elf.json')
            if ph in ('cold','first'):
                proof=j(k+'proof.json');assert proof['complete']==(a=='C' or ph=='first')
                if proof['complete']:assert len(proof['effective_inputs'])==45
    assert len(f['incomplete_traces'])==1 and n==13 and complete==12
print(json.dumps({'cargo_successes':n,'fully_traced_phases':complete,'incomplete_pid_traces':1,'true_whole_workspace_wall_samples':0,'admitted':False,'remaining_unrun':3},sort_keys=True))
