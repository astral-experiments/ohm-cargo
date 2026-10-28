import argparse
import collections
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys

P=Path(__file__).resolve().parent

def read(p):
    p=Path(p);return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())

def digest(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def signature(j):return hashlib.sha256((json.dumps(j,sort_keys=True,indent=2)+'\n').encode()).hexdigest()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--archive',type=Path);parser.add_argument('--catalog',type=Path);a=parser.parse_args()
    for row in (P/'SHA256SUMS').read_text().splitlines():
        h,name=row.split('  ',1);assert digest(P/name)==h,(name,h)
    x=read(P/'rc18-census.json.gz'); y=read(P/'earlier-e2e-inputs.json.gz'); z=read(P/'shadow.json'); i=read(P/'independent-native.json');cap=read(P/'acquisition.json');stored=read(P/'earlier-cargo-recipes.json'); stop=read(P/'first-reporter-stop.json')
    assert stop['scored_slots']==0 and stop['controller_stderr_sha256']
    assert signature(z)==i['complete_result_json'] and signature(cap)==i['capture_receipt_json']
    rs=x['phases']; phases=['cold','unchanged','edited','restored','final-unchanged'];assert len(rs)==5
    for ph in (phases[1],phases[-1]):
        c=rs[ph];assert (c['units'],c['fresh'],c['counts'])==(619,563,{'full':1,'link-only':50,'collect2':50,'wild':50,'cargo':1});assert c['dirty_libraries']==sorted(['ron','insta','insta_cmd','mdtest','ruff_mdtest','ty_test']); assert len(c['target_rows'])==50 and len({v['file']for v in c['target_rows']})==50
        assert sum(bool(v['ron'])for v in c['target_rows'])==c['with_ron']==35 and len(c['without_ron'])==15 and c['full_rustc']==['ron']; assert set(c['native_directory_families'].values())=={16,21,13}
        assert all(v['raw_dylibs_first'] and v['native_path_family'][0]=='psm' and v['library_names']==['gcc_s','util','rt','pthread','m','dl','c']and not v['explicit_threads']for v in c['target_rows'])
        assert c['e2e_rustc_argv_count']==737 and (c['e2e_wild']['argc'],c['e2e_wild']['rlibs'],c['e2e_wild']['codegen_objects'],c['e2e_wild']['search_count'])==(446,250,139,13)
    for f in x['fanout_argv'].values():
        assert f['only_three_transient_fields']==50 and f['earlier_occurrence_counts']=={'1':50} and len(f['rows'])==50
        assert all(r['before_physical_occurrences']==len(r['comparisons_to_single_repeat'])==1 and next(iter(r['comparisons_to_single_repeat']))['mismatches']=={'GCC plugin resolution pathname':1,'rustc raw-dylibs search directory':1,'rustc symbol object pathname':1} for r in f['rows'].values())
    old='273bacc28190231ae32fc61b30ab8c8c41a1e7d1d47b9a215c68231ef7f51738'; ed='fa4f1c0712ff4b8b4805e266b2e8bc4f14b740b351943322c48e7e2d285c09c2'
    assert [rs[k]['e2e_elf']['sha256']for k in phases]==[old,old,ed,old,old] and [rs[k]['e2e_elf']['size']for k in phases]==[225211904,225211904,225211808,225211904,225211904]
    assert [x['e2e_argv_comparison'][l+' to '+r]['differing_field_positions']for l,r in zip(phases,phases[1:])]==[3,142,142,3]
    name=z['name'];assert len(y['roles'])==5 and all(r['argv_line_keys']==446 and r['literal_inputs']==412 and sum(v['bytes']for v in r['groups'].values())==615586261 for r in y['roles'].values());
    for role in y['roles'].values():
        assert role['ron']==[['libron-b99685b70e2bcee4.rlib','41e67201eab0ccb3ffa005fa5da3066f5265647cbdb22f3b7fe2f2a7677de354',2114272]];w=role['widths']; assert len(w)==16 and len(set(w.values()))==2 and {w[str(i)]for i in range(2,17)}=={w['2']} and w['1']!=w['2']; assert z['previous_exe_sha256']==w['1']
    for arm in ('composed','observer'):
        q=y['pairs']['selected-'+arm+('#2'if arm=='observer'else'#1')+' -> repeat-'+arm+'#1']; assert q['same_literal_paths']==410 and q['content_multiset_identical'] and not q['differing_same_path_resolution'] and q['removed_contents']==q['added_contents']==0
        rc=stored[arm]['candidates']['out/'+name+'.rlink-cache.json']; assert rc['version']==5 and rc['objects_count']==139 and sorted(rc['executable_keys'])==['len','modified_nanos','path']; assert re.fullmatch('[0-9a-f]{64}',rc['rlink_record']);
    assert stored['composed']['candidates']['out/'+name+'.rlink']['sha256']==z['recipe_sha256'] and z['recipe_sha256']!=stored['observer']['candidates']['out/'+name+'.rlink']['sha256']
    assert (z['still_available_positive_files'],z['still_available_positive_bytes'])==(410,615547333); assert z['stock_wild']==cap['stock']=='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'; assert z['cpus']==i['cpu_mask']==cap['cpu_mask']==[24,25,26,27] and not z['cargo_jobserver_forwarded'] and not cap['jobserver']
    a0,a1,a2,a3=z['phases']; assert [v['phase']for v in z['phases']]==['original','earlier-object','invalid-earlier-file','restored']; assert [v['rustc_exit']for v in z['phases']]==[0,0,1,0] and [v.get('list_exit')for v in z['phases']]==[0,83,None,0] and [v.get('listed_tests')for v in z['phases']]==[200,0,None,200]
    assert a0['elf_sha256']==a3['elf_sha256']==w['2']==cap['e2e_elf'] and a0['elf_bytes']==a3['elf_bytes']==227926992; assert a1['elf_sha256']not in w.values() and a2['diagnostic_mentions_shadow']; assert a0['list_sha256']==a3['list_sha256']==cap['listing']==z['previous_list_sha256']
    for row,p in zip(i['proof'],z['phases'],strict=True):
        assert row['phase']==p['phase'] and row['raw_exec_summary_sha256']==p['overall_trace_sha256'] and [v['kind']for v in row['successful_execve']]==['rustc','cc','collect2','ld.bfd'];assert row['successful_execve'][0]['input_rlink'] and row['successful_execve'][-1]['event_sha256']==p['stock_wild_exec_sha256'];
    assert 'INVALID_LINK_SCRIPT_FOR_E2E_NEGATIVE' in str(i['proof'][2]['error_excerpt']) and cap['physical_donor_unchanged'] and cap['literal_argc']==446 and cap['change_count_in_native_argv']==3 and cap['permissions']=='0o600'
    assert cap['temporary_operands']['resolution.res']==[hashlib.sha256(b'').hexdigest(),0] and cap['temporary_operands']['symbols.o']==[y['roles']['repeat-composed#1']['symbols'],38928] and cap['raw_dylibs_mode']=='empty-directory' and cap['still_existing_positive_bytes']+38928==615586261
    if a.archive:
        import importlib.util
        cs=importlib.util.spec_from_file_location('frozen_census',P/'census.py');census=importlib.util.module_from_spec(cs);cs.loader.exec_module(census);assert census.summarize(a.archive)==x
    if a.catalog:
        f=read(a.catalog);assert f['target'].endswith('/'+name) and f['raw_private_evidence']=='cf759d32f165dd6819eec5b2e2522e1be5902a7c30e6d75d3949c2da0b221b01';assert len(f['recipes'])==len(y['roles'])
        for k,r in f['recipes'].items():
            role=y['roles'][r['phase']+'#'+str(r['ordinal'])]; assert role['recipe']==k and role['raw_input_file_sha256']==r['exact_physical_input_json_sha256'] and role['default_output']==r['raw_default'];assert {str(v['width']):v['plain_sha256']for v in r['widths']}==role['widths'] and all(v['plain_exit']==v['depfile_exit']==0 and v['plain_sha256']==v['depfile_sha256']for v in r['widths']);assert r['positive_bytes']==615586261
    print('PASS: 2 x 50 -18 jobs, 5 real earlier e2e acquisitions, 160 width-output comparisons, real exit 0/83/link-fail/0, 410 unchanged persistent files, and a separate complete temporary-input capture.')

if __name__=='__main__':main()
