"""Summarize 28 reviewer-generated control and ordinary installations from replay_one.py."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
from analyze import PHASES,one

def read(path):return json.loads(path.read_bytes())
def summarize(root,schedule):
    order=schedule['order'];assert len(order)==28 and len(set(order))==28
    tools={};known={};inventory=set();slots={};inputs={}
    for slot in order:
        base=root/slot;id=read(base/'identity.json');arm=slot[-1]
        assert tools.setdefault(arm,id)==id;file=base/'results.json';rows=read(file)
        inputs[slot]=hashlib.sha256(file.read_bytes()).hexdigest()
        control=slot.startswith(('admit-','post-'))
        expected={'empty-B','first-A','return-B','return-A','invalid-A','recovered-A','unchanged-A'} if control else set(PHASES)
        assert set(rows)==expected
        for name,row in rows.items():
            assert row['exit']==(101 if name=='invalid-A' else 0)
            if name=='invalid-A':continue
            rev=name.rsplit('-',1)[1];assert rev in 'AB' and known.setdefault(rev,row['ELF'])==row['ELF']
            inventory.add(row['inventory']);assert row['tests']==53 and len(inventory)==1
            if name.startswith('return'):assert sorted(row['dirty'])==['ruff_db','ruff_python_ast','ruff_python_formatter','ruff_python_parser']
            if name.startswith('unchanged'):assert not row['dirty']
        if not control:slots[slot]=rows
    assert len(known)==len(set(known.values()))==2
    assert tools['P']['driver']!=tools['Q']['driver'] and {k:v for k,v in tools['P'].items() if k!='driver'}=={k:v for k,v in tools['Q'].items() if k!='driver'}
    metrics={};orders=schedule['pairs']
    for phase in PHASES:
        metrics[phase]={}
        for kind in ('wall_s','cpu_s','with_git_s'):
            def cost(arm,i):
                row=slots[f'n{i:02d}-{arm}'][phase]
                if kind=='cpu_s':return row['user_s']+row['system_s']
                if kind=='wall_s':return row['wall_ns']/1e9
                return (row['wall_ns']+row['git_ns'])/1e9
            metrics[phase][kind]=one([(cost('P',i),cost('Q',i)) for i in range(1,13)],orders)
    return {'scope':'separate user-supplied local replication','observations':inputs,'identities':tools,'same_source_ELFs':known,'test_listing':list(inventory)[0],'phase_metrics':metrics}
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('reports',type=Path);p.add_argument('schedule',type=Path);a=p.parse_args()
    print(json.dumps(summarize(a.reports,read(a.schedule)),sort_keys=True,indent=2))
