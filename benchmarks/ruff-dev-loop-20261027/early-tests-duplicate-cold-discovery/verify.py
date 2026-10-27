from collections import Counter
from pathlib import Path
import gzip,json
p=Path(__file__).resolve().parent;x=json.loads(gzip.decompress((p/'cold-census.json.gz').read_bytes()));assert set(x)=={'C','D'}
for arm,data in x.items():
    groups=data['groups'];assert data['total_compilers']==636 and data['distinct_argv']==623 and data['duplicate_calls']==data['duplicate_groups']==len(groups)==13
    assert len({a['rustc_complete_argv_sha256'] for a in groups})==13
    assert len({tuple(sorted(a['rustc_ids'])) for a in groups})==13 and len({n for a in groups for n in a['rustc_ids']})==26
    status=Counter();link_status=Counter()
    for row in groups:
        assert row['has_test']==(row['target'] not in {'crates/ruff_python_parser/tests/fixtures.rs','crates/ruff_python_formatter/tests/fixtures.rs','crates/ruff_mdtest/tests/mdtest.rs'})
        assert row['target'].endswith('.rs') and row['target'].startswith('crates/') and '/tests/' in row['target']
        assert len(row['cargo_rows'])==1 and row['cargo_rows'][0]['kind']==['test'] and row['cargo_rows'][0]['profile']['test'] and not row['cargo_rows'][0]['fresh']
        assert row['own_extern'] and len(row['rustc_ids'])==2 and len(row['native_links'])==1
        for pid in row['rustc_ids']:
            stats=row['rustc_exit_signal_observations'][pid];assert len(stats)==1 and stats[0][0]=='CLD_EXITED';status[stats[0][1]]+=1
        current=row['native_links'][0];assert current['out'].startswith('$RUN/') and row['extra_filename'] in current['out']
        for proc in current['successful_execs']:
            stat=proc['terminal'];link_status[str(stat)]+=1;assert not stat or stat==[['CLD_EXITED','0']]
    assert status==({'0':26} if arm=='C' else {'0':25,'1':1})
    assert data['total_wild']==(201 if arm=='C' else 200) and data['distinct_wild_output_paths']==188
    assert data['duplicate_wild_output_calls']==(13 if arm=='C' else 12)
    print(arm,data['duplicate_calls'],dict(status),data['duplicate_wild_output_calls'],dict(link_status))
