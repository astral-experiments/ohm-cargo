"""Verify the zero-clock failure and the four independently decoded debug pairs."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

root=Path(__file__).resolve().parent
if (root/'SHA256SUMS').exists():
    subprocess.run(['sha256sum','--quiet','-c','SHA256SUMS'],cwd=root,check=True)
sys.path.insert(0,str(root))
import namespace_paths as names
assert names.selftest()
read=lambda n:json.loads((root/n).read_bytes())
sha=lambda raw:hashlib.sha256(raw).hexdigest()
original=read('original-terminal.json')
assert original['exit']=='1' and not original['complete'] and original['pairs']=={'package':0,'workspace':0}
inspection=read('native-elf-diagnostic.json')
assert inspection['prior_exit']==1 and inspection['prior_clock_files']==inspection['prior_ledger_files']==0
assert inspection['prior_grant']=='9291ff85cd3af9bd65111b1688955c86cffae83ee260031869937bddc28a15a7'
assert inspection['helper_sha256']==sha((root/'namespace_paths.py').read_bytes())
assert inspection['prior_failure']==original['failure'] and inspection['prior_stderr']==original['stderr']
native=inspection['native']; package=native['package']; workspace=native['workspace']
assert (package['units'],package['files'],package['runnable'],package['exact'])==(303,4,1,4) and not package['differences']
assert (workspace['units'],workspace['files'],workspace['runnable'],workspace['exact'])==(619,110,102,106)
assert len(workspace['differences'])==4
dwarf=read('dwarf-decode.json')
assert len(dwarf['readelf'])==64 and dwarf['pairs'].keys()==workspace['differences'].keys()
filemap={}
for n,v in workspace['differences'].items():
    a,b=v['raw']
    assert a!=b and not v['strict_elf_pass']
    d=v['difference']
    assert len(set(d['sizes']))==1
    assert set(d['differing_bytes_by_section'])=={'.debug_info','.debug_macro','.debug_str','.note.gnu.build-id'}
    assert all(len(p)==1 and p[0][1]=='.debug_str' for p in d['namespace_occurrences'])
    l,r=dwarf['pairs'][n]
    assert l['debug_strings']==r['debug_strings'] and l['debug_strings']['namespace_occurrences']==1
    for section in ('info','macro'):
        x,y=l[section],r[section]
        assert (x['lines'],x['str_offsets'],x['namespaces'])==(y['lines'],y['str_offsets'],y['namespaces'])
        assert not x['stderr_len'] and not y['stderr_len'] and x['decoded']==y['decoded']
        assert x['lines']>10000 and (section!='info' or x['str_offsets']>10000)
    filemap[n]=[a,b]
print(json.dumps({'native_pairs':{'package':{},'workspace':filemap},'original_commands':0,'debugger':'readelf','qualified_debug_pairs':4},sort_keys=True))
