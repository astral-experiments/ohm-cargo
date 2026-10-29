#!/usr/bin/env python3
"""Verify source identity, versions, compiler rosters, standard suites and named-pipe controls."""
import gzip
import hashlib
import json
from pathlib import Path
import re
import runpy

root=Path(__file__).resolve().parent
constants=runpy.run_path(str(root/'reconstruct.py'))
PRIOR,FIX=constants['PRIOR'],constants['FIX']
h=lambda b:hashlib.sha256(b).hexdigest()
def validate(led):
    assert set(led['arms'])=={f'{s}-{n}' for s in ['prior','fixed','stamped'] for n in PRIOR}
    assert led['rustc_sha256']==constants['RUSTC']
    assert led['fixture_manifest']=='7bd69adfb38cdf31f300b61679fef88bc60b2530757683d979de384ce144d264'
    assert (led['earlier_harness_preflight']['completed_fingerprints'],led['earlier_harness_preflight']['failed_conditional'])==(73,7)
    fixture=root/'regression'
    original=(fixture/'fixture-source.SHA256SUMS').read_bytes();assert h(original)==led['fixture_manifest']
    retained={n:d for d,n in (line.split(maxsplit=1) for line in original.decode().splitlines()) if n.startswith(('fixture/','wrapper/')) or n=='reproduce.py'}
    assert set(retained)=={str(f.relative_to(fixture)) for f in fixture.rglob('*') if f.is_file() and f.name!='fixture-source.SHA256SUMS'}
    assert all(h((fixture/n).read_bytes())==d for n,d in retained.items()) and retained['reproduce.py']==led['fixture_reproduce']
    streams=json.loads(gzip.decompress((root/'suite-stdout.json.gz').read_bytes()))
    assert set(streams)=={k+'/'+case for k,a in led['arms'].items() if a['suites'] for case in a['suites']['sets']}
    outputs=set()
    for n in PRIOR:
        src=led['source'][n]; patch=(root/f'pr{n}.patch').read_bytes()
        assert src['prior']['commit']==PRIOR[n] and src['fixed']['commit']==FIX[n]
        assert src['fixed']['parents'][0]==PRIOR[n] and (n!='103' or src['fixed']['parents']==[PRIOR['103'],FIX['101']])
        assert src['path']==constants['MOD'] and h(patch)==src['patch_sha256']
        assert patch.count(b'diff --git ')==1 and b'fingerprint/mod.rs' in patch
        assert 'speculative_short_fingerprint_follows_regular_symlinks_and_rejects_fifos' in patch.decode()
        assert src['prior']['file_git_blob']!=src['fixed']['file_git_blob']
        for stage in ['prior','fixed','stamped']:
            r=led['arms'][f'{stage}-{n}']; compiled=r['image']; dec=compiled['declaration']; recovery=r['recovery'];z=recovery['result']
            role='prior' if stage=='prior' else 'fixed'
            stamp=FIX[n] if stage=='stamped' else PRIOR[n]
            assert dec['source']==src[role]['commit'] and dec['tree']==src[role]['tree']
            assert h(('\n'.join(compiled['version_lines'])+'\n').encode())==compiled['cargo_vv']
            assert compiled['commit_reported']==compiled['build_script_stamp']['CARGO_COMMIT_HASH']==stamp
            assert '('+stamp[:9]+' ' in compiled['reported_cargo'] and compiled['physical_size']>0
            assert dec['cargo']==z['cargo_sha256'] and dec['rustc']==z['rustc_sha256']==led['rustc_sha256']
            assert 'ohm-defaults' in dec['features'] and re.fullmatch(r'[0-9a-f]{64}',compiled['original_build_receipt'])
            if stage=='stamped':
                assert compiled['launch']['source']==FIX[n] and compiled['launch']['parents']==src['fixed']['parents']
                assert compiled['launch']['cpus']==[4,5,6,7] and compiled['launch']['uid']==1000 and compiled['launch']['root_uid']==0
                assert compiled['cargo_vv']==dec['stdout_vv'] and dec['build_trace']==compiled['trace']['sha256']
                assert {'bin','lib'}=={x['kind'] for x in compiled['compile_execves']} and compiled['git_queries']
                assert dec['legacy_fixed_binary']==led['arms']['fixed-'+n]['image']['declaration']['cargo']
            assert dec['cargo'] not in outputs;outputs.add(dec['cargo'])
            ph=z['phases']; prior=stage=='prior'
            assert z['value']==1 and z['first_success']==('untouched-1' if prior else 'reverted')
            assert ph['prime']['exit']==ph['prime-program']['exit']==ph['final-program']['exit']==0
            assert ph['forced-failure']['exit']==101 and ph['forced-failure']['rustcs']==[['dep','lib'],['app','lib']]
            assert ph['reverted']['rustcs']==([['dep','lib'],['app','bin']] if prior else [['dep','lib'],['app','lib'],['app','bin']])
            assert ph['reverted']['exit']==(101 if prior else 0) and ph['reverted']['errors']==(['E0460'] if prior else [])
            assert ('untouched-1' in ph)==prior and (not prior or ph['untouched-1']['exit']==0)
            assert recovery['forced_parent_started'] and recovery['forced_producer_failed'] and recovery['program_stdout']=={'prime':'1\n','final':'1\n'}
            assert all(ph[d]['files']['stdout']==h(b'1\n') for d in ['prime-program','final-program'])
            fi=r['fifo']
            for mode in ('default','no-ohm'):
                case=fi[mode+'/parent-error'];b=case['result']; flags=case['opens']['fifo']
                assert b['subject']==f'{stage}-{n}' and b['cargo']==dec['cargo'] and b['rustc']==led['rustc_sha256']
                assert b['mode']==mode and b['variant']=='parent-error' and b['rc']==101 and not b['deadline'] and b['parent_eisdir']
                assert len(flags)==b['fifo_open_calls']==(0 if prior else 1) and b['writer_processes']==0
                if flags: assert 'O_NONBLOCK' in flags[0]['flags'] and 'O_NOCTTY' in flags[0]['flags'] and flags[0]['returned']
                if stage=='stamped':
                    single=fi[mode+'/single-fifo']; b=single['result']; f=single['opens']['fifo']
                    assert b['deadline'] and b['timeout_seconds']==4 and b['rc']<0 and not b['parent_eisdir']
                    assert b['writer_processes']==0 and b['cargo']==dec['cargo'] and b['rustc']==led['rustc_sha256']
                    assert any('O_NONBLOCK' in entry['flags'] for entry in f)
                    assert any('O_NONBLOCK' not in entry['flags'] for entry in f)
            assert len(fi)==(4 if stage=='stamped' else 2)
            if prior:
                assert r['suites'] is None
                continue
            suite=r['suites']['sets']
            expect={'fingerprints':73,'conditional':7,'markers':1}
            if n=='103':expect['macro-marker']=1
            assert {s:t['passed'] for s,t in suite.items()}==expect
            for name,t in suite.items():
                stream=streams[stage+'-'+n+'/'+name]
                assert h(stream.encode())==t['stdout'] and t['tests']==[line for line in stream.splitlines() if line.startswith('test ') and line.endswith(' ... ok')]
                assert len(set(t['tests']))==len(t['tests'])==expect[name]
                assert all(s.endswith(' ... ok') for s in t['tests'])
                assert len(t['native_cargo_events'])==t['physical_cargo_calls']
                assert t['physical_cargo_calls']==(0 if name=='fingerprints' else 23 if name=='conditional' else 2)
                if stage=='stamped':
                    witness=t['mount_witness']
                    assert witness=={'mounted_product_sha256':dec['cargo'],'version_sha256':compiled['cargo_vv'],
                                     'commit':stamp,'same_inode':True,'uid':1000,'root_uid':0,
                                     'caps':{'CapEff':'0000000000000000','CapBnd':'0000000000000000','NoNewPrivs':'1'}}
                    assert r['suites']['userns_preflight']['prior_exit']==1 and r['suites']['userns_preflight']['test_processes']==0
                    sel=r['suites']['build_selection']
                    assert sel['test_build_binary']!=sel['product_binary']==dec['cargo'] and sel['first_suite_test_processes']==0
            assert any('committed_dependent_after_failed_producer_is_reverted' in s for s in suite['conditional']['tests'])
            fp=suite['fingerprints']['tests']
            for needle in ['speculative_short_fingerprint_follows_regular_symlinks_and_rejects_fifos','committed_short_hash_only_validates_one_current_comparison']:
                assert any(needle in t for t in fp)
        for select in ['fingerprints','conditional','markers',*(['macro-marker'] if n=='103' else [])]:
            before=led['arms']['fixed-'+n]['suites']['sets'][select]
            after=led['arms']['stamped-'+n]['suites']['sets'][select]
            assert before['tests']==after['tests']
    return True

if __name__=='__main__':
    led=json.loads((root/'results.json').read_bytes())
    assert validate(led)
    print('Verified both original E0460 controls, four fixed first reverts, six source/version bindings, 16 FIFO controls, and 163 passing standard tests for each fixed build series.')

