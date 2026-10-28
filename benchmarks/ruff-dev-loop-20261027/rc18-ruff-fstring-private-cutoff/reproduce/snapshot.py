from prime import *
import re,ast,mmap,collections

def dig(x):return hashlib.sha256(x).hexdigest()
def capture(path):
 # Whole physical immutable copies, never hardlinked to a future Cargo output.
 h=sha(path);out=Y/'objects'/h
 if not out.exists():
  tmp=out.with_suffix('.tmp');sp.run(['cp','--reflink=auto','--',path,tmp],check=True);assert sha(tmp)==h;os.replace(tmp,out)
 return h

def armap(blob, h):
 dest=Y/'objects'/('ar-'+h+'.json')
 if dest.exists():return
 with blob.open('rb') as f,mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as a:
  assert a[:8]==b'!<arch>\n',blob;off=8;nt=b'';members=[]
  while off<len(a):
   header=a[off:off+60];assert len(header)==60 and header[-2:]==b'`\n',(blob,off);tag=header[:16].rstrip(b' ').decode();sz=int(header[48:58]);start=off+60;end=start+sz;assert end<=len(a);name=tag
   if tag=='//':nt=a[start:end]
   elif tag.startswith('/') and tag[1:].isdigit():
    pos=int(tag[1:]);term=nt.find(b'/\n',pos);assert term>=0;name=nt[pos:term].decode()
   elif tag not in ('/','/SYM64/') and tag.endswith('/'):name=tag[:-1]
   members.append({'name':name,'header_sha256':dig(header),'bytes':sz,'sha256':dig(a[start:end]),'offset':start,'elf':a[start:start+4]==b'\x7fELF'});off=end+(sz%2)
  assert off==len(a);write(dest,{'archive_sha256':h,'bytes':len(a),'members':members})

def native(d):
 cmd_re=re.compile(r'^execve\(("(?:[^"\\]|\\.)*"), (\[.*\]), [^\n]*\)\s+= 0$')
 jobs=[]; counts=collections.Counter(); hashsrc=lambda a:dig(json.dumps(a,ensure_ascii=True,separators=(',',':')).encode());link=[]
 for p in sorted(d.glob('exec.*')):
  if p.stat().st_size==0:continue
  for line in p.read_text(errors='surrogateescape').splitlines():
   if not line.startswith('execve(') or not line.rstrip().endswith('= 0'):continue
   m=cmd_re.match(line);assert m,(str(p),line[:300]);exe=ast.literal_eval(m[1]);a=ast.literal_eval(m[2]);base=Path(exe).name;counts[base]+=1
   if base in ('ld.bfd','wild','ld.lld','rust-lld','collect2','gcc','cc'):
    link.append({'pid':int(p.suffix[1:]),'path':exe,'name':base,'output':a[a.index('-o')+1] if '-o'in a else None,'argv_sha256':hashsrc(a)}); continue
   if base!='rustc' or '--crate-name' not in a:continue
   nm=a[a.index('--crate-name')+1]; cratety=[v for i,v in enumerate(a) if i and a[i-1]=='--crate-type'];kind='link-only' if '-Zlink-only' in a or any(v=='link-only' and i and a[i-1]=='-Z' for i,v in enumerate(a)) else 'full'; paths=[z for z in a if z.endswith('.rs') or z.endswith('.rlink')]; jobs.append({'pid':int(p.suffix[1:]),'name':nm,'crate_types':cratety,'kind':kind,'args':a,'argv_sha256':hashsrc(a),'sources':paths[:2]})
 write(d/'processes.json',{'counts':counts,'jobs':jobs,'native':link});return jobs

def products(d):
 rows=[json.loads(x) for x in (d/'stdout.jsonl').read_text().splitlines()]; arts=[z for z in rows if z['reason']=='compiler-artifact'];assert rows[-1]['reason']=='build-finished' and rows[-1]['success']; out=[]
 for row in arts:
  local=row['package_id'].startswith('path+file:');target=row['target'];files={}
  for raw in row['filenames']:
   f=Path(raw); assert f.is_file(),str(f);save=local; h=capture(f) if save else sha(f);files[str(f)]={'sha256':h,'bytes':f.stat().st_size,'mtime_ns':f.stat().st_mtime_ns,'cas':save}
   if save and f.suffix=='.rlib':armap(Y/'objects'/h,h)
   if save and f.suffix=='.rmeta':
    cache=Y/'objects'/('rmeta-'+h+'.json')
    if not cache.exists():
     cmd=[PROXY/'rustc','+ohm','-Zls=root',f]; q=sp.run(cmd,env=env(),cwd=W,capture_output=True);raw=(q.stdout+q.stderr).decode(errors='replace');assert q.returncode==0 and 'public_hash 'in raw and 'private hash 'in raw,(str(f),raw[:1000]);write(cache,{'sha256':h,'header':'\n'.join(raw.splitlines()[:9]),'root_output_sha256':dig(q.stdout),'exit':q.returncode})
  out.append({'package':row['package_id'],'target':target['name'],'kind':target['kind'],'types':target['crate_types'],'fresh':row['fresh'],'local':local,'files':files})
 write(d/'artifacts.json',out);return rows,out

def reader(d,rows,out):
 ext={};ls=set();nl=[]
 for target in out:
  for f in target['files']:
   if Path(f).suffix in ('.rmeta','.rlib','.so'):ls.add(str(Path(f).parent))
   if target['local'] and target['target'] in ('ruff_python_ast','ruff_python_parser') and f.endswith('.rlib'):ext[target['target']]=f
 for r in rows:
  if r['reason']=='build-script-executed':nl+=r['linked_paths']
 assert len(ext)==2; exe=Y/'external-reader';cmd=[PROXY/'rustc','+ohm','--edition=2024','--crate-name','external_truthiness',Y/'caller.rs','-o',exe]
 for n,f in sorted(ext.items()):cmd+=['--extern',n+'='+f]
 for n in sorted(ls):cmd+=['-L','dependency='+n]
 for n in sorted(set(nl)):cmd+=['-L',n]
 q=sp.run(cmd,cwd=W,env=env(),capture_output=True);(d/'caller-compile.stderr').write_bytes(q.stderr);assert q.returncode==0,(d,q.stderr.decode(errors='replace')[-1000:]); q=sp.run([exe],cwd=W,env=env(),capture_output=True);assert q.returncode==0
 # Invoke the real Ruff diagnostic for the four expressions, independent of this separately compiled reader.
 data='print(f"{x}abc" or "bar")\nprint(f"" f"{x}" or "bar")\nprint(f"{\'x\':.0}" or "bar")\nprint(f"{x > y}" or "bar")\n';cli=P/'target/debug/ruff';args=[cli,'check','--isolated','--no-cache','--select','SIM222','--output-format','json','-'];result=sp.run(args,cwd=W,env=env(),input=data.encode(),capture_output=True);(d/'ruff.stderr').write_bytes(result.stderr);assert result.returncode==1,(d,result.returncode,result.stderr); diags=json.loads(result.stdout);assert all(z['code']=='SIM222' for z in diags);write(d/'cli-diagnostics.json',diags)
 z=sp.run(['nm','-A','--defined-only','--demangle',ext['ruff_python_ast']],capture_output=True);assert z.returncode==0; symbols=[l for l in z.stdout.decode(errors='replace').splitlines() if 'is_non_empty_f_string' in l];(d/'helper-symbols.txt').write_text('\n'.join(symbols)+'\n');assert any(re.search(r' [tT] (?:.+::)?is_non_empty_f_string(?:\[[0-9a-f]+\])?$',s) for s in symbols),symbols[:3]
 result={'external_output':q.stdout.decode().splitlines(),'external_sha256':capture(exe),'cli_sha256':capture(cli),'cli_lines':[z['location']['row'] for z in diags],'cli_exit':1,'complete_cli_json_sha256':sha(d/'cli-diagnostics.json'),'defined_helper_symbols':len(symbols),'external_input_rlibs':{n:sha(f) for n,f in ext.items()}};write(d/'programs.json',result);return result

def snapshot(phase):
 d=Y/'receipts'/phase;assert json.loads((d/'exit.json').read_text())=={'returncode':0}; jobs=native(d);rows,out=products(d); programs=reader(d,rows,out);write(d/'complete.json',{'cargo_artifacts':len(out),'cargo_fresh':sum(x['fresh'] for x in out),'rustc':dict(collections.Counter(j['kind'] for j in jobs)),'programs':programs});return programs
