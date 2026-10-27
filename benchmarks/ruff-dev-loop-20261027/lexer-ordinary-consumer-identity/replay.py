from pathlib import Path
import json,collections,struct
class R:
 def __init__(s,b):s.v=b;s.root=int.from_bytes(b[8:16],'little');s.i=s.root;s.prev=None
 def raw(s,n):r=s.v[s.i:s.i+n];s.i+=n;return r
 def u(s):
  ret=0;j=0
  while 1:
   b=s.raw(1)[0];ret|=(b&127)<<j
   if not b&128:return ret
   j+=7
 def text(s):v=s.raw(s.u()).decode();assert s.raw(1)==b'\xc1';return v
 def sym(s):
  k=s.u()
  if k==0:return s.text()
  n=s.u()
  if k==2:return n
  assert k==1;i=s.i;s.i=n;t=s.text();s.i=i;return t
 def arr(s):
  n=s.u()
  if not n:return (0,0)
  d=s.u();s.prev=s.root-d if s.prev is None else s.prev+d;return n,s.prev
 def deps(s):
  assert s.u()==0;s.text();s.raw(32);s.sym();s.raw(2);s.text();s.raw(8)
  if s.u():s.u()
  s.u();s.u();s.raw(4);s.arr();n,pos=s.arr();s.i=pos;z=[]
  for c in range(1,n+1):
   name=s.sym();hash=s.raw(16).hex();host=s.raw(16).hex()if s.u()else None;k=s.u();extra=s.text();pr=s.u();z.append([name,c,hash,extra,host,k,pr])
  return z

from pathlib import Path
import ast, hashlib, json, os, re, shutil, subprocess, sys

base=Path.home()/'.cache/ohm-233-position-qualified-20261027'
suite=base/'first-occurrence-mixed-parser-20261027'; state=suite/'state/test/B'
snap=base/'first-occurrence-parser-b-diagnostic-20261027'; run=base/'lexer-identity-falsifier-v1'
P=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027'); F=P/'frozen-toolchain'
W=Path('/home/dev-user/code/oss/ruff-ohm-whole-native-20261027'); sr=Path('crates/ruff_python_parser/src/lexer.rs'); sig='librustc_driver-774a793a844d5500.so'
parser='ruff_python_parser'; cg='ruff_python_codegen'; imp='ruff_python_importer'
Dmixed='7c31057e86f800e313b7d32080c7a5abaa7b92fef92254ac21b2e43febf16384'; D233='dec72d1e68fdb0f8ff91fc98e8a826bf837878eca30b1ec5ea2f3258b6b2f99f'
get=lambda p:json.loads(p.read_bytes())
def sha(p):
 with p.open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()
def save(p,z):p.write_text(json.dumps(z,indent=2,sort_keys=True)+'\n')
def root(p):
 b=p.read_bytes();r=R(b);assert r.u()==0;triple=r.text();priv=r.raw(16).hex();pub=r.raw(16).hex();return {'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b),'target':triple,'serialized_private_svh':priv,'serialized_public_svh':pub,'parser_edges':[v for v in R(b).deps() if v[0]==parser]}
def physical(p):return state/'target'/p.relative_to(P/'native-target')
assert sorted(os.sched_getaffinity(0))==[30] and get(suite/'complete.json') and (state/'source-state').read_text().strip()=='original'
if len(sys.argv)>1: run=run.with_name(run.name+'-'+sys.argv[1])
assert not run.exists();run.mkdir(mode=0o700);out=run/'results';out.mkdir();shutil.copytree(state/'rustup',run/'rustup',symlinks=True)
old=get(snap/'restored'/'receipt.json'); L=old['trace_inputs']['ruff_linter']['L_search_arguments']; dirs=[Path(s[11:]) for s in L if s.startswith('dependency=')];assert set(L[::2])=={'-L'} and len(set(dirs))==len(dirs),(len(dirs),len(L))
prod=Path(old['compiler_reported_path']);dirs_of={n:next(p for p in dirs if p.parts[-3]==n) for n in (cg,imp,parser)}; assert dirs_of[parser]==prod.parent
md={n:dirs_of[n]/next(physical(dirs_of[n]).glob('lib*.rmeta')).name for n in dirs_of}
assert md[parser]==prod; vers={}; phys={n:root(physical(p)) for n,p in md.items()}; curr_key=phys[parser]['serialized_public_svh'];assert all(phys[n]['parser_edges'][0][2]==curr_key for n in (cg,imp))
for v in ('restored','edited'):
 s=snap/v/prod.name;ev=get(snap/v/'receipt.json');assert sha(s)==ev['rmeta_sha256'];d=run/'sources'/v;d.mkdir(parents=True);shutil.copyfile(s,d/prod.name);vers[v]=root(s);assert sha(snap/v/'lexer.rs')==ev['lexer_rs_sha256']
assert curr_key==vers['restored']['serialized_public_svh'] and curr_key not in (vers['edited']['serialized_private_svh'],vers['edited']['serialized_public_svh'])
# Confirm that no other Cargo-provided dependency directory has matching artifacts.
choices={str(q):[f.name for f in physical(q).glob('libruff_python_parser-*') if f.suffix in ('.rlib','.rmeta','.so')] for q in dirs};choices={k:v for k,v in choices.items() if v};assert list(choices)==[str(prod.parent)],choices
source={cg:'extern crate ruff_python_codegen;\npub use ruff_python_codegen::Mode as PythonPrinterMode;\n',imp:'extern crate ruff_python_importer;\npub use ruff_python_importer::Insertion as PythonImportInsertion;\n',parser:'pub use ruff_python_parser::lexer::lex as current_lexer;\n','diag':'pub fn check_exported_function() {\n    let _ = ruff_python_parser::lexer::lex();\n}\n'}
for k,v in source.items():(out/(k+'.rs')).write_text(v)
rows=[];drivers={}
def command(driver,v,case,args,mode='caller'):
 dd=base/'drivers'/('driver-'+driver);drivers[driver]={'actual_sha256':sha(dd),'frontend_sha256':sha(F/'bin/rustc')};assert drivers[driver]['actual_sha256']==driver
 d=out/(driver[:8]+'-'+v+'-'+case);d.mkdir();trial=[str(d/'out') if a=='@OUTDIR@' else str(d/'ordinary.rmeta') if a=='@RMETA@' else a for a in args];(d/'out').mkdir()
 wraps=['bwrap','--ro-bind','/','/','--dev-bind','/dev','/dev','--proc','/proc','--bind',str(run/'rustup'),str(P/'rustup'),'--bind',str(d),str(d)]
 for ph,lg in [('target','native-target'),('shared','shared'),('registry-home','registry-home')]:wraps+=['--ro-bind',str(state/ph),str(P/lg)]
 for src,dst in [(run/'sources'/v,prod.parent),(snap/v/'lexer.rs',W/sr),(dd,F/'lib'/sig)]:wraps+=['--ro-bind',str(src),str(dst)]
 cmd=['rustc','+ohm',*trial];env=dict(os.environ,RUSTUP_HOME=str(P/'rustup'),RUSTUP_AUTO_INSTALL='0',CARGO_HOME=str(P/'registry-home'),LC_ALL='C.UTF-8',RUST_BACKTRACE='0')
 if v=='edited' and case in (cg,imp):env['RUSTC_LOG']='rustc_metadata::creader=info,rustc_metadata::locator=info'
 cp=subprocess.run(wraps+['--',*cmd],env=env,cwd=W,capture_output=True,timeout=60);(d/'stdout').write_bytes(cp.stdout);(d/'stderr.jsonl').write_bytes(cp.stderr);save(d/'argv.json',cmd)
 diags=[]
 for line in cp.stderr.splitlines():
  try: vj=json.loads(line)
  except ValueError:continue
  if (c:=vj.get('code')) and c.get('code'):diags.append({'code':c['code'],'message':vj['message'],'notes':[c['message'] for c in vj.get('children',[]) if c['level']=='note'],'definition_spans':[s for c in vj.get('children',[]) if 'defined here' in c['message'] for s in c.get('spans',[])]})
 log=cp.stderr.decode(errors='replace').splitlines(); selected=[s for s in log if any(v in s for v in ('Rejecting via hash:', "->\"ruff_python_parser", chr(96)+'->'+chr(96)+'ruff_python_parser'+chr(96)))];(d/'loader-rejections.log').write_text('\n'.join(selected)+'\n' if selected else '')
 row={'driver':driver,'parser':v,'caller_or_producer':case,'mode':mode,'status':cp.returncode,'diagnostics':diags,'stderr_sha256':sha(d/'stderr.jsonl'),'argv_sha256':sha(d/'argv.json'),'emitted_metadata_sha256':sha(d/'ordinary.rmeta') if (d/'ordinary.rmeta').is_file() else None};rows.append(row);print(driver[:8],v,case,cp.returncode,[(e['code'],e['message']) for e in diags],flush=True);save(d/'observation.json',row);return row,d
for driver in (Dmixed,D233):
 for v in ('restored','edited'):
  for crate in (cg,imp,parser,'diag'):
   n=parser if crate=='diag' else crate
   args=['--sysroot',str(F),'--crate-name','ordinary_external_caller','--crate-type','lib','--edition=2024','--emit=metadata','--error-format=json','--extern',n+'='+str(md[n]),*L,str(out/(crate+'.rs')),'-o','@RMETA@'];obs,d=command(driver,v,crate,args)
   if crate=='diag':assert [e['code'] for e in obs['diagnostics']]==['E0061'] and obs['diagnostics'][0]['definition_spans'][0]['line_start']==(1623 if v=='restored' else 1620),obs
   elif crate==parser or v=='restored':assert obs['status']==0 and obs['emitted_metadata_sha256'],(obs,(d/'stderr.jsonl').read_text()[-500:])
   else:assert obs['status']==1 and any(e['code'] in ('E0460','E0463') for e in obs['diagnostics']),(obs,(d/'stderr.jsonl').read_text()[-1800:])
# Recompile the real tiny unchanged source in a private output dir. Retain all genuine externs,
# cfgs, products and codegen flags, removing only incremental state and redirecting output.
D=suite/'receipts/test/B/lexer-pending-indentation-edit';orig=[t for t in get(D/'receipt.json')['processes']['jobs'] if t['crate']==cg and t['kind']=='full'];lines=[]
for t in orig:
 fp=D/t['pid'];lines.extend((s,fp) for s in fp.read_text().splitlines() if s.startswith('execve(') and s.endswith('= 0') and '"--crate-name", "ruff_python_codegen"' in s and '"--test"' not in s)
assert len(lines)==1,len(lines);line,tracef=lines[0];m=re.match(r'execve\(("(?:[^"\\]|\\.)*"),\s*(\[.*\]),\s*(?:0x[\da-f]+|NULL)',line);argv=[ast.literal_eval(x) for x in re.findall(r'"(?:[^"\\]|\\.)*"',m[2])];args=[];i=1
while i<len(argv):
 a=argv[i];i+=1
 if a=='--out-dir':args+=['--out-dir','@OUTDIR@'];i+=1
 elif a=='-C' and argv[i].startswith('incremental='):i+=1
 elif a=='-Cincremental' or a.startswith('-Cincremental='):assert a.startswith('-Cincremental=')
 else:args.append(a)
assert '--out-dir' in args and '--test' not in args and '--crate-name' in args and any(a.startswith('--emit=') and 'link' in a for a in args)
repl,d=command(Dmixed,'edited','rebuild-real-codegen',args,'fresh-native-bridge');assert repl['status']==0,(d/'stderr.jsonl').read_text()[-2000:];new=next((d/'out').glob('libruff_python_codegen*.rmeta'));newheader=root(new);assert newheader['parser_edges'][0][2]==vers['edited']['serialized_public_svh'];
recheck,cd=command(Dmixed,'edited','new-caller-rebuilt-real-bridge',['--sysroot',str(F),'--crate-name','ordinary_external_caller','--crate-type','lib','--edition=2024','--emit=metadata','--error-format=json','--extern',cg+'='+str(new),*L,str(out/(cg+'.rs')),'-o','@RMETA@']);assert recheck['status']==0 and recheck['emitted_metadata_sha256'],recheck
assert (state/'source-state').read_text().strip()=='original' and all(root(physical(p))==phys[n] for n,p in md.items()); save(out/'complete.json',{'parser':vers,'physical_restored':phys,'fresh_edited_codegen':newheader,'permitted_search_path_count':len(dirs),'dirs_with_parser_before_private_overlay':choices,'private_parser_entries':[f.name for f in sorted((run/'sources'/'edited').iterdir())],'compiler_driver_and_frontend':drivers,'unchanged_real_codegen_source':str(W/'crates/ruff_python_codegen/src/lib.rs'),'unchanged_real_codegen_source_sha256':sha(W/'crates/ruff_python_codegen/src/lib.rs'),'source_trace_sha256':sha(tracef),'source_trace_line_sha256':hashlib.sha256(line.encode()).hexdigest(),'rows':rows});print('COMPLETE',len(rows),flush=True)
