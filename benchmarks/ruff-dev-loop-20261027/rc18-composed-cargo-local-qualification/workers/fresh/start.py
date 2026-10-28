"""Run the published worker's six authenticated trained cases on the current physical toolchain."""
from pathlib import Path
import hashlib, json, os, subprocess, sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import exercise
R=Path('/home/dev-user/.cache/ohm-rc18-current-epoch-20261028');SDK=Path('/dev/shm/ohm-published-member-h2-20261028/installed17')
if len(sys.argv)>1:
    rows={}
    for kind in exercise.KINDS:
        for stamp in ('current','preserved'):
            n='trained-'+kind+'-'+stamp;rows[n]=exercise.case(R/n,SDK,kind,True,stamp)
            j=json.loads((R/n/'report.json').read_bytes())
            assert j['rows']['again']['fresh'] and j['rows']['again']['initially_complete'] and j['rows']['again']['value']==17 and j['rows']['clean']['value']==29
            print(n,'old source=29; trained target=17; empty=29',flush=True)
    (R/'complete.json').write_text(json.dumps(rows,indent=2,sort_keys=True)+'\n')
else:
    assert exercise.sha(SDK/'bin/cargo')=='4e4065390403afbf4fb77b2f41fbc21c59afe3dda2337a5bbe29fda29a47dbb3'
    R.mkdir(mode=0o700)
    subprocess.run(['bwrap','--die-with-parent','--ro-bind','/','/','--dev','/dev','--proc','/proc','--ro-bind','/dev/shm','/dev/shm','--tmpfs','/tmp','--bind',str(R),str(R),'--','taskset','-c','8-11',sys.executable,'-B',__file__,'inner'],check=True)
