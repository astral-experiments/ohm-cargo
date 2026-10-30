"""Verify checkout ordering against all retained session names, table filenames and producer observations."""
import gzip,hashlib,json,sys
from pathlib import Path
def verify(p,out):
    import importlib.util
    z=importlib.util.spec_from_file_location("checkout_decoder",out/"decisions.py");module=importlib.util.module_from_spec(z);z.loader.exec_module(module)
    hasher,parsed=module.hasher,module.parsed
    obj=json.loads(gzip.decompress((out/'checkout-sessions.json.gz').read_bytes()))
    src=obj['row_sources'];rows=obj['units'];assert len(rows)==20
    labels=obj['checkout_keys']
    assert labels=={'A':hasher(b'ref: refs/heads/historical-parent'),'B':hasher(b'ref: refs/heads/historical-feature')}=={'A':'3372b4745d5226e8','B':'a3a1413392b7d81d'}
    assert obj['compiler_that_ran']=='8ea2252344ba85e7406f4f04f979053e2bd191b1' and obj['counterfactual_compiler']=='08d49cba6aacb0cac27a96eea335ed1c7439f483'
    assert obj['source_blobs']['8ea_fs']=='fc9ebb14bf974ad9cd86371d926f59c62f2dfea9' and obj['source_blobs']['08d49_fs']=='2c9ba9c02cc657ef34c05b3fd88c215ce4c000fd'
    for k,v in src.items():
        ref=p['slots']['on-storage'][k]['ledgers']
        assert v=={'table-ledger.json':ref['tables'],'physical-native.json':ref['kernel'],'result.json':ref['native_terminal']}
    seen=set();switches=cold=fresh=packed=0;per_phase={}
    for row in rows:
        unit=row['unit'];assert unit['crate_directory']==module.stable_crate_directory(unit['crate'],[unit['metadata']],unit['crate_type'],obj['cfg_version']);key=tuple(unit[k] for k in ('crate','metadata','incremental'))
        assert key not in seen and not Path(key[2]).is_absolute();seen.add(key)
        prior={};stages=row['stages']
        assert [k['phase'] for k in stages]==['empty-A','first-B','return-A','return-B','unchanged-B']
        for phase in stages:
            tag=phase['phase'];active=tag[-1];key=labels[active];assert phase['active_checkout']==active
            after=phase['after'];before=phase['before'];assert before==prior
            for name,s in after.items():
                assert s['crate_dir']==unit['crate_directory'];time,checkout=parsed(name);assert (time,checkout)==(s['timestamp_us'],s['checkout_key']) and s['checkout_key'] in labels.values()
                assert set(s['tables'])=={'packed' if v['packed'] else 'raw' for v in s['files'].values()}
                for f,v in s['files'].items():
                    assert v['packed']==f.startswith('ohm-packed-') and v['bytes']>0 and v['allocated']>0 and v['names_of_inode']>0
                assert any('dep-graph' in f for f in s['files']) and any('query-cache' in f for f in s['files'])
            assert len({s['timestamp_us'] for s in before.values()})==len(before)
            newest=max(before.values(),key=lambda v:v['timestamp_us'],default=None)
            saw=any(v['checkout_key']!=key for v in before.values());different=bool(newest and newest['checkout_key']!=key)
            assert phase['previous_newest']==newest and phase['older_policy_if_invoked']==saw and phase['switch_policy_if_invoked']==different
            new=set(after)-set(before);assert new==set(phase['new_sessions'])
            if tag=='unchanged-B':
                assert not phase['rustc_ran'] and before==after and not new and saw and not different
                assert phase['same_decision_exercised'] is None;fresh+=1
            else:
                assert len(new)==1 and phase['rustc_ran'] and phase['same_decision_exercised'] and saw==different
                x=after[new.pop()];assert x['checkout_key']==key and ((x['tables']==['packed'])==saw)
                if before:assert saw and x['timestamp_us']>newest['timestamp_us'];switches+=1;packed+=len(x['files'])
                else:assert not saw and x['tables']==['raw'];cold+=1
            per_phase.setdefault(tag,set()).add((saw,different,phase['rustc_ran']));prior=after
    assert (len(seen),switches,cold,fresh)==(20,60,20,20) and packed>=120
    return {'identities':20,'cold_no_pack':cold,'actual_switches_both_predicates_pack':switches,'actual_fresh_final_b_rustc':p['slots']['on-storage']['unchanged-B']['physical'].get('SDK rustc',0),'final_B_units_unchanged':fresh,'new_packed_table_names_across_three_switches':packed,'source_only_alternative':'08d49cba6aacb0cac27a96eea335ed1c7439f483'}
if __name__=='__main__':
    q=Path(sys.argv[1]);print(json.dumps(verify(json.loads(q.read_bytes()),q.parent),sort_keys=True,indent=2))
