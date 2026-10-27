from pathlib import Path
import hashlib,json,re,subprocess
root=Path(__file__).resolve().parent;repo=Path('/home/dev-user/code/oss/ruff-ohm-private-trait-20261026');base='93526150df078af7dd8fc4226cdcc469539d2001';seed='ohm-build-private-parser-independent-20261027-v1';prefix='crates/ruff_python_parser/src/parser/';paths=[prefix+s for s in ['expression.rs','pattern.rs','statement.rs','mod.rs','parameters.rs']];skip=['3ea20f6161','0ecff87790','6e29838d4b','42cbce538b'];git=lambda *args:subprocess.check_output(['git','-C',repo,*args]);incl=[]
for sha in git('rev-list','--no-merges','--max-count=150',base,'--',*paths).decode().splitlines():
 if any(sha.startswith(s) for s in skip):continue
 ch=git('diff','--name-only',sha+'^',sha).decode().splitlines();rs=[f for f in ch if f.endswith('.rs')];
 if len(rs)!=1 or rs[0] not in paths or len(ch)>18:continue
 body=git('diff','-U0',sha+'^',sha,'--',rs[0]);lines=body.decode().splitlines();delta=[l[1:] for l in lines if l[:1] in ('+','-') and not l.startswith(('---','+++'))];hs=[l for l in lines if l.startswith('@@')];
 if not 2<=len(delta)<=65 or not all('Parser<' in h for h in hs) or any(re.match(r'\s*(pub(\s|\()|const\s|#\[inline|impl\b|trait\s|struct\s|enum\s)',l) for l in delta):continue
 if not any(l.strip() and not l.strip().startswith(('//','/*','*')) for l in delta):continue
 patch=git('diff','--binary',sha+'^',sha);app=subprocess.run(['git','--no-optional-locks','-C',repo,'apply','--reverse','--check','-'],input=patch,capture_output=True).returncode==0;rank=hashlib.sha256((seed+'\n'+sha).encode()).hexdigest();incl.append(dict(sha=sha,title=git('show','-s','--format=%s',sha).decode().strip(),applies=app,rank=rank,changed_lines=len(delta),files=ch,patch_sha256=hashlib.sha256(patch).hexdigest()));
incl.sort(key=lambda r:r['rank']);pool=[x for x in incl if x['applies']] or incl;selected=pool[0] if pool else None;print('candidates',len(incl),'applied',sum(x['applies'] for x in incl),'chosen',selected,flush=True);(root/'holdout-selection.json').write_text(json.dumps({'base':base,'seed':seed,'candidates':incl,'selected':selected},indent=2)+'\n')
