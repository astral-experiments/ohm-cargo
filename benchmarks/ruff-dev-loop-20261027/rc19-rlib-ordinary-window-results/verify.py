import hashlib
import json
from pathlib import Path
import runpy

here=Path(__file__).resolve().parent
score=runpy.run_path(str(here/'score.py'))['score']
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
assert sha(here/'window.py')=='1d9c3ac1f9ef7721adba2f0044864cb3697dc8cb9cea56b4419b8a17751e33ce'
for host,expected in [('genoa',(167.1,169.4,1.64)),('milan',(463.0,465.9,3.69))]:
    file=here/(host+'.json')
    s=score(file)
    m=s['medians']
    assert (round(m['lower_ms'],1),round(m['upper_ms'],1),round(m['high_share'],2))==expected
    provenance=json.loads((here/(host+'-attempts.json')).read_bytes())
    closed=provenance[-1]
    assert closed['worker_complete'] and closed['closed_sha256']==sha(file) and closed['complete_pairs']==6
    assert all(t['expected']==t['declared'] for t in closed['training']) and closed['training'][-1]['fresh']==248
    if host=='milan':
        assert len(provenance)==1 and closed['outer_exit']==0
    else:
        assert [v['outer_exit'] for v in provenance]==[1,1,1]
        assert [v['failure'] for v in provenance]==['git-identity-preflight','unit-path-preflight','outer-mount-busy']
        assert [v['complete_pairs'] for v in provenance]==[0,0,6]
        assert not provenance[0]['training'] and provenance[1]['training'][0]['fresh']==0
        pre=provenance[1]['training'][0]
        assert pre['declared']!=pre['expected'] and Path(pre['declared']).name==Path(pre['expected']).name
    print(host, round(m['lower_ms'],2), round(m['upper_ms'],2), 'ms,', round(m['high_share'],3), 'percent maximum loop share')
custody=json.loads((here/'teardown.json').read_bytes())
assert not custody['external_mount'] and not custody['attached'] and custody['compiler_and_linker_processes']==[]
