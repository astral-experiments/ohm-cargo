"""Native engineering screen on three real contents, one independent process per observation."""
from pathlib import Path
import hashlib,json,os,platform,shutil,statistics,struct,subprocess,sys,tarfile
D=Path(__file__).resolve().parent;H=Path.home();O=H/'.cache/ohm-ruff-18-fresh-prep-linkscout-20261028';plan=json.loads((D/'leaf-cost-plan.json').read_text())
def sha(b):return hashlib.sha256(b).hexdigest()
assert sha((D/'blake3.crate').read_bytes())==plan['BLAKE3_1_8_5_crate_sha256'] and sha((D/'leaf-cost.c').read_bytes())==plan['source_sha256']
with tarfile.open(D/'blake3.crate')as t:t.extractall(D/'src',filter='data')
C=D/'src/blake3-1.8.5/c';exe=D/'compare'
cflags=['-O3','-DNDEBUG','-std=gnu17','-fno-lto','-I'+str(C)];src=[D/'leaf-cost.c',*[C/(n+'.c')for n in ['blake3','blake3_dispatch','blake3_portable']],*[C/('blake3_'+n+'_x86-64_unix.S')for n in ('sse2','sse41','avx2','avx512')]]
subprocess.run(['cc',*cflags,*src,'-o',exe],check=True)
roster=O/'target/debug/build/workspaces/5183fbb458952a35/v2-63fe60e05f649687';d=roster/'ruff_unicode_names2/f17900a6a44d7d41/out';z=roster/'ty_vendored/55bc40c417024a68/out/zipped_typeshed.zip'
files=[d/'generated.rs',d/'generated_phf.rs',z]; metadata={p.name:{'sha256':sha(p.read_bytes()),'bytes':p.stat().st_size}for p in files}; total=sum(v['bytes']for v in metadata.values());assert total==7918933 and metadata[z.name]['sha256']=='198913903bc7a97bf02a697768ab78ed3675b645a0f9ecaf78bd1cd9ca7800de'
old=z.read_bytes();a=bytearray(old);eocd=old.rfind(b'PK\x05\x06');cd=struct.unpack_from('<I',old,eocd+16)[0];offset=struct.unpack_from('<I',old,cd+42)[0]
for p in [cd+12,offset+10]:a[p]^=1
changed=D/'changed.zip';changed.write_bytes(a);assert sha(a)=='9981488fd5597c72340f4546aa08b91a8d0bcd891a78267a81e72c7220987bb3'
plan_sha=sha((D/'leaf-cost-plan.json').read_bytes());avail=int(next(s for s in Path('/proc/meminfo').read_text().splitlines()if s.startswith('MemAvailable:')).split()[1])*1024;load=os.getloadavg()
assert load[0]<2 and avail>=10*2**30, (load,avail)
data={'plan_sha256':plan_sha,'implementation':'C reference from exact cargo-locked blake3 1.8.5, runtime-dispatched x86 assembly','cc':subprocess.check_output(['cc','--version'],text=True).splitlines()[0],'model_elf':sha(exe.read_bytes()),'start_load':load,'memory_available':avail,'cpu':28,'processor':next(l.split(':',1)[1].strip()for l in Path('/proc/cpuinfo').read_text().splitlines()if l.startswith('model name')),'overlap':metadata,'controls':[],'slots':[]}
def run(arm,first,second):
 q=json.loads(subprocess.check_output(['taskset','-c','28',exe,arm,files[0],files[1],first,second]));assert q['read_bytes']==total*2 and q['peak_saved_bytes']==(z.stat().st_size if arm=='copy'else 0);return q
for label,first,second in [('original',z,z),('different',z,changed),('reverse',changed,z),('changed',changed,changed)]:
 a=run('raw',first,second);b=run('copy',first,second);assert a['raw_blake3']==b['raw_blake3'] and b['copy_misses']==(first!=second)
 if second==z: assert b['raw_blake3'][-1]=='468e82dc48f65a681b6018342015024b2f5964a11b2f5166e04edc70874a906d'
 data['controls'].append({'label':label,'raw_blake3':b['raw_blake3'],'changed_copy_paths':b['copy_misses'],'bytes':a['read_bytes'],'tree_same_across_different_format':a['model_tree']==b['model_tree']})
for i,order in enumerate(plan['orders']):
 for slot,arm in enumerate(order.split('-')):
  row=run(arm,z,z);assert row['raw_blake3']==data['controls'][0]['raw_blake3'] and row['copy_misses']==0
  data['slots'].append({'block':i,'slot':slot,'arm':arm,**row})
data['ending_inputs']={p.name:sha(p.read_bytes())for p in files};assert all(data['ending_inputs'][k]==v['sha256']for k,v in metadata.items())
data['median_ns']={arm:statistics.median(x['ns']for x in data['slots']if x['arm']==arm)for arm in ['raw','copy']}
deltas=[next(r for r in data['slots']if r['block']==i and r['arm']=='copy')['ns']-next(r for r in data['slots']if r['block']==i and r['arm']=='raw')['ns']for i in range(24)]
data['median_paired_delta_ns']=statistics.median(deltas);data['copy_favorable']=sum(x<0 for x in deltas);data['median_minor_faults']={arm:statistics.median(x['minflt']for x in data['slots'] if x['arm']==arm)for arm in ['raw','copy']};data['terminal']=True
(D/'results.json').write_text(json.dumps(data,sort_keys=True,indent=2)+'\n')
print(json.dumps({k:data[k]for k in ('median_ns','median_paired_delta_ns','copy_favorable','median_minor_faults','processor','start_load','terminal')}))
