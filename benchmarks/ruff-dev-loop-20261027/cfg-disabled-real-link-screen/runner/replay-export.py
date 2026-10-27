"""Export registered real time rows and public-safe per-phase evidence after both endpoint schedules end."""
from pathlib import Path
import csv,hashlib,json,os,shutil
P=Path('/mnt/devbox-scratch/dev-user/ohm-empty-test-h4-20261027');root=P/'results/a11-screen-v1';out=P/'results/a11-safe-final'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
load=lambda p:json.loads(p.read_bytes())
def dump(n,x):(out/n).write_text(json.dumps(x,indent=2,sort_keys=True)+'\n')
def main():
 c=load(root/'complete.json');assert c['commands_timed']==64 and sha(root/'dirty.csv')==c['dirty_csv'] and sha(root/'fresh.csv')==c['fresh_csv']
 out.mkdir();plan=load(P/'transfer/A11-screen-plan.json');ds={}
 for ed in plan['endpoint_order']:
  ds[ed]={}
  for arm in ('A','C'):
   commands={}
   for d in sorted((root/ed/arm).iterdir()):
    if not d.is_dir():continue
    v=load(d/'verified.json');inv=load(d/'invocation.json')
    assert v['units']==619 and v['executables']==102 and v['elf_count']==110
    keep={k:v[k] for k in ('roster','messages','dirty','units','executables','elf_count','listing','cli','caller','elfs') if k in v}
    keep.update(inv)
    if 'phase_trace' in v:
     tr=v['phase_trace'];keep['successful_processes']={k:tr[k] for k in ('rustc','native_links','cc_with_output','collect2_with_output','native_probes','total_execs')}
    commands[d.name]=keep
   ds[ed][arm]=commands
 for k in ('dirty','fresh'):
  rows=list(csv.DictReader((root/(k+'.csv')).open()));assert len(rows)==32
  for row in rows:
   ed,arm,i=row['endpoint'],row['arm'],int(row['pair']);v=ds[ed][arm][k+f'-pair-{i:02}'];assert v['elapsed_ns']==int(row['elapsed_ns']) and not v['traced'] and v['exit']==0
   schedule=plan['schedule'][ed][i-1];assert schedule['order'][int(row['slot'])-1]==arm and row['direction']==schedule['direction']
  shutil.copy2(root/(k+'.csv'),out/(k+'.csv'))
 for n in ('complete.json','host-before.json','host-after.json'):shutil.copy2(root/n,out/n)
 shutil.copy2(root/'expected.json',out/'preflight-allowed.json')
 for n in ('A11-screen-grant','A11-screen-resume'):shutil.copy2(P/'results'/n,out/(n+'.json'))
 dump('commands.json',ds)
 gates={}
 for f in sorted((P/'results/a11-screen-independent-stock').glob('*/certificate.json')):
  obj=load(f);obs={}
  for digest,ref in obj['stock_full'].items():
   o=load(P/'results'/ref);assert o['elf']['raw']==digest;obs[digest]=o
  gates[f.parent.name]={'certificate':obj,'physical_stock_full_commands':obs}
 dump('supplemental-stock.json',gates)
 dump('preflights.json',{ed:{arm:load(P/'results'/ed/n/'complete.json')['seed']['roster'] for arm,n in [('A','Stock11'),('C','A11')]} for ed in plan['endpoint_order']})
 print(len(gates),'supplemental same-source stock ELF witnesses')
if __name__=='__main__':main()
