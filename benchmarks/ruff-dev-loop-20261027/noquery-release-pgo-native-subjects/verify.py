"""Verify the sealed admission, including the original whole-ELF failure and raw native controls."""
from pathlib import Path
import gzip,hashlib,itertools,json,re,tarfile
root=Path(__file__).resolve().parent
raw=lambda path:(root/path).read_bytes()
read=lambda tar,name:json.load(tar.extractfile(name))
sha=lambda data:hashlib.sha256(data).hexdigest()
plan=json.loads(raw('registration.json'));bind=plan['eligible_immutable_inputs']; arms=('seed','A','A-repeat','Q','N');original=json.loads(raw('unmodified-build-record.json'))
assert plan['observed_timed_ruff_commands']==0 and not plan['claimed_performance_endpoints'] and plan['new_contract_does_not_authorize_timing']
assert original['strict_raw_baseline_gate']==False and original['terminal_exit']==1 and original['scored_trials']==0
assert len({row['exe_sha256'] for row in bind['cargo'].values()})==5
assert sha(raw('narrow-inputs.tar.gz'))==plan['complete_original_tar_sha256']
with tarfile.open(root/'narrow-inputs.tar.gz') as t:
    assert not any('complete.json'==p for p in t.getnames())
    assert t.extractfile('shared-generation.json').read()==raw('unmodified-build-record.json')
    assert sha(t.extractfile('build.py').read())==sha(raw('workers/build-pinned.py'))
    srcs={k:read(t,k+'/actual-inputs.json') for k in arms}
    for k in arms:
        receipt=read(t,k+'/receipt.json');assert receipt==original['matched'][k]
        assert receipt['subject']==bind['cargo'][k]['source'] and receipt['binary']==bind['cargo'][k]['exe_sha256']
        assert receipt['compiler']==bind['common_cargo_builder'] and receipt['profile']==bind['external_production_profile'] and receipt['source_verified']==3108
        assert receipt['jobs']==[['cargo','bin'],['cargo','lib']]
        assert len(srcs[k])==2
        for src,row in srcs[k].items():
            assert len(row['native'])==404
            if src=='src/lib.rs':
                assert len(row['externs'])==80 and sum(map(len,row['externs'].values()))==159
            else:
                assert src=='src/bin/cargo/main.rs' and len(row['externs'])==81
            row['externs'].pop('cargo',None)
        assert sha(json.dumps(srcs[k],sort_keys=True,separators=(',',':')).encode())==receipt['common_nonproduct_inputs_sha256']==bind['expected_actual_common_argv_and_dependency_files_sha256']
        assert srcs[k]==srcs['seed']
    detailed=read(t,'complete-symbol-deltas.json')
    assert detailed==json.loads(gzip.decompress(raw('full-symbol-changes.json.gz'))) and sha(raw('full-symbol-changes.json.gz'))==plan['all_symbol_changes_sha256']
    assert len(detailed['pairs'])==3 and len(detailed['stages'])==5
    assert {r['entire_file_after_fixed_fields_masked_sha256'] for k,r in detailed['stages'].items() if k in ('A','A-repeat','seed')}=={'c7fb34d6563e5bf87aa29cfaf098694d0584f16d4528b93f051ea07d9d30b81b'}
    assert all(detailed['stages'][k]['raw_sha']==bind['cargo'][k]['exe_sha256'] for k in arms)
    changes=set()
    for key,pair in detailed['pairs'].items():
        assert pair['whole_raw_equal']==False and pair['unchanged_entire_file_except_number_suffixes_and_build_id'] and pair['identical_dynamic_names']
        assert pair['full_symbols']==69183 and pair['strtab_roster']==69184 and pair['differing_bindings']=={'0':53,'1':89} and len(pair['symtab_changes'])==142
        cur=set()
        for q in pair['symtab_changes']:
            left=re.fullmatch(r'(.+)\.llvm\.([0-9]+)',q['old']);right=re.fullmatch(r'(.+)\.llvm\.([0-9]+)',q['new'])
            assert left and right and left[1]==right[1] and left[2]!=right[2] and len(left[2])==len(right[2])
            cur.add((q['symtab_index'],q['binding'],q['section_index'],q['value'],q['bytes'],left[1]))
        assert len(cur)==142
        if changes:assert changes==cur
        changes=cur
    for name in ('elf-seed-A.json','elf-A-A-repeat.json'):
        elf=read(t,name);assert set(elf['differences'])=={'.note.gnu.build-id','.strtab'}
        for x in elf['differences'].values():assert not x['payload_equal'] and not x['different_header_fields']
with tarfile.open(root/'independent-donors.tar.gz') as t:
    r=read(t,'release-input-audit.json');assert r['summary']==plan['prior_raw_gate']['earlier_raw_extern_disagreement']
    assert set(r['summary']['src/lib.rs']['N']['differ'])=={'curl','git2','gix','rusqlite'}
    for who in ('Q','N'):assert r['summary']['src/lib.rs'][who]['argv_equal']
    for who in ('A','Q','N'):assert read(t,'complete.json')[who]['binary']==plan['prior_raw_gate']['earlier_images'][who]!=bind['cargo'][who]['exe_sha256']
with tarfile.open(root/'pinned-native-records.tar.gz') as t:
    states=read(t,'receipt.json');assert len(t.getmembers())==106 and t.extractfile('receipt.json').read()==raw('native-guards.json') and sha(raw('native-guards.json'))==plan['required_native_receipt_sha256']
    for kind,z in states.items():
        who=kind[0];assert z['cargo']==bind['cargo'][who]['exe_sha256'] and z['compiler']==bind['rust']['common_frontend_sha256']
        assert z['driver']==bind['rust']['older_driver_sha256' if kind=='N-legacy' else 'producer_driver_sha256']
        rr=z['rows'];assert rr['first']['stamps']==rr['changed']['stamps'] and rr['first']['real']!=rr['changed']['real']
        for lab,row in rr.items():
            b=kind+'/case/records/'+lab+'/'; get=lambda n:t.extractfile(b+n).read()
            dep=get('rustc.d');fp=get('fingerprint')
            assert sha(dep)==row['dep_sha'] and sha(fp)==row['fp_sha'] and fp[-41:-37]==b'OBS1' and fp[-33]==row['complete']
            assert get('native').decode()==row['native'] and row['value']==(17 if lab=='first' else 29)
            lines=[json.loads(x) for x in get('stdout.jsonl').splitlines()]
            picked,=[o for o in lines if o.get('reason')=='compiler-artifact' and o['target']['name']=='hold_direct']
            assert picked['fresh']==row['fresh']==(lab=='noop') and lines[-1]['success']
            if lab in ('first','empty'):
                assert row['complete']==int(kind in ('Q-common','N-common'))
                assert (b'# ohm-observer-inputs-v1 ' in dep)==(kind in ('A-common','N-common'))
            assert row['queries']==int(who=='Q' and lab!='noop') and row['caller_full_compiles']==int(lab!='noop')
            events=[];pending={}
            for line in get('exec').decode().splitlines():
                m=re.match(r'(\d+)\s+(.*)',line)
                if not m:continue
                pid,msg=m.groups()
                if msg.startswith('execve('):
                    if msg.endswith('<unfinished ...>'):
                        pending[pid]=msg[:-len('<unfinished ...>')];continue
                elif msg.startswith('<... execve resumed>'):
                    if pid not in pending:continue
                    msg=pending.pop(pid)+msg[len('<... execve resumed>'):]
                else:continue
                if re.search(r'= 0\s*$',msg) and re.match(r'execve\("[^"]+/(active-sdk|rustup/toolchains/ohm)/bin/rustc"',msg):events.append(msg)
            assert sum('"--crate-name", "hold_direct"' in v and '"--print=' not in v for v in events)==row['caller_full_compiles']
            assert sum('"-Zohm-observer-dep-info", "--print=sysroot"' in v for v in events)==row['queries']
print('Verified five release builds, four-way exact Rust/native inputs, three unequal raw baseline comparisons, 426 enumerated symbol differences and 16 native observer guards. Zero timed Ruff commands.')
