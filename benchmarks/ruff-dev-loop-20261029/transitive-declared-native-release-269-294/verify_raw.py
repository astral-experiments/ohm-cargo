"""Reopen raw per-pid syscalls, Cargo output and archived native executables."""
from pathlib import Path
from collections import Counter,defaultdict
import argparse,ast,gzip,hashlib,json,os,re,subprocess
import sys
stages={'original':17,'insert':29,'overwrite':41,'malformed':None,'remove':17,'repair':73,'restore':17}
roles=['ordinary','repeat','force','clean'];bins=['first_probe','second_probe'];lib='libohm_269_transitive.a'
def sha(x):return hashlib.sha256(x).hexdigest()
def read(p):return json.loads(p.read_bytes())
def grade(path):
 ev=path/'evidence';root=read(ev/'result.json');kit=read(path/'kit.json');expected=112 if len(root['cases'])==4 else 56
 assert root['physical_cases']==expected and (path/'exit').read_text().strip()=='0'
 assert root['pins']==kit and len(root['sources']['declared'])==len(root['sources']['undeclared']) and [k for k in root['sources']['declared'] if root['sources']['declared'][k]!=root['sources']['undeclared'][k]]==['provider/build.rs']
 hashes={};checked=[];body={};global_counts=Counter();inputs={};native_images={};rfiles=[]
 for kind in root['cases']:
  modes={};body[kind]=modes;want_wild=kind.endswith('-default');declared=kind.startswith('declared-')
  for stage,known in stages.items():
   base=ev/kind/stage;inp=read(base/'inputs.json');inputs.setdefault(stage,(inp['early'],inp['late']));assert (inp['early'],inp['late'])==inputs[stage];rows=modes[stage]={}
   assert (inp['early'] is None)==(stage in ('original','remove','restore'))
   for role in roles:
    p=base/role;r=read(p/'result.json');trace=r['trace'];typed=(p/'cargo.stdout').read_bytes();err=(p/'cargo.stderr').read_bytes();assert sha(typed)==r['stdout'] and sha(err)==r['stderr']
    fs=(p/'exec-open.json.gz').read_bytes();assert sha(fs)==trace['raw_sha256'];full=json.loads(gzip.decompress(fs));assert len(full)==trace['trace_files']
    doc=list(map(json.loads,typed.splitlines()));assert doc[-1]=={'reason':'build-finished','success':r['exit']==0};known_diagnostics=[m['message']['message'] for m in doc if m['reason']=='compiler-message' and m['message']['level']=='error'];assert known_diagnostics==r['diagnostics']
    arts=[m for m in doc if m['reason']=='compiler-artifact'];assert (len(arts),sum(m['fresh'] for m in arts))==(r['typed'],r['fresh'])
    launches=[];children=defaultdict(set);opens=defaultdict(list)
    for k,raw in full.items():
     pid=int(k);pending=''
     for line in raw.splitlines():
      if line.endswith('<unfinished ...>'):assert not pending;pending=line[:line.index('<unfinished ...>')];continue
      if line.startswith('<... ') and ' resumed>' in line:
       assert pending;start,_,end=line.partition(' resumed>');assert start[5:]==pending.partition('(')[0];line=pending+end;pending=''
      born=re.fullmatch(r'(?:clone|clone3|vfork|fork)\(.*\)\s*= (\d+)',line)
      if born:children[pid].add(int(born[1]))
      if line.startswith('openat(') and lib in line:
       op=re.match(r'openat\([^,]+, ("(?:[^"\\]|\\.)*"), .*\)\s*= (-?\d+)',line)
       if op:opens[pid].append((ast.literal_eval(op[1]),int(op[2])))
      if line.startswith('execve(') and line.endswith('= 0'):
       m=re.fullmatch(r'execve\(("(?:[^"\\]|\\.)*"), (\[.*\]), .*\)\s*= 0',line);assert m
       launches.append((pid,ast.literal_eval(m[1]),ast.literal_eval(m[2])))
     assert not pending or not pending.startswith(('openat(','execve(','clone(','clone3('))
    actualcargo=[(pid,v,a) for pid,v,a in launches if '/toolchains/ohm/bin/cargo' in v];assert len(actualcargo)==1 and actualcargo[0][0]==trace['cargo'][0]['pid'] and actualcargo[0][2]==trace['cargo'][0]['argv'] and trace['cargo'][0]['sha']==kit['cargo_sha']
    allrc=[(pid,a) for pid,v,a in launches if v.endswith('/toolchains/ohm/bin/rustc')]
    fullrc=sorted((pid,a[a.index('--crate-name')+1]) for pid,a in allrc if '--crate-name' in a and any(x.endswith('.rs') for x in a));cached=sorted(pid for pid,a in allrc if '-Zlink-only' in a or any(x.startswith('-Zlink-only=') for x in a))
    assert fullrc==sorted((x['pid'],x['crate']) for x in trace['compiles'])
    rawlinks=[(pid,v,a) for pid,v,a in launches if Path(v).name in {'ld','ld.bfd','ld.gold','ld.lld','rust-lld','lld','wild'}]
    assert sorted((pid,v,a) for pid,v,a in rawlinks)==sorted((z['pid'],z['image'],z['argv']) for z in trace['native_links'])
    terms={};allnames=[]
    for pid,v,a in rawlinks:
     iswild='/wild-ld/' in v;prior,=[z for z in trace['native_links'] if z['pid']==pid and z['image']==v and z['argv']==a]
     assert prior['wild']==iswild and (not iswild or prior['sha']==kit['wild']);native_images[Path(v).name+'-'+('wild' if iswild else 'system')]=prior['sha']
     allnames.append('wild' if iswild else Path(v).name)
     if '-o' not in a:continue
     out=Path(a[a.index('-o')+1]);which=next((i for i in bins if out.name==i or out.name.startswith(i+'-')),None)
     assert which==prior['root']
     if not which:continue
     assert iswild==want_wild;family={pid};work=[pid]
     while work:
      for child in children[work.pop()]-family:family.add(child);work.append(child)
     got=[(name,fd) for p1 in sorted(family) for name,fd in opens[p1]]
     assert got==[tuple(z) for z in prior['provider_lookups']]
     chosen={Path(q).parent.name for q,fd in got if fd>=0};assert chosen==({'early'} if inp['early'] else {'late'}),(kind,stage,role,which,chosen)
     assert which not in terms;terms[which]=chosen.pop()
    warm=role in ('ordinary','repeat');expect=known if declared or not warm else 17;assert r['exit']==(0 if expect is not None else 101),(kind,stage,role,r['exit'])
    if r['exit']==0:
     assert set(r['products'])==set(bins) and not r['diagnostics']
     for name,z in r['products'].items():
      a,=[m for m in arts if m['target']['name']==name and m.get('executable')];assert a['fresh']==z['fresh']
      h=z['sha256']
      if h not in hashes:
       raw=gzip.decompress((ev/'elf'/(h+'.gz')).read_bytes());assert sha(raw)==h and len(raw)==z['bytes'] and raw.startswith(b'\x7fELF')
       fd=os.memfd_create('two-native-readback',os.MFD_CLOEXEC)
       with os.fdopen(fd,'wb') as f:
        f.write(raw);f.flush();os.fchmod(fd,0o500);run=subprocess.run(['/proc/self/fd/'+str(fd)],pass_fds=[fd],capture_output=True,timeout=5)
       assert run.returncode==0 and not run.stderr
       hashes[h]=run.stdout.decode().strip()
      assert hashes[h]==f'{name}={expect}' and z['value']==expect
    else:assert not r['products'] and r['diagnostics'] and any('linking' in e or 'archive' in e for e in r['diagnostics'])
    # A clean and a forced call must launch both terminal native links. An unchanged undeclared repeat must launch none.
    if not warm:assert set(terms)==set(bins)
    if warm and not declared and (role=='repeat' or stage!='original'):assert not terms
    if warm and declared and role=='ordinary':assert set(terms)==set(bins)
    if declared and role=='repeat' and known is not None:assert not terms
    if declared and role=='repeat' and known is None:assert set(terms)==set(bins)
    global_counts.update({'commands':1,'failures':int(r['exit']!=0),'launched_executables':len(r['products']),'full_rustc':len(fullrc),'cached_rustc':len(cached),'terminal_links':len(terms),'all_wild':allnames.count('wild'),'all_gnu':allnames.count('ld'),'trace_files':len(full)})
    b={k:z['sha256'] for k,z in r['products'].items()};rows[role]={'exit':r['exit'],'values':{k:z['value'] for k,z in r['products'].items()},'full_elf':b,'full_rustc':sorted(v for _,v in fullrc),'link_only':len(cached),'links':terms,'wild':allnames.count('wild'),'gnu_ld':allnames.count('ld'),'fresh':r['fresh'],'typed':r['typed'],'trace_sha256':sha(fs),'cargo_stdout_sha256':sha(typed),'cargo_stderr_sha256':sha(err)}
    rfiles.append((f'{kind}/{stage}/{role}',sha((p/'result.json').read_bytes()),sha(fs),sha(typed),sha(err)))
   assert rows['force']['full_elf']==rows['clean']['full_elf']
   if declared:assert all(rows[k]['full_elf']==rows['clean']['full_elf'] for k in roles)
   else:assert rows['ordinary']['full_elf']==rows['repeat']['full_elf'] and (stage in ('original','remove','restore'))==(rows['ordinary']['full_elf']==rows['clean']['full_elf'])
 assert global_counts['commands']==expected
 return dict(pins={k:kit[k] for k in ['cargo_sha','cargo_commit','rust_commit','rustc','driver','wild']},counts=dict(global_counts),cohort=body,native_images=native_images,source_hashes=root['sources'],input_sha256={k:{'early':v[0],'late':v[1]} for k,v in inputs.items()},unique_reexecuted_elf=len(hashes),raw_terminal_sha256=sha((ev/'result.json').read_bytes()),per_visit_sha256=rfiles)
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('root',type=Path);a.add_argument('out',type=Path);v=a.parse_args();result=grade(v.root);b=(json.dumps(result,sort_keys=True,indent=2)+'\n').encode()
 with v.out.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
 print(json.dumps({'sha256':sha(b),'bytes':len(b),'counts':result['counts'],'elf':result['unique_reexecuted_elf'],'raw':result['raw_terminal_sha256']},sort_keys=True))
