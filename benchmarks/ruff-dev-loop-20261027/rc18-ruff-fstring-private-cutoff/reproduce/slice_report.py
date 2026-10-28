from analyze_v2 import *
import gzip

def onephase(ph):
 d=Y/'receipts'/ph;x=read(d/'processes.json');a=read(d/'artifacts.json');js=x['jobs'];return {'artifacts':len(a),'fresh':sum(z['fresh']for z in a),'full_by_type':{k:[v['name']for v in js if v['kind']=='full' and label(v)==k]for k in ('rlib','mixed','bin','proc-macro','other')},'link_only':[v['name']for v in js if v['kind']=='link-only'],'all_full':sum(v['kind']=='full'for v in js),'native_outputs':[Path(z['output']).name for z in x['native'] if z['name']=='ld.bfd'],'programs':read(d/'programs.json'),'sources':{Path(p).name:v for p,v in read(d/'inputs.json')['source_files'].items()},'commitments':{n:sha(d/n)for n in ('artifacts.json','processes.json','inputs.json','programs.json','complete.json','exit.json','stdout.jsonl','stderr')}}
def label(v):
 s=v['crate_types'];return 'mixed' if 'cdylib'in s and 'rlib'in s else ('rlib' if s in (['rlib'],['lib']) else (s[0] if len(s)==1 and s[0] in ('bin','proc-macro') else 'other'))
def pointer(ph):
 d=Y/'receipts'/ph; z=read(d/'processes.json');r={}
 for v in z['jobs']:
  if v['name'] not in ('ty_python_semantic','ty_wasm','ruff_wasm','ruff_python_ast') or v['kind']!='full':continue
  args=v['args'];out=Path(args[args.index('--out-dir')+1]);fd=[]
  for p in sorted(out.glob('*.d')):
   content=p.read_bytes(); tokens=[needle.decode() for needle in (b'ohm-foreign-span-bytes',b'ohm-proc-macro',b'ohm-worktree-seed')if needle in content];fd.append({'name':p.name,'sha256':dig(content),'select_markers':tokens,'bytes':len(content)})
  r[v['name']]={'actual_argv_sha256':v['argv_sha256'],'crate_types':v['crate_types'],'emit_flags':[x for x in args if x.startswith('--emit')],'ohm_flags':[x for x in args if x.startswith(('-Zpublic-api','-Zrelink-only','-Zthreads','-Zcache-proc-macros','-Zchecksum','-Zbinary-dep'))],'current_depfiles':fd}
 return r

def audit_raw(phases):
 packed={};maps={};refs={}
 for ph in phases:
  z=read(Y/'receipts'/ph/'artifacts.json');raw=[]
  for u in z:
   if not u['local'] or not any(p.endswith('.rlib')for p in u['files']):continue
   fs={Path(p).name:{'sha256':x['sha256'],'bytes':x['bytes']} for p,x in u['files'].items()};raw.append({'crate':u['target'],'kind':u['kind'],'types':u['types'],'fresh':u['fresh'],'files':fs});
   for p,x in fs.items():
    h=x['sha256'];
    if p.endswith('.rlib'):
     if h not in maps:
      ix=read(Y/'objects'/('ar-'+h+'.json'));assert sha(Y/'objects'/h)==h;maps[h]=ix
    if p.endswith('.rmeta'):
     if h not in refs:
      header=read(Y/'objects'/('rmeta-'+h+'.json'));assert sha(Y/'objects'/h)==h;refs[h]=header
  packed[ph]=raw
 # All original archive and .rmeta bytes and complete ar indexes remain on the host. The packet commits every member in encounter order.
 raw=json.dumps({'phases':packed,'archives':maps,'rmeta':refs},separators=(',',':'),sort_keys=True).encode();(Y/'all-rosters.json.gz').write_bytes(gzip.compress(raw,compresslevel=8,mtime=0));return {'archive_digests':len(maps),'metadata_digests':len(refs),'members':sum(len(i['members'])for i in maps.values()),'raw_bytes':len(raw),'gzip_sha256':sha(Y/'all-rosters.json.gz'),'gzip_bytes':(Y/'all-rosters.json.gz').stat().st_size}
if __name__=='__main__':
 while not (Y/'slice-terminal.json').exists():time.sleep(5)
 gate=read(Y/'slice-terminal.json');roots=read(Y/'terminal.json');ss=gate['phases'];ds={a+'__'+b:delta(a,b,{ 'ruff_python_ast','ruff_python_parser','ruff_linter','ty_python_semantic','ruff_wasm','ty_wasm'} if n==0 else set())for n,(a,b)in enumerate([('slice-baseline','slice-warm'),('slice-warm','slice-repeat'),('slice-repeat','slice-cold'),('slice-repeat','slice-restore'),('slice-baseline','slice-restore-repeat')])};result={'inputs':read(Y/'slice-control/input.json'),'phases':{p:onephase(p) for p in ss},'local_libraries':ds,'source_locations':{p:symbols(p)for p in ('slice-baseline','slice-warm','slice-cold','slice-restore')},'restored_depinfo':pointer('slice-restore-repeat'),'native_commitments':audit_raw(roots['phases']+ss)};write(Y/'slice-result.json',result)
