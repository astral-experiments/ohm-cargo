"""Offline verifier for committed typed native evidence, with no compiler invocation."""
import gzip
import hashlib
import json
from pathlib import Path
import sys

def hash_data(b):return hashlib.sha256(b).hexdigest()
def digests(t):return bool(t) and all(len(v)==64 and all(x in '0123456789abcdef' for x in v) for v in t.values())
def check_native(root):
    a=json.loads(gzip.decompress((root/'native.json.gz').read_bytes()));p=a['payload'];s=a['source_records_sha256'];assert set(p)==set(s)
    for k,v in p.items():
        if k!='provenance':assert hash_data((json.dumps(v,indent=2,sort_keys=True)+'\n').encode())==s[k],k
    assert p['provenance']['revision']=='93526150df078af7dd8fc4226cdcc469539d2001'
    registries=p['provenance']['registry']; assert len(registries)==11 and registries['ron-0.12.0']=='fd490c5b18261893f14449cbd28cb9c0b637aebf161cd77900bfdedaff21ec32'
    phase=p['registry_and_upstream']
    assert set(phase)=={'registry','editable'} and len(phase['registry'])==3 and len(phase['editable'])==7
    for case,entries in phase.items():
        for name,r in entries.items():
            assert r['ron_registry_features']==['default','std'] and not r['ron_fresh'] and r['full'].count('ron')==1 and r['incomplete_obs1'] and len(r['ron_argv'])==1
            assert r['argv'][:4]==['cargo','+ohm','build','--offline'] and digests(r['complete_trace_digests'])
            assert r['program_decodes']==(3 if name in ('edited','edited-repeat','cold-edited') else 2)
        for n in ('unchanged-1','unchanged-2'):
            r=entries[n];assert r['bitflags_fresh'] and r['full']==['ron','ron_native_probe'] and not r['link_only'] and r['wild_count']==1
    ed=phase['editable'];assert all('bitflags' in ed[n]['full'] for n in ('edited','restored')) and 'bitflags' not in ed['edited-repeat']['full']
    r=p['real_serde']['rows'];A='Extensions("IMPLICIT_SOME")';B='ChangedExtensions("IMPLICIT_SOME")'
    assert [v['program'] for v in r]==[A,A,B,B,B,A,A,B,B,A,A]
    checked={}
    for row in r:
        n=row['phase'];checked[n]=row;assert row['ron_marker'] and row['physical_full'].count('ron')==1 and 'observe_ron_serde' in row['physical_full']
        assert ('serde_derive' in row['physical_full'])!=row['dso_fresh'] and digests(row['trace_sha256'])
    assert not checked['true-edit']['dso_fresh'] and not checked['restore']['dso_fresh']
    assert checked['true-edit']['source_sha256']!=checked['cold']['source_sha256']==checked['restore']['source_sha256']
    # All observed same-configuration executables must match their independent clean state, including backdated alternation.
    for want,clean in ((A,'independent-restored'),(B,'independent-edited')):
        assert all(v['program_sha256']==checked[clean]['program_sha256'] for v in r if v['program']==want)
    switched=[checked[n] for n in ('same-size-A','backdated-external-B','unchanged-external-B','backdated-external-A')]
    for item in switched:assert item['dso_fresh'] and item['source_sha256']==checked['restore']['source_sha256']
    assert len({tuple(v['dso'][k] for k in ('dev','ino','mtime_ns','size')) for v in switched})==1
    assert len({v['dso']['sha256'] for v in switched})==2
    assert checked['true-edit']['dso']['sha256']==checked['independent-edited']['dso']['sha256']
    assert len(p['real_serde']['artifact_replacements'])==2
    scores={'registry_and_upstream_commands':sum(map(len,phase.values())),'real_serde_commands':len(r),'true_edit_elf':checked['true-edit']['program_sha256'],'restored_elf':checked['restore']['program_sha256'],'images':p['provenance']['images']}
    if 'dso_ron' in p:
        rows=p['native_ambient'];assert [r['program'] for r in rows]==['2 17','2 29','2 29','2 29','2 17','2 17'] and len(p['preliminary_ambient'])==5
        warm=[r for r in rows if not r['phase'].startswith('independent')]
        assert all(r['inputs']==warm[0]['inputs'] and r['dep_info']==warm[0]['dep_info'] for r in warm)
        assert all(not r['app_fresh'] and r['native_marker'] and not r['socket_present_in_declared_inputs'] and r['external_socket_inode_and_times_stable'] and r['compiler_trace'] and r['socket_traces'] and digests(r['trace_sha256']) for r in rows)
        for k in ('dso_ron','dso_socket'):
            e=p[k];assert e['calls']==e['calls_with_stack'] and not e['possible_unwind_failures'] and digests(e['trace_sha256'])
        ser=p['dso_ron']['macro_stack_calls'];assert len(ser)==1 and ser[0]['call']=='getrandom' and any('hashmap_random_keys' in f for _,f in ser[0]['macro_frames'])
        assert any(r['call']=='connect' and any('libambient_macro-' in m for m,_ in r['macro_frames']) for r in p['dso_socket']['macro_stack_calls'])
        scores.update(ambient_commands=len(rows),macro_syscall_phases=2,serde_random_dispatches=1)
    elif 'installer' in p:
        i=p['installer'];assert i['all_aliases_private'] and all(p['provenance']['images'][k]==i['images'][k] for k in ('rustc','cargo','driver'))
        assert i['sources']=={'cargo':'7caf39914da1e28a67744ecbc963a5f26361474d','rust':'a4fa11bcd38280639cb94daacc125472657db6c3'} and i['images']['wild']=='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'
    else:raise ValueError('unknown scope')
    return scores

def check_workspace(root):
    r=json.loads((root/'workspace.json').read_bytes());seal=json.loads((root/'fingerprint.json').read_bytes());m=json.loads((root/'rmeta.json').read_bytes())
    assert len(r)==5 and len(m['artifacts'])==3;roles={}
    for name,one in r.items():
        rec=one['genuine_observer_dir_at_read_time']['cargo_record'];h=one['history'];roles[name]=h['native']
        assert h['units']==619 and not one['declared_cargo_fresh'] and len(one['extern_files_at_read_time'])==6
        assert rec['blake3_seal']==seal['blake3'] and rec['body_sha256']==seal['body_sha256'] and seal['changing_status_detected']
        assert one['genuine_observer_dir_at_read_time']['cargo_record_sha256']==seal['record_sha256']
        assert [rec[k] for k in ('version','marker_status','marker_index','number_of_paths','checksummed','env_count')]==[2,0,11,20,0,0]
        if name.endswith('repeat'): assert h['fresh']==563 and h['native']=={'full':1,'link-only':50,'wild':50}
    assert len({r['invocation_sha256'] for r in r.values()})==1
    assert len({v['output_history']['ron_after']['.rlib'] for v in r.values()})==1
    assert set(m['artifacts'])=={v['output_history']['ron_after']['.rmeta'] for v in r.values()}
    vals=list(m['artifacts'].values());stable=vals[0]['stable_fields'];assert all(v['stable_fields']==stable for v in vals)
    assert [stable[k]['count'] for k in ('defs','expansion_hashes','source_table','allocations')]==[3240,1705,18,195]
    canonical=lambda v:sorted((x['source_byte'],x['map_method'],x['path_hash']) for x in v['synthetic_lifetime_order'])
    assert all(canonical(v)==canonical(vals[0]) for v in vals)
    assert all(sum(n for _,n in f['ranges'])==f['bytes_different']==138 for f in m['byte_deltas'].values())
    return {'workspace_phases':len(r),'two_unchanged_workspace_native':roles['rehearsal-workspace-repeat'],'decoded_ron_metadata_variants':len(vals)}

if __name__=='__main__':
    d=Path(__file__).resolve().parent;ans=check_native(d)
    if (d/'workspace.json').exists():ans.update(check_workspace(d))
    print(json.dumps(ans,indent=2,sort_keys=True))
