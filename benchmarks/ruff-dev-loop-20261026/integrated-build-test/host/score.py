from pathlib import Path
import collections,csv,hashlib,itertools,json,math,os,re,statistics,subprocess as sp,sys
R=Path(__file__).resolve().parent;spec=json.loads((R/'plan.json').read_text());safe=(24*(1<<30));S=Path('/mnt/devbox-scratch/dev-user');lib='librustc_driver-774a793a844d5500.so';roles=['cargo','rustc','clang','wild'];mode=sys.argv[1];assert mode in ('build','test');D=R/mode; st=S/'ohm-ruff-loop-20261026/wild-full'/('prebuilt-'+mode);unit='ruff' if mode=='build' else 'fixtures';nelf=6 if mode=='build' else 102;ntarget=501 if mode=='build' else 619

def saved(p):return json.loads(p.read_text())
def write(p,obj):p.write_text(json.dumps(obj,sort_keys=True,indent=2)+'\n')
def digest(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def check_observation(d,arm):
 j=saved(d/'result.json');start=saved(d/'start.json'); assert j['returncode']==0 and j['idx_stable'] and j['source_unchanged'] and j['actual']==[unit],(d,j['actual']); assert j['inv_equal'] and j['inventory']==start['inventory'],(d,'cache changed'); reg='.ohm-registry-json-v'+('1' if arm=='parent' else '2'); assert len(j['inventory'][reg])>=300
 if arm=='candidate':assert len(j['inventory']['.ohm-git-index-sha1dc-v1'])==1 and j['inventory']['.ohm-git-index-sha1dc-v1'][0][1]==32
 else:assert '.ohm-git-index-sha1dc-v1' not in j['inventory']
 assert j['all_elf_equal'] and len(j['elf_hashes'])==nelf and (d/'stdout').stat().st_size==0
 err=(d/'stderr').read_text(); assert re.search(r'\bCompiling '+('ruff|ruff_python_formatter' if mode=='build' else r'ruff_python_formatter')+r'\b',err) and re.search(r'Finished `(?:dev|test)` profile',err),d
 if mode=='test':
  # Cargo prints test targets here; JSON also identifies executable support binaries.
  roster=lambda text:sorted(re.findall(r'^\s*Executable\s+(.+)$',text,re.M))
  terminal=roster(err);native=roster((D/'native-roster-parent/stderr').read_text());assert len(terminal)>0 and terminal==native,d
 return j

def census(d):
 pending={};found=[]
 for line in (d/'execve').read_text().splitlines():
  m=re.match(r'^(\d+)\s+execve\(.*<unfinished \.\.\.>$',line)
  if m:assert m[1] not in pending;pending[m[1]]=line[:line.rindex('<unfinished ...>')].rstrip();continue
  m=re.match(r'^(\d+)\s+<\.\.\. execve resumed>(.*)$',line)
  if m:line=pending.pop(m[1])+m[2]
  m=re.match(r'^(\d+)\s+execve\("([^"]+)".*\)\s+=\s+0$',line)
  if m:found.append([int(m[1]),m[2]]);
  elif 'execveat(' in line:raise ValueError(line[:130])
 assert not pending
 expected=['/home/dev-user/.cargo/bin/cargo',str(st/'rustup/toolchains/ohm/bin/cargo'),str(st/'runtime/bin/cargo'),str(st/'compiler-wrapper'),str(st/'runtime/bin/rustc'),str(st/'clang'),'/usr/bin/clang',str(st/'wild-dispatch'),str(st/'ld.bfd')];assert collections.Counter(x[1] for x in found)==collections.Counter(expected),(d,found); assert len({x[0] for x in found})==4; write(d/'native-roster.json',found);return found

def counters(d,arm,preflight=False):
 j=check_observation(d,arm);a,=d.glob('cargo.*.ir');pid=a.name.split('.')[1];lines=[x.split() for x in a.read_text().splitlines()];assert lines[0]==['B',pid,'0','0'] and lines[-1]==['P',pid,'0','0'] and all(len(l)==4 and l[0] in 'BPTFS' and l[1]==pid for l in lines); assert sum(l[0]=='B' for l in lines)==sum(l[0]=='P' for l in lines)==1;T=sorted(l[2] for l in lines if l[0]=='T');F=sorted(l[2] for l in lines if l[0]=='F');assert T==F and len(set(T))==len(T)>0
 ca,=d.glob('cargo.*.argv');assert ca.name.split('.')[1]==pid and os.fsdecode(ca.read_bytes().split(b'\0')[0])==str(st/'runtime/bin/cargo'); assert 'cargo:'+pid in j['mapped'],(d,'cargo mapping',j['mapped']);items=[{'role':'cargo','engine':'DynamoRIO','ir':sum(int(l[3]) for l in lines if l[0]=='F'),'threads':len(T),'pid':int(pid),'image':str(st/'runtime/bin/cargo'),'sha256':spec['inputs'][arm]['cargo']['sha256'],'raw_sha256':digest(a)}]
 pathmap={str(st/'runtime/bin/rustc'):'rustc','/usr/bin/clang':'clang',str(Path('/usr/bin/clang').resolve()):'clang',str(st/'ld.bfd'):'wild'}
 for guest in sorted(d.glob('guest.*')):
  toolpid=guest.name.split('.')[1];logp=d/('vg.'+toolpid);log=logp.read_text();assert log.count(' I refs:')==1 and 'Process terminating' not in log; cmd,ir=None,None
  with guest.open() as f:
   for line in f:
    if line.startswith('cmd: '):cmd=line[5:].split()
    elif line.startswith('summary: '):ir=int(line.split()[1]);break
  role=pathmap[cmd[0]];assert ir>0 and int(re.search(r' I refs:\s*([\d,]+)',log)[1].replace(',',''))==ir
  item={'role':role,'engine':'Cachegrind','pid':int(toolpid),'image':cmd[0],'ir':ir,'raw_sha256':digest(guest),'log_sha256':digest(logp)}
  if role=='rustc':
   argv=d/('all-rustc.'+toolpid+'.argv');args=argv.read_bytes().split(b'\0');assert args[args.index(b'--crate-name')+1].decode()==cmd[cmd.index('--crate-name')+1]==unit;driver={l.split('Reading syms from ',1)[1].strip() for l in log.splitlines() if 'Reading syms from ' in l and l.rstrip().endswith('/'+lib)};assert driver=={str(st/'drivers/selected'/lib)},driver;assert 'driver:'+toolpid in j['mapped'],(d,j['mapped']);item.update(crate=unit,driver=sorted(driver)[0],driver_sha256=spec['inputs'][arm]['driver']['sha256'],argv_sha256=digest(argv))
  elif role=='clang':assert '-Wl,--no-fork' in cmd
  else:assert '--no-fork' in cmd or len(cmd)==2 and cmd[1].startswith('@');item['sha256']=spec['inputs'][arm]['wild']['sha256']
  items.append(item)
 assert len(items)==len({x['pid'] for x in items})==4 and sorted(x['role'] for x in items)==sorted(roles) and len(list(d.glob('vg.*')))==3;counts={x['role']:x['ir'] for x in items};write(d/'counter-roster.json',{'images':items,'counts':counts,'component_sum':sum(counts.values()),'distinction':'Cargo uses DynamoRIO guest instructions; rustc/clang/Wild use Cachegrind I refs. Launcher/dispatch shell work is outside the sum.'});return counts

def run(arm,variant,label,kind):
 p=sp.run([sys.executable,R/'bench.py',mode,arm,variant,label,kind]);assert p.returncode==0,(mode,arm,label);return D/label

def stats(rows):
 vals=[100*(1-z['candidate']['sum']/z['parent']['sum']) for z in rows];p=len(vals);assert p==12;lo=max(i for i in range(p//2+1) if sum(math.comb(p,j) for j in range(i))*2/2**p<=.05);signed=[(z['parent']['sum']-z['candidate']['sum'])*(1 if z['order'].startswith('parent') else -1) for z in rows];observed=abs(sum(z['parent']['sum']-z['candidate']['sum'] for z in rows));dist=[abs(2*sum(signed[i] for i in idx)-sum(signed)) for idx in itertools.combinations(range(12),6)];q=sum(v>=observed for v in dist)/len(dist);s=sorted(vals);return {'metric':'mixed-counter component sum','median_paired_reduction_pct':statistics.median(vals),'median_ci95_pct':[s[lo-1],s[p-lo]],'paired_range_pct':[s[0],s[-1]],'favorable':sum(v>0 for v in vals),'balanced_randomization_p':q,'order_count':len(dist),'per_component_median_ir_by_arm':{role:{arm:statistics.median(z[arm][role] for z in rows) for arm in ('parent','candidate')} for role in roles+['sum']}}
if sys.argv[2]=='preflight':
 for am in ('parent','candidate'):census(D/('native-roster-'+am));
 counters(D/'mixed-preflight-candidate','candidate');print('native 4-image rosters and current candidate mixed pass');
elif sys.argv[2]=='run':
 for am in ('parent','candidate'):census(D/('native-roster-'+am));
 counters(D/'mixed-preflight-candidate','candidate');log=D/'blocks.jsonl';assert not log.exists();rows=[]
 for block,assignment in enumerate(spec['schedule'][mode]):
  z={'block':block,'order':assignment}
  for pos,am in enumerate(assignment.split(',')):
   reset=run(am,'original',f'pair-{block:02}-{pos}-{am}-reset','plain');check_observation(reset,am)
   d=run(am,'edited',f'pair-{block:02}-{pos}-{am}','count');values=counters(d,am);z[am]={**values,'sum':sum(values.values())}
  with log.open('a') as f:f.write(json.dumps(z,sort_keys=True)+'\n');rows.append(z);print('complete',mode,block,flush=True)
 write(D/'statistics.json',stats(rows))
