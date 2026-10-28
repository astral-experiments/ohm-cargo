"""Read completed H1 operational controls; summarize actual process rosters while retaining input hashes."""
from pathlib import Path
import hashlib,json,re,os
N=Path(__file__).resolve().parent
def sha(p):return hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
def events(path):
 lines=[];pending={};failed=0
 for raw in path.read_text().splitlines():
  m=re.match(r'(\d+)\s+(.*)',raw)
  if not m:continue
  pid,msg=m.groups()
  if msg.startswith('execve('):
   if msg.endswith('<unfinished ...>'):
    pending[pid]=msg[:-len('<unfinished ...>')];continue
  elif msg.startswith('<... execve resumed>'):
   msg=pending.pop(pid)+msg[len('<... execve resumed>'):]
  else:continue
  if re.search(r'= 0\s*$',msg):
   e=re.match(r'execve\("((?:\\.|[^"])*)",',msg);assert e,msg[:120];lines.append((int(pid),Path(e.group(1)),msg))
  else:failed+=1
 assert not pending,pending
 return lines
def roster(tr,front):
 result=[]
 for pid,p,line in events(tr):
  if not p.is_file():continue
  if p.name=='rustc' and p.samefile(front):
   m=re.search(r'"--crate-name", "([^"]+)"',line)
   if m and '"--print=' not in line:result.append({'pid':pid,'exec':'rustc','crate':m.group(1),'phase':'relink' if '"link-only"' in line or '"-Zlink-only"' in line else 'full','explicit_first':'"-Zohm-observer-dep-info"' in line,'explicit_binary':'"-Zbinary-dep-depinfo"' in line})
   elif '"--print=sysroot"' in line and '"-Zohm-observer-dep-info"' in line:result.append({'pid':pid,'exec':'observer-query'})
  elif p.name in ('ld','ld.bfd','ld.lld','wild','rust-lld') and '"-o"' in line:result.append({'pid':pid,'exec':'native-linker','image':sha(p)})
 return result
def small(root,data,effective=None):
 front=(effective or root/'active-sdk')/'bin/rustc';rows={}
 for key,v in data.items():
  origin=root/'case/records'/key;provenance={p.name:sha(p) for p in origin.iterdir() if p.name in ('native','stderr','stdout.jsonl','exec','fingerprint','rustc.d')}
  raw=origin/'exec';rs=roster(raw,front)
  rows[key]={k:v[k] for k in ['value','units','fresh','all_fresh','elf','fp_sha','complete','dep_sha','stamps','real','wire','version','native'] if k in v};rows[key].update(original_sha256=provenance,processes=rs,has_optional=b'# ohm-observer-inputs-v1 ' in (origin/'rustc.d').read_bytes())
 return rows
cases={}
for case in ('old-rust-cargo-baseline','N-old-raw','Q-old-raw','A-common','Q-common','N-common'):
 root=N/case;v=json.loads((root/('rechecked-observer.json' if case=='Q-old-raw' else 'result.json')).read_bytes());cases[case]=small(root,v['rows'])
for k,f,sd in [('guard-switch-v2','rechecked-namespace-results.json',None),('guard-wrapper-v3','results.json',N/'N-common/active-sdk'),('guard-off-v2','results.json',N/'N-common/active-sdk')]:
 root=N/k;v=json.loads((root/f).read_bytes());cases[k]=small(root,v,sd)
ops={}
for arm in ('A','N'):
 root=N/'ron-native-probe-v3'/arm;v=json.loads((root/'result.json').read_bytes());ops[arm]={};front=N/(arm+'-common')/'active-sdk/bin/rustc'
 for label,r in v.items():
  d=root/label;stable={'units':r['units'],'fresh':r['fresh'],'complete':r['complete'],'has_optional':r['optional'],'ordinary_checksums':r['ordinary_checksums'],'programs':r['programs'],'processes':roster(d/'exec',front),'original_sha256':{f.name:sha(f) for f in d.iterdir() if f.is_file()}}
  ops[arm][label]=stable
p=N/'common-release';release=json.loads((p/'receipt.json').read_bytes())
print(json.dumps({'format':1,'small':cases,'ron':ops,'registry':json.loads((N/'ron-native-probe-v3/preflight.json').read_bytes()),'permanent':{k:v for k,v in json.loads((N/'permanent/result.json').read_bytes()).items() if k!='stderr_last'},'unit':json.loads((N/'cargo-func/unit.json').read_bytes())['tail'][-12:],'images':{'supporting_compiler':release['candidate_postbolt'],'common_frontend':release['frontend'],'cargo_A':sha(N.parent/'release-unicode/subjects/rc17-complete-v4'),'cargo_Q':sha(N/'cargo-func/cargo-Q'),'cargo_N':sha(N/'cargo-func/cargo-N')},'prior_parser_failures':['First unscored wrapper counter counted the wrapper and the real rustc, because the wrapper also carries rustc as argv[1]. Corrected reader uses the execve executable as well as the PID.','Both physical namespaces legitimately remained in the post-swap target. The reader now uses the actual compiler --out-dir; original raw successful downgrade was recovered.','Q on the unsupported compiler truly attempts its old query; the original proof-only classifier expected none from all legacy arms. Q original row is retained and source/remaining outputs match.','The first two registry fixtures exited before any compilation (unmounted private sysroot, then unmapped configured registry). The six original native commands use private offline caches.']},sort_keys=True))
