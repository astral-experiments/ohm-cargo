"""Qualify the two release-profile Cargo executables on a genuine Ruff edit and its clean rebuild."""
from collections import Counter
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys

root=Path.home()/'.cache/ohm-18-ty-e2e-link-20261028';study=root/'native-ready-order19';reports=study/'reports';ops=root/'ops';worker=ops/'native-order-primary-v4.py';lane=study/'native-order-lane.py'
images={'A':'6aaa263e68d2d77aeb8977166f9744f1fa8e0ea4df3216fe516355be68517bac','B':'419200f1010d167502103a3f1964c937eec8c22ade26a021309718b854363f94'}
read=lambda path:json.loads(path.read_bytes())
def sha(path):
    with path.open('rb') as fd:return hashlib.file_digest(fd,'sha256').hexdigest()
def dump(path,obj):
    with path.open('x') as fd:json.dump(obj,fd,sort_keys=True,indent=2);fd.write('\n')
def call(*args):return subprocess.run([sys.executable,'-IB',lane,*args],check=True)
def run(batch,arm,mode,state,shape,label):call('run',batch,arm,'--',sys.executable,'-IB',worker,mode,arm,state,shape,label)
def census(batch,arm,state,shape,phase):
    label='gate-v4-'+arm+'-'+phase;run(batch,arm,'census',state,shape,label);assert (reports/label/'result.json').is_file()

assert sha(lane)=='57fb5d806c115856aafa96ffb1fb69b56a585d1a912c768236bd4bb407d5c253'
mode=sys.argv[1];roles=[x.upper() for x in sys.argv[2:]];assert mode in ('warm-gate','cold-gate','compare')
assert sha(worker)=='ab724484def80ccdf10d34d6d4128776567a7403bbb13c36a83cf9a3cacfe62a'
assert sha(ops/'native-order-product-roster.json')=='27875afe1aa700922fbb5f0916e943ac75199efb4d756c5d2c22cdf65f7f628e'
for arm,digest in images.items():assert sha(study/'images'/arm)==digest
lock=(root/'measure.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
if mode!='compare':
    assert len(roles)==1 and roles[0] in images;arm=roles[0]
    if mode=='warm-gate':
        call('edit','qa',arm,'original');run('qa',arm,'warm','original','settle','gate-v4-'+arm+'-settle')
        census('qa',arm,'original','repeat','original')
        call('edit','qa',arm,'notebook');census('qa',arm,'notebook','transition','edit')
        census('qa',arm,'notebook','repeat','edit-followup')
        call('edit','qa',arm,'original');census('qa',arm,'original','transition','restore')
        census('qa',arm,'original','repeat','final')
    else:
        call('edit','clean',arm,'notebook');census('clean',arm,'notebook','cold','cold-edit')
    print('Completed off-clock',mode,arm);sys.exit(0)
assert not roles
phases=('original','edit','edit-followup','restore','final','cold-edit');records={};digests={}; comparisons=[]
for arm in images:
    for phase in phases:
        name='gate-v4-'+arm+'-'+phase;p=reports/name/'result.json';rec=read(p);records[arm,phase]=rec;digests[name]=sha(p)
        assert rec['exit']==0 and rec['units']==619 and rec['behavior']['listed']==200
        status=101 if phase in ('edit','edit-followup','cold-edit') else 0
        assert {x['exit'] for x in rec['behavior']['tests'].values()}=={status}
        assert set(rec['counts'])<={'cargo','gcc','collect2','stock-wild','rustc-full','rustc-link-only','rustc-query'}
        if phase=='cold-edit':assert rec['fresh']==0
        assert rec['behavior']['sha256']!=records[arm,'original']['behavior']['sha256'] if phase in ('edit','edit-followup','cold-edit') else True

def compare(a,b):
    aa,bb=records[a],records[b];pairs=[]
    common=sorted(set(aa['products'])&set(bb['products']));assert len(common)>=50
    for key in common:
        x,y=aa['products'][key],bb['products'][key];assert x['size']==y['size'] and x['fields']['normalized']==y['fields']['normalized'],(a,b,key,x,y)
        if x['sha256']!=y['sha256']:pairs.append({'file':Path(key).name,'a_sha256':x['sha256'],'b_sha256':y['sha256'],'a_build_id':x['fields']['build_id'],'b_build_id':y['fields']['build_id'],'a_rodata_entsize':x['fields']['rodata_entsize'],'b_rodata_entsize':y['fields']['rodata_entsize']})
    assert aa['source_sha256']==bb['source_sha256'] and aa['behavior']['listing_sha256']==bb['behavior']['listing_sha256']
    comparisons.append({'a':a,'b':b,'compared':len(common),'byte_identical':len(common)-len(pairs),'differing_known_fields':pairs})
for mode in phases:
    compare(('A',mode),('B',mode))
    if mode!='cold-edit':assert records['A',mode]['compiler_args']==records['B',mode]['compiler_args'],mode
assert records['A','original']['native_args']==records['B','original']['native_args'], 'persistent original native arguments or live ephemeral bytes differ'
for a in images:
    assert records[a,'edit']['behavior']['sha256']==records[a,'cold-edit']['behavior']['sha256'],(a,'edited complete e2e differs from clean')
    assert records[a,'edit-followup']['behavior']['sha256']==records[a,'cold-edit']['behavior']['sha256'],(a,'edited repeat differs from clean')
    assert records[a,'restore']['behavior']['sha256']==records[a,'original']['behavior']['sha256'],(a,'restored complete e2e differs from original')
    for phase,ref in [('edit','cold-edit'),('edit-followup','cold-edit'),('final','original'),('restore','original')]:compare((a,phase),(a,ref))
plan_sha='467090560adc9c413466e40f2b80770ab781245f0fa8af3ad7839a94829b10a6';seal={'eligible':True,'images':images,'binding_sha256':{a:sha(study/'images'/(a+'-build.json')) for a in images},'plan_sha256':plan_sha,'worker_sha256':sha(worker),'lane_sha256':sha(lane),'receipts':digests,'comparisons':comparisons}
dump(reports/'functional-admission-v4.json',seal);print('Primary edit and clean admission passed',len(digests),len(comparisons),sum(len(x['differing_known_fields']) for x in comparisons))
