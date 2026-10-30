"""Exercise independent rejection paths with replaced observations in memory."""
from pathlib import Path
import copy,importlib.util,json
D=Path(__file__).resolve().parent
def load(name,filename):
    sp=importlib.util.spec_from_file_location(name,D/filename);m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m);return m
own=load('whole_audit','audit.py');cls=load('class_audit','verify-file-classes.py')
def reject(name,func):
    try:func()
    except AssertionError:return name
    raise ValueError(name+' unexpectedly passed')
def verify_all(obs):
    rejected=[]
    def mutate(name,slot,phase,change):
        r=copy.deepcopy(obs);change(r['slots'][slot]['phase'][phase]);rejected.append(reject(name,lambda:own.native(r)))
    mutate('settled hardlink intersection','off-storage','empty-A',lambda x:x['settled'].__setitem__('both_roots_same_inode',x['settled']['both_roots_same_inode']+4096))
    mutate('increased peak outside sampled trace','off-storage','empty-A',lambda x:x['sampler'].__setitem__('max_observed',x['sampler']['max_observed']+4096))
    mutate('changed physical Wild launches','off-storage','first-B',lambda x:x['physical'].__setitem__('stock Wild',0))
    mutate('unexpected compiler on fresh B','off-storage','unchanged-B',lambda x:x['physical'].__setitem__('SDK rustc',1))
    def forge_cold(x):
        x['cli']['sha256']='0'*64;x['custody']['ruff']['sha256']='0'*64;x['custody']['ruff']['retained_bytes']='0'*64
    mutate('entire independently empty B executable','off-clean-B','empty-B',forge_cold)
    r=copy.deepcopy(obs);q=r['slots']['on-storage']['kit']['bin/cargo'];q[1]+=1
    rejected.append(reject('distinct SDK Cargo inode with identical digest',lambda:own.native(r)))
    if 'category' in obs['slots']['off-storage']['phase']['empty-A']:
        phase=obs['slots']['off-storage']['phase']['empty-A'];where=D/'classes/off-storage--empty-A.jsonl.gz'
        def class_bad(k,change):
            z=copy.deepcopy(phase['category']);change(z);rejected.append(reject(k,lambda:cls.one(where,z,phase)))
        class_bad('reclassified native object charge',lambda z:z['classes']['native-object'].__setitem__('bytes',z['classes']['native-object']['bytes']+4096))
        class_bad('physical namespace ledger without inode bound',lambda z:z.__setitem__('physical_ledger_sha256','0'*64))
    return rejected
if __name__=='__main__':
    evidence=json.loads((D/'observations.json').read_bytes());print(json.dumps({'rejected':verify_all(evidence)},indent=2,sort_keys=True))
