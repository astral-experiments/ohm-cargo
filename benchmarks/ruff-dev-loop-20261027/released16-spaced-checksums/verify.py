from pathlib import Path
import gzip,hashlib,io,json,sys,tarfile
root=Path(__file__).resolve().parent
def sha(data):return hashlib.sha256(data).hexdigest()
if (root/'SHA256SUMS').exists():
 for row in (root/'SHA256SUMS').read_text().splitlines():
  digest,name=row.split('  ',1); assert sha((root/name).read_bytes())==digest,name
with tarfile.open(root/'native.tgz','r:gz') as t:
 def raw(path):return t.extractfile(path).read()
 def obj(path):return json.loads(raw(path))
 direct=obj('packaged-decoy/receipt.json')
 assert direct['stdout']=='17\n' and direct['matches_decoy'] and not direct['matches_actual']
 assert direct['decoy'] in direct['reported'] and direct['actual']!=direct['decoy']
 result=obj('cargo-decoy-v3/result.json')
 cases={'decoy':([17,17,17,17,29],[0,1,1,1,0],[False,False,False,True,False]),'no-decoy':([17,17,17,29,29],[0]*5,[False]*5),'ordinary':([17,17,17,29,29],[0,1,1,1,0],[False,False,True,False,False])}
 for mode,(values,states,freshes) in cases.items():
  rows=result[mode];labels=['first','train','unchanged','swapped','independent']
  for (label,value,status,fresh) in zip(labels,values,states,freshes):
   row=rows[label];d=f'cargo-decoy-v3/{mode}/{label}'
   assert row==obj(d+'/row.json') and row['exit']==0 and row['units']==4
   assert row['value']==value and row['native'].strip().endswith('escape-value='+str(value))
   assert row['fresh']==fresh and row['status']==status
   deps=raw(d+'/rustc.d')
   assert sha(deps)==row['depinfo_sha'] and b'ohm-foreign-span-bytes' in deps
   assert all(x.encode() in deps for x in row['checksum_line'])
   assert raw(d+'/encoded')[-41:-37]==b'OBS1' and raw(d+'/encoded')[-33]==status
   stdout=raw(d+'/stdout.jsonl');assert sha(stdout)==row['raw_stdout_sha']
   events=[json.loads(x) for x in stdout.splitlines()];a,=[x for x in events if x.get('reason')=='compiler-artifact' and x['target']['name']=='hold_direct']
   assert a['fresh']==fresh and events[-1]=={'reason':'build-finished','success':True}
  assert rows['unchanged']['external_sha256']!=rows['swapped']['external_sha256']==rows['independent']['external_sha256']
  if mode=='decoy':
   assert rows['first']['shadow_sha256']==rows['swapped']['external_sha256'] and rows['swapped']['all_fresh']
   assert rows['swapped']['elf']==rows['unchanged']['elf']!=rows['independent']['elf']
 fifo=json.loads((root/'fifo.json').read_text())
 assert fifo['returncode_before_timeout'] is None and fifo['no_writer_opened'] and any('wait_for_partner' in x['wchan'] for x in fifo['kernel'].values())
 print('Verified 15 ordinary Cargo builds, 15 native programs, compiler checksum mismatch and one bounded writer-free blocked rustc.')
