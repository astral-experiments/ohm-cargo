from pathlib import Path
from collections import Counter,defaultdict
import ast,hashlib,json,os,re,subprocess,tarfile
quotes=r'"(?:[^"\\]|\\.)*"';exec_re=re.compile(r'execve\(('+quotes+r'),\s*(\[.*\]),\s*(?:0x[\da-f]+|NULL)');fork=re.compile(r'(?:clone3?|vfork|fork)\(.*\)\s+=\s+(\d+)$');ret_fd=re.compile(r'\s=\s\d+<(.+)>$');failed_open=re.compile(r'\s=\s-1 (ENOENT|ENOTDIR)\b');F=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027/frozen-toolchain');
def digest(p):
 with p.open('rb') as h:return hashlib.file_digest(h,'sha256').hexdigest()
def save(p,x):p.write_text(json.dumps(x,sort_keys=True,indent=1)+'\n')
def parse(d,phase):
 fns=sorted(d.glob('exec.*'));parents={};jobs={};raw=defaultdict(lambda:{'opens':set(),'missing':set(),'other_errors':Counter(),'unfinished':0});images=[];kindcounts=Counter();totals=Counter();unclassified=[];all_execs=0
 for path in fns:
  pid=int(path.name.rsplit('.',1)[1]);r=raw[pid];pending=None
  with path.open(errors='replace') as f:
   for ln in f:
    s=ln.strip()
    if s.endswith('<unfinished ...>'):pending=s.removesuffix('<unfinished ...>');continue
    if s.startswith('<... '):
     m=re.match(r'^<\.\.\. \w+ resumed>(.*)$',s)
     if m and pending is not None:s=pending+m[1];pending=None
     else:r['unfinished']+=1;continue
    if (fm:=fork.fullmatch(s)) and int(fm[1])>0:parents[int(fm[1])]=pid;continue
    if s.startswith(('open(','openat(','openat2(')):
     if (m:=ret_fd.search(s)):r['opens'].add(m[1]);continue
     if (m:=failed_open.search(s)):
      z=re.search(quotes,s);r['missing'].add((ast.literal_eval(z[0]) if z else '<unparsed>')+' ['+m[1]+']');continue
     if ' = -1 ' in s:r['other_errors'][s.split(' = -1 ',1)[1].split(' ',1)[0]]+=1
     continue
    if not s.startswith(('execve(','execveat(')) or not re.search(r'\)\s+= 0$',s):continue
    m=exec_re.match(s)
    if not m:unclassified.append({'pid':pid,'reason':'unparsed-exec','line_sha256':hashlib.sha256(s.encode()).hexdigest()});continue
    img=Path(ast.literal_eval(m[1]));args=[ast.literal_eval(q) for q in re.findall(quotes,m[2])];all_execs+=1;b=img.name;images.append((pid,str(img)));k=None;n=None
    if b=='rustc' and img.is_file() and img.samefile(F/'bin/rustc'):
     n=args[args.index('--crate-name')+1] if '--crate-name' in args else None
     if n is None or n in ('___','__','_') or '--print=file-names' in args:kindcounts['rustc-query']+=1;continue
     link=any(a=='-Zlink-only' or (i>0 and args[i-1]=='-Z' and a=='link-only') for i,a in enumerate(args));guard=[s for s in args if 'ohm-checked-mixed-rlink=' in s];k='rustc-guarded-unknown' if guard else 'rustc-link-only' if link else 'rustc-full'
    elif b=='ld.bfd' and img.parent.name=='wild-ld' or b in ('wild','wild-linker'):k='wild'
    elif b=='collect2':k='collect2'
    elif b in ('cc','gcc','clang','clang++','c++','g++') or re.fullmatch(r'[a-z0-9_]+-linux-gnu-(?:gcc|g\+\+)(?:-\d+)?',b):k='cc'
    elif b in ('ld','rust-lld','ld.lld','ld.bfd','ld.gold'):k='other-linker'
    if k:
     if pid in jobs:unclassified.append({'pid':pid,'reason':'same-pid-multiple-typed-execs','before':jobs[pid]['kind'],'after':k})
     jobs[pid]={'pid':pid,'img':str(img),'kind':k,'crate':n,'argv':args,'link_output':args[args.index('-o')+1] if '-o' in args else None,'test':'--test' in args,'exec_sha256':hashlib.sha256(s.encode()).hexdigest()};kindcounts[k]+=1;totals[k]+=1
  if pending is not None:r['unfinished']+=1
 own=defaultdict(lambda:{'opens':set(),'missing':set(),'other_errors':Counter(),'unfinished':0});
 for pid,r in raw.items():
  orig=pid;visited=set()
  while pid not in jobs and pid in parents and pid not in visited:visited.add(pid);pid=parents[pid]
  if pid not in jobs:continue
  o=own[pid];o['opens'].update(r['opens']);o['missing'].update(r['missing']);o['other_errors'].update(r['other_errors']);o['unfinished']+=r['unfinished']
 for pid,r in jobs.items():
  o=own[pid];r['opens']=sorted(o['opens']);r['missing']=sorted(o['missing']);r['other_open_errors']=dict(o['other_errors']);r['unfinished']=o['unfinished'];p=parents.get(pid);r['parent_job']=None
  while p is not None:
   if p in jobs:r['parent_job']=p;break
   p=parents.get(p)
  r['image_sha256']=digest(Path(r['img']))
  args=r['argv'];r['externs']=[s.split('=',1)[1] for i,s in enumerate(args) if i and args[i-1]=='--extern' and '=' in s];r['file_fts']=len(fns)
 save(d/'processes.json',{'typed':list(jobs.values()),'exec-images':images,'unclassified':unclassified,'typed_invocations':dict(kindcounts),'process_trace_files':len(fns),'open_capture':phase in ('edit','restore'),'total_successful_execs':all_execs});save(d/'process-totals.json',dict(totals));expect_fast=any(i.name=='cargo' for _,v in images for i in (Path(v),));assert expect_fast,'missing actual Cargo exec'
 # Compression is only of our disposable trace files; the tokenized evidence and original raw data both survive.
 rawlist=d/'trace-members';rawlist.write_bytes(b'\0'.join(f.name.encode() for f in fns)+b'\0');dest=d/'exec-traces.tar.zst'
 subprocess.run(['tar','--null','-I','zstd -q -T2 -1','-cf',str(dest),'-T',str(rawlist)],cwd=d,check=True);subprocess.run(['zstd','-q','-t',str(dest)],check=True)
 for f in fns:f.unlink()
