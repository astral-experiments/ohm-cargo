"""Report native publication bounds in the six registered, ordinary edited builds."""
import json
from pathlib import Path
import statistics
import sys

root=Path(__file__).resolve().parent
def score(path):
    body=json.loads(path.read_bytes())
    rows=body['samples']
    assert len(rows)==6 and body['admission']['trained']==[248,True]
    assert body['admission']['images']=={'cargo':'02a86ebd2d9e4f237b33f212102b81ed145eb77fae090d67e379cb6f1d70a573',
        'rustc':'c6ab483d6698f68eebb49d74b27361f3e02ede55452dc0416c3fdec9a45b7f60','wild':'0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'}
    names=sorted('ruff_db ruff_linter ruff_python_ast ruff_python_codegen ruff_python_importer ruff_python_index ruff_python_literal ruff_python_parser ruff_python_semantic ruff_ranged_value'.split())
    stats=[]
    pre=body['admission']['origin']
    for n,row in enumerate(rows):
        parent=n%2==0
        assert row['direction']==('parent' if parent else 'historical')
        assert row['before']==pre and row['consumer']['linter']!=pre
        assert row['consumer']['exit']==0 and row['consumer']['stdout']==('2 SIM222\n3 SIM222\n4 SIM222\n' if parent else '1 SIM222\n')
        pre=row['consumer']['linter']
        edit,rep=(row['phases'][k] for k in ('edit','repeat'))
        assert edit['dirty']==names and rep['dirty']==[] and rep['bounds'] is None
        actual=edit['record']
        assert actual['returncode']==rep['record']['returncode']==0 and not rep['record']['events']
        events=actual['events'];assert [v['role'] for v in events]==['create','publish','remove']
        a,b,c=events
        assert a['name']==c['name'] and a['name'].endswith('.temp-archive') and b['name']=='<archive>'
        assert b['cookie'] and all(v['hi']>=v['lo'] for v in events)
        bounds=edit['bounds']
        assert bounds=={'lo':max(0,b['lo']-a['hi']),'hi':b['hi']-a['lo'],'create_bracket':a['hi']-a['lo'],'publish_bracket':b['hi']-b['lo']}
        loop=actual['command_ns']+rep['record']['command_ns']
        stats.append(dict(n=n+1,direction=row['direction'],lower_ms=bounds['lo']/1e6,upper_ms=bounds['hi']/1e6,
                          create_bound_ms=bounds['create_bracket']/1e6,publish_bound_ms=bounds['publish_bracket']/1e6,
                          edit_s=actual['command_ns']/1e9,repeat_s=rep['record']['command_ns']/1e9,
                          low_share=100*bounds['lo']/loop,high_share=100*bounds['hi']/loop,
                          edit_low_share=100*bounds['lo']/actual['command_ns'],edit_high_share=100*bounds['hi']/actual['command_ns'],
                          observer_edit_cpu_ms=actual['observer_cpu_ns']/1e6,observer_repeat_cpu_ms=rep['record']['observer_cpu_ns']/1e6))
    return {'medians':{k:statistics.median(s[k] for s in stats) for k in stats[0] if k not in ('n','direction')},'observed':stats}

if __name__=='__main__':
    for name in sys.argv[1:]:
        print(name,json.dumps(score(Path(name)),sort_keys=True,indent=2))
