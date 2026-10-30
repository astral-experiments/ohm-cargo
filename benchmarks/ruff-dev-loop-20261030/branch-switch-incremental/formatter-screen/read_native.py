"""Independently validate and analyze the six registered historical formatter installations."""
import argparse,ast,collections,hashlib,json,re,subprocess,tarfile
from pathlib import Path
def sha(stream):
 return hashlib.file_digest(stream,'sha256').hexdigest()
def h(path):
 with path.open('rb') as f:return sha(f)
def get(p):return json.loads(p.read_bytes())
def digest_table(d):return hashlib.sha256(json.dumps(d,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def decode_quoted(s,i):
 while s[i]==' ':i+=1
 assert s[i]=='"';end=i+1
 while s[end]!='"':end+=2 if s[end]=='\\' else 1
 return ast.literal_eval(s[i:end+1]),end+1
def argv_of(line):
 if line.startswith('execveat('):
  pos=line.index(',')+1
 elif line.startswith('execve('):
  pos=line.index('(')+1
 else:return
 path,pos=decode_quoted(line,pos);pos=line.index('[',pos)+1;args=[]
 while True:
  while line[pos] in ' ,':pos+=1
  if line[pos]==']':break
  arg,pos=decode_quoted(line,pos);args.append(arg)
 return path,args
def traces(p):
 ex=collections.Counter();links=collections.Counter();objs=set();probes=0;nprobes=0;real={};members={};reader=subprocess.Popen(['zstd','-qdc',p/'trace.tar.zst'],stdout=subprocess.PIPE)
 with tarfile.open(fileobj=reader.stdout,mode='r|') as tf:
  for t in tf:
   if t.isdir():continue
   assert t.isfile() and t.name.startswith('./exec.');name=t.name[2:];assert name not in members;data=tf.extractfile(t).read();members[name]=hashlib.sha256(data).hexdigest();pending=None
   for line0 in data.decode().splitlines():
    if not line0[:1].isdigit():continue
    stamp,line=line0.split(' ',1)
    if '<unfinished ...>' in line:
     assert pending is None;pending=line.replace('<unfinished ...>','');continue
    if line.startswith('<... ') and ' resumed>' in line:
     assert pending is not None;line=pending+line.split(' resumed>',1)[1];pending=None
    if (line.startswith('openat(') or line.startswith('creat(')) and 'O_CREAT' in line and ('O_WRONLY' in line or 'O_RDWR' in line) and re.search(r'= \d+$',line.rstrip()):
     objs.update(q for q in re.findall(r'"([^"]+\.rcgu\.o)"',line))
    if not line.rstrip().endswith('= 0'):continue
    rec=argv_of(line)
    if rec is None:continue
    image,args=rec;nm=Path(image).name
    if image.endswith('/rustup/toolchains/ohm/bin/rustc'):
     if '--crate-name' not in args:probes+=1;continue
     crate=args[args.index('--crate-name')+1]
     if crate=='___' and any(k=='--print' or k.startswith('--print=') for k in args):nprobes+=1;continue
     flags=[s[2:] for s in args if s.startswith('-Z') and s!='-Z']+[args[ix+1] for ix,g in enumerate(args[:-1]) if g=='-Z'];cached=any(s.split('=')[0]=='link-only' and s not in ['link-only=no','link-only=false','link-only=off'] for s in flags);ex[('cached' if cached else 'full',crate)]+=1
    if 'wild-ld/' in image and nm in ('ld.bfd','ld','wild'):links['wild']+=1
    if nm=='collect2':links['collect2']+=1
    if nm in ('cc','gcc') or re.match(r'.*-gcc(?:-\d+)?$',nm):links['cc_or_gcc']+=1
   assert pending is None,t.name
 reader.stdout.close();assert reader.wait()==0 and members==dict(get(p/'trace-hashes.json'));assert h(p/'trace.tar.zst')==get(p/'result.json')['trace_archive']
 return {'full':{n:c for (q,n),c in ex.items() if q=='full'},'cached':{n:c for (q,n),c in ex.items() if q=='cached'},'tools':dict(links),'object_writes':len(objs),'raw_threads':len(members),'target_probes':nprobes,'version_probes':probes}
def inventory_key(x):
 pk=x['package_id'];kind,tail=pk.split('#',1);pkg=(Path(kind).name+'@'+tail if kind.startswith('path+') and '@' not in tail else tail);return [pkg,x['target']['name'],x['target']['kind'],x['profile']['test'],x['features']]
def main(root):
 r=Path(root);ops=r/'ops';assert h(ops/'SHA256SUMS')=='6c7029547d0a70724df5769d3e03dd5d37f40817566afd5ee581ebf1d8ec5e1b'
 for line in (ops/'SHA256SUMS').read_text().splitlines():
  s,n=line.split('  ');assert h(ops/n)==s
 assert get(r/'terminal.json')['exit']==0;allterm=get(r/'complete.json')['terminals'];order=['admit-P','admit-Q','pair1-P','pair1-Q','pair2-Q','pair2-P'];assert set(allterm)==set(order);proof={};native={};visits={};elves={}
 expected_tests=['tests::basic','tests::string_processing','comments::tests::parenthesized_expression']
 for slot in order:
  stage0=r/'runs'/slot;record=get(stage0/'complete.json');assert h(stage0/'complete.json')==allterm[slot] and get(stage0/'terminal.json')['exit']==0;identity=get(stage0/'identity.json');assert identity['empty'] and identity['cpu']==[28,29,30,31] and identity['crates']==505 and identity['index']==465;arm=slot[-1];admit=slot.startswith('admit');rr={}
  for tag,reg in record['rows'].items():
   p=stage0/tag;curr=get(p/'result.json');assert all(reg[k]==v for k,v in curr.items());proc=get(p/'cargo.process.json');assert proc['before']['private']>650*1024**2 and proc['after']['private']>650*1024**2;msgs=[json.loads(li) for li in (p/'cargo.stdout').read_bytes().splitlines()];assert h(p/'cargo.stdout')==proc['stdout'] and h(p/'cargo.stderr')==proc['stderr'] and msgs[-1]=={'reason':'build-finished','success':tag!='invalid-A'};tracked={'terminal':h(p/'result.json'),'cargo_stdout':proc['stdout'],'cargo_stderr':proc['stderr'],'real_elapsed_ns':proc['elapsed_ns'],'real_user_s':proc['user_s'],'real_sys_s':proc['sys_s'],'rev':curr['rev']}
   if tag=='invalid-A':
    assert proc['exit']==101 and curr['diagnostics'] and curr['diagnostics'][0][0]=='E0308';tracked['diagnostics']=curr['diagnostics'];rr[tag]=tracked;continue
   assert proc['exit']==0;typed=[x for x in msgs if x['reason']=='compiler-artifact'];assert len(typed)==curr['typed'];iv=sorted((inventory_key(x) for x in typed),key=repr);dirty=sorted((inventory_key(x) for x in typed if not x['fresh']),key=repr);assert sum(1 for x in typed if not x['fresh'])==len(curr['dirty'])
   listed=(p/'list.stdout').read_text().splitlines();names=[x[:-6] for x in listed if x.endswith(': test')];assert len(set(names))==len(names)==curr['tests'] and h(p/'list.stdout')==curr['inventory'] and set(expected_tests)<=set(names)
   for i,n in enumerate(expected_tests):
    o=(p/('test-'+str(i)+'.stdout')).read_text();assert n in o and '1 passed; 0 failed;' in o
   if curr['whole_runtime']:
    out=(p/'all-tests.stdout').read_text();f=re.search(r'test result: ok\. (\d+) passed; 0 failed; (\d+) ignored;',out);assert f and int(f[1])+int(f[2])==len(names)
   expected=64 if curr['rev'].startswith('b5dba861') else 56;assert expected==curr['expr_bytes']
   for size in (64,56):
    z=get(p/f'size-{size}.process.json');assert z['exit']==(0 if size==expected else 1)
    if size!=expected:assert any(x.get('code') and x['code']['code']=='E0308' for x in (json.loads(z) for z in (p/f'size-{size}.stderr').read_bytes().splitlines()))
   hs=curr['elf'];assert re.fullmatch(r'[0-9a-f]{64}',hs)
   if hs not in elves:
    e=r/'elf'/(hs+'.zst');un=subprocess.Popen(['zstd','-dcq',e],stdout=subprocess.PIPE);d=hashlib.sha256();size=0
    with un.stdout as st:
     magic=st.read(4);assert magic==b'\x7fELF';d.update(magic);size=4
     while b:=st.read(2**20):d.update(b);size+=len(b)
    assert un.wait()==0 and d.hexdigest()==hs and curr['elf_bytes']==size;elves[hs]=[size,h(e)]
   tracked.update(elf=hs,typed_count=len(typed),roster=digest_table(iv),dirty=dirty,test_count=len(names),inventory=curr['inventory'],full_clean_test=curr['whole_runtime'],expr=expected)
   if curr['actual_wild'] is not None:
    acts=traces(p);assert (acts['full'],acts['cached'],acts['tools'].get('wild',0),acts['object_writes'])==(curr['actual_compile'],curr['actual_cached'],curr['actual_wild'],curr['actual_cgus']),(slot,tag,acts,curr['actual_cgus']);native[(arm,'A' if 'return-A' in tag else 'B')]=acts;tracked['native']=acts
   rr[tag]=tracked
  proof[slot]={'completion':allterm[slot],'driver':identity['driver'],'cargo':identity['cargo'],'wild':identity['wild'],'rows':rr}
 for arm in 'PQ':
  for v in 'AB':
   t=proof['admit-'+arm]['rows'];trace=t['return-'+v+'-native'];
   for pair in [1,2]:
    x=proof[f'pair{pair}-{arm}']['rows'];y=x['return-'+v];ref=x['empty-A'] if v=='A' else t['empty-B'];assert (y['roster'],y['inventory'],y['expr'],y['dirty'])==(trace['roster'],trace['inventory'],trace['expr'],trace['dirty']);assert y['roster']==ref['roster'] and y['inventory']==ref['inventory'];y['matches_clean_elf']=y['elf']==ref['elf']
 for v in 'AB':
  cmp=[]
  for pair in [1,2]:
   a,b=[proof[f'pair{pair}-{arm}']['rows']['return-'+v] for arm in 'PQ'];assert (a['inventory'],a['roster'],a['dirty'])==(b['inventory'],b['roster'],b['dirty']);cmp.append({'whole_cpu_ratio_P_over_Q':(a['real_user_s']+a['real_sys_s'])/(b['real_user_s']+b['real_sys_s']),'wall_ratio_P_over_Q':a['real_elapsed_ns']/b['real_elapsed_ns'],'paired_elf_equal':a['elf']==b['elf'],'P_clean':a['matches_clean_elf'],'Q_clean':b['matches_clean_elf']})
  visits[v]={'pairs':cmp,'numerical_gate':all(min(m['whole_cpu_ratio_P_over_Q'],m['wall_ratio_P_over_Q'])>=1.8 for m in cmp),'all_elf_equal':all(m['paired_elf_equal'] and m['P_clean'] and m['Q_clean'] for m in cmp)}
 return {'schema':1,'protocol':h(ops/'SHA256SUMS'),'scope':'historical Ruff #28335, formatter library test build (not test execution)','run_order':order,'visits':visits,'installs':proof,'elf_cas':elves}
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('raw_root',type=Path);parser.add_argument('--output',type=Path);args=parser.parse_args();result=json.dumps(main(args.raw_root),sort_keys=True,indent=2)+'\n'
 if args.output:args.output.write_text(result)
 else:print(result,end='')
