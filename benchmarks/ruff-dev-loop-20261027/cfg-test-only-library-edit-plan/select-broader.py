"""Input-only selection. Make no Cargo calls or consult compilation/ELF or timing outcomes."""
from pathlib import Path
import difflib,hashlib,json,re,subprocess,tempfile
D=Path(__file__).resolve().parent;g=['git','-C','/home/dev-user/code/oss/ruff'];base='93526150df078af7dd8fc4226cdcc469539d2001'
def run(*args,**kw):return subprocess.check_output([*g,*args],**kw)
log=re.split(r'(?m)^COMMIT (?=[0-9a-f]{40}\t)',run('log','-10000','--no-merges','--format=COMMIT %H%x09%s','--name-only',base).decode())[1:];cand=[];sk=[];containers={}
for rank,v in enumerate(log):
 rows=v.strip().splitlines();h,_,title=rows[0].partition('\t');files=[x for x in rows[1:] if x.strip()]
 if len(files)!=1 or not re.fullmatch(r'crates/[^/]+/src/.+\.rs',files[0]):continue
 f=files[0]
 if f not in containers:
  b=subprocess.run([*g,'show',base+':'+f],capture_output=True).stdout
  matches=list(re.finditer(rb'(?m)^#\[cfg\(test\)\]\n(?:#\[[^\n]+\]\n)*(?:(?:pub|pub\([^\n]*\)) )?mod ([a-zA-Z0-9_]+) \{\n',b))
  result=None
  for m in reversed(matches):
   # Scope must end at the first flush-left closing brace, permitting trailing non-Rust whitespace only.
   mt=re.search(rb'(?m)^\}\r?\n?',b[m.end():])
   if not mt:continue
   end=m.end()+mt.end()
   if b[end:].strip():continue
   result=(b,m.start(),m.end(),end,m[1].decode());break
  containers[f]=result
 c=containers[f]
 if not c:continue
 b,attr,start,end,mod=c
 if not re.search(r'.',title,re.I):continue
 p=run('diff','--no-ext-diff','--no-renames','--full-index','--binary',h+'^',h)
 if len(p)>60000:continue
 with tempfile.TemporaryDirectory(dir=D) as tmp:
  tmp=Path(tmp);pp=tmp/f;pp.parent.mkdir(parents=True);pp.write_bytes(b);res=subprocess.run(['git','apply','--no-index','-R','--whitespace=nowarn','-'],input=p,cwd=tmp,capture_output=True)
  if res.returncode!=0:continue
  changed=pp.read_bytes()
 if b[:start]!=changed[:start] or b[end:]!=changed[len(changed)-(len(b)-end):] or b==changed:continue
 orig=b.splitlines(keepends=True);new=changed.splitlines(keepends=True);changes=[(i,j,a,z) for o,i,j,a,z in difflib.SequenceMatcher(a=orig,b=new,autojunk=False).get_opcodes() if o!='equal']
 if not changes:continue
 first_orig=sum(map(len,orig[:min(i for i,j,a,z in changes)]));last_orig=sum(map(len,orig[:max(j for i,j,a,z in changes)]))
 if first_orig<start or last_orig>end-2:continue
 cand.append(dict(rev=h,rank=rank,title=title,file=f,module=mod,attr=attr,body=start,end=end,first_original_byte=first_orig,last_original_byte=last_orig,original_bytes=len(b),edited_bytes=len(changed),original_lines=len(orig),edited_lines=len(new),original_sha256=hashlib.sha256(b).hexdigest(),edited_sha256=hashlib.sha256(changed).hexdigest(),line_ranges=changes,bytes_to_module_end=end-last_orig,patch_sha256=hashlib.sha256(p).hexdigest()))
final=sorted(cand,key=lambda a:(a['original_bytes']!=a['edited_bytes'] or a['original_lines']!=a['edited_lines'],a['bytes_to_module_end']>128,a['rank']))
(D/'candidate-inputs.json').write_text(json.dumps({'source_history_cap':10000,'selector':'complete reverse applicable single-source patch inside preexisting final #[cfg(test)] module, same byte and line lengths preferred, then last changed original byte within 128 of EOF, then closest history rank','candidates':final},indent=2)+'\n')
print('candidates',len(final));print([(a['rev'][:11],a['file'],a['original_bytes']-a['edited_bytes'],a['original_lines']-a['edited_lines'],a['bytes_to_module_end'],a['title']) for a in final[:8]])
if final:
 w=final[0];p=run('diff','--no-ext-diff','--no-renames','--full-index','--binary',w['rev']+'^',w['rev']);assert hashlib.sha256(p).hexdigest()==w['patch_sha256'];(D/'historical.patch').write_bytes(p);(D/'selected.json').write_text(json.dumps(w,sort_keys=True,indent=2)+'\n')
