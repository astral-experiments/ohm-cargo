#!/usr/bin/env python3
"""Verify cached mixed-library decisions, the full native oracle and rebuilt Rust downstream consumers."""
from pathlib import Path
import hashlib,json,os,subprocess as sp,sys,shutil
D=Path(__file__).resolve().parent
ss=Path('/home/dev-user/.cache/ohm-ruff-packed-edges-20261026/nonleaf/trait-pgo-state')
rt=ss/'sysroot';front=rt/'bin/rustc';driver_name='librustc_driver-774a793a844d5500.so'
root=Path(sys.argv[1]).resolve();root.mkdir(exist_ok=False)
cargo=Path(sys.argv[2]).resolve(); driver=Path(sys.argv[3]).resolve(); target=root/'target'; shared=root/'shared'
main=root/'ws'; main.mkdir()
(main/'Cargo.toml').write_text('[workspace]\nmembers=["leaf","mid","bundle","app"]\nresolver="3"\n')
for name in ('leaf','mid','bundle','app'):
 p=main/name;(p/'src').mkdir(parents=True)
 toml=f'[package]\nname="{name}"\nversion="0.1.0"\nedition="2024"\n'
 if name=='bundle':toml+='[lib]\ncrate-type=["cdylib","rlib"]\n[dependencies]\nleaf={path="../leaf"}\nmid={path="../mid"}\n'
 if name=='app':toml+='[dependencies]\nbundle={path="../bundle"}\n'
 (p/'Cargo.toml').write_text(toml)
leaf=main/'leaf/src/lib.rs';mid=main/'mid/src/lib.rs'
base='pub fn value() -> i32 { inner() }\nfn inner() -> i32 { VALUE }\n'
mid.write_text('pub fn keep() -> i32 { 0 }\n')
bundle=main/'bundle/src/lib.rs'
bundle.write_text('#[unsafe(no_mangle)] pub extern "C" fn observed()->i32 { leaf::value() + mid::keep() }\npub fn via_rust()->i32 { observed() }\n')
(main/'app/src/main.rs').write_text('fn main(){println!("{}",bundle::via_rust());}\n')
wrapper=root/'wrapper'
wrapper.write_text('''#!/bin/sh
case " $* " in *" --crate-name "*) printf '%s\\0' "$@" > "$REC/child.$$.argv"; set -- "$@" --sysroot "$SYS";; esac
exec "$@"
''');wrapper.chmod(0o755)
env=dict(os.environ,RUSTUP_HOME=str(ss/'rustup'),RUSTUP_AUTO_INSTALL='0',RUSTUP_TOOLCHAIN='ohm',CARGO_HOME=str(root/'cargo-home'),CARGO_TARGET_DIR=str(target),CARGO_BUILD_BUILD_DIR=str(shared),CARGO_BUILD_JOBS='4',CARGO_INCREMENTAL='0',RUSTC=str(front),RUSTC_WRAPPER=str(wrapper),SYS=str(rt),LD_LIBRARY_PATH=str(rt/'lib'),GIT_OPTIONAL_LOCKS='0',CARGO_LOG='cargo::compiler::fingerprint=debug,cargo::compiler=info')
ns=['taskset','-c','0-3','bwrap','--ro-bind','/','/','--dev','/dev','--proc','/proc','--tmpfs','/tmp','--bind',str(root),str(root),'--ro-bind',str(cargo),str(rt/'bin/cargo'),'--ro-bind',str(driver),str(rt/'lib'/driver_name),'--chdir',str(main),'--','/home/dev-user/.cargo/bin/cargo','+ohm']
def run(rec,package):
 rec.mkdir(parents=True);args=[*ns,'build','--locked','--offline','-p',package,'--message-format=json']; env['REC']=str(rec)
 if not (main/'Cargo.lock').exists() or rec.parent.name=='transitive':args.remove('--locked')
 p=sp.run(args,env=env,capture_output=True);(rec/'stdout.jsonl').write_bytes(p.stdout);(rec/'stderr').write_bytes(p.stderr)
 if p.returncode:raise RuntimeError(p.stdout.decode()[-3100:]+p.stderr.decode()[-2500:])
 artifacts=[json.loads(l) for l in p.stdout.splitlines()]; children=[]
 for item in rec.glob('child.*.argv'):
  a=[j.decode() for j in item.read_bytes().split(b'\0') if j]
  children.append({'crate':a[a.index('--crate-name')+1], 'link_only':'link-only' in a or '-Zlink-only' in a,'argv':a})
 (rec/'children.json').write_text(json.dumps(children,indent=2))
 return {a['target']['name']:a for a in artifacts if a['reason']=='compiler-artifact'},children
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def result(outputs):
 meta,=[Path(x) for x in outputs['bundle']['filenames'] if x.endswith('.rmeta')]; so=meta.with_suffix('.so');lib=meta.with_suffix('.rlib')
 nm=sp.check_output(['nm','-D','--defined-only',so],text=True)
 al=sp.check_output(['ar','t',lib],text=True).splitlines()
 data={'sha256':sha(so),'rmeta':sha(meta),'exports':sorted(r.split()[-1] for r in nm.splitlines()),'observed':int(sp.check_output([sys.executable,'-c','import ctypes,sys;print(ctypes.CDLL(sys.argv[1]).observed())',so],text=True)),'objects':[[name.split('.')[:-3],hashlib.sha256(sp.check_output(['ar','p',lib,name])).hexdigest()] for name in al if name.endswith('.o')],'full_rmeta':hashlib.sha256(sp.check_output(['ar','p',lib,'lib.rmeta'])).hexdigest()}
 return so,data
def code(v,extra=''):return base.replace('VALUE',str(v))+extra
def exported(name):return f'#[unsafe(export_name="{name}")] extern "C" fn hidden()->i32 {{ 7 }}\n'
stages=[('cold',code(1),'full',1,[]),('body',code(2),'relink',2,[]),('add_export',code(2,exported('first_c')),'full',2,['first_c']),('rename_export',code(2,exported('second_c')),'full',2,['second_c']),('remove_export',code(2),'full',2,[]),('public_api',code(2,'pub const NEW: usize=1;\n'),'full',2,[]),('prior_invocation',code(5,'pub const NEW: usize=1;\n'),'full',5,[]),('transitive',code(6,'pub const NEW: usize=1;\n'),'full',6,[]),('new_native',code(7,'pub const NEW: usize=1;\n#[link(name="m")] unsafe extern "C" {}\n'),'full',7,[]),('remove_native',code(8,'pub const NEW: usize=1;\n'),'full',8,[])]
rows=[]
for name,s,expect,value,exports in stages:
 rec=root/name;leaf.write_text(s)
 if name=='prior_invocation':run(rec/'separate-leaf','leaf')
 if name=='transitive':
  manifest=main/'mid/Cargo.toml';manifest.write_text(manifest.read_text()+'[dependencies]\nleaf={path="../leaf"}\n')
  mid.write_text('pub fn keep()->i32 { if false { leaf::value() } else { 0 } }\n')
 outs,kids=run(rec/'current','bundle');child=[c for c in kids if c['crate']=='bundle'];assert len(child)==1,(name,kids)
 so,current=result(outs);(rec/'current.json').write_text(json.dumps(current,indent=2))
 if (target/'debug/app').exists():
  for exe in target.rglob('out/app-*'):
   if exe.is_file() and os.access(exe,os.X_OK):exe.rename(rec/(exe.name+'.before-candidate'))
 app,c=run(rec/'candidate-downstream','app')
 app_argv,=[k['argv'] for k in c if k['crate']=='app']
 assert not any(k['crate']=='bundle' for k in c) and 'bundle='+str(so.with_suffix('.rlib')) in app_argv,(name,c)
 assert int(sp.check_output([app['app']['executable']],text=True))==value
 # Losing the actual output makes Cargo perform a fresh full mixed-library compile at the same paths.
 so.rename(rec/'candidate.so')
 full,kids=run(rec/'full-reference','bundle');assert any(c['crate']=='bundle' and not c['link_only'] for c in kids),(name,kids)
 _,gold=result(full);(rec/'full.json').write_text(json.dumps(gold,indent=2))
 assert current==gold,(name,current,gold)
 assert gold['exports']==sorted(['observed',*exports]) and gold['observed']==value,(name,gold)
 if (target/'debug/app').exists():
  for exe in target.rglob('out/app-*'):
   if exe.is_file() and os.access(exe,os.X_OK):exe.rename(rec/(exe.name+'.prev'))
 app,_=run(rec/'downstream','app');assert int(sp.check_output([app['app']['executable']],text=True))==value
 modes='relink' if child[0]['link_only'] else 'full'
 h=max(target.rglob('lib-leaf.public-api-hash'),key=lambda p: p.stat().st_mtime_ns);row={'name':name,'expected':expect,'observed':modes,'leaf':json.loads(h.read_text()),'so_sha256':gold['sha256'],'rmeta':gold['rmeta'],'symbols':gold['exports'],'value':value}
 assert modes==expect,(name,modes,expect)
 rows.append(row);(root/'observations.json').write_text(json.dumps(rows,indent=2)+'\n');print(row,flush=True)
