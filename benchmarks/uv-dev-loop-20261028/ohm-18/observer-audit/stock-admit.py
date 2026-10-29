"""Cheap stock-only stop gates before attempting any wrapper-free process-tree count."""
import argparse
import ast
import collections
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import traceback

here=Path(__file__).resolve().parent;work=here.parent.parent;bench=Path((work/'bench-home.path').read_text().strip());release=work/'upstream-monitor/toolchain18';observer=here.parent/'resolver-bare-edited/external-exec/observe.py';spec=importlib.util.spec_from_file_location('kernel_grammar',observer);grammar=importlib.util.module_from_spec(spec);spec.loader.exec_module(grammar)
root=bench/'wrapper-free-stock-admission';out=here/'stock-results';src=root/'source';target=root/'target';home=root/'cargo-home';stock=release/'bin/cargo';rustc=str(release/'bin/rustc');crate='heck-0.5.0';checksum='2304e00983f87ffb38b55b444b5e3b60a884b5d30c0fca7d82fe33449bbe55ea'
def save(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def env():return dict(PATH=str(release/'bin')+':/usr/bin:/bin',HOME=str(root/'env-home'),PWD=str(src),CARGO_HOME=str(home),CARGO_TARGET_DIR=str(target),RUSTC=rustc,RUSTDOC=str(release/'bin/rustdoc'),CARGO_NET_OFFLINE='true',CARGO_TERM_COLOR='never',TZ='UTC',LC_ALL='C.UTF-8',SSL_CERT_FILE='/etc/ssl/certs/ca-certificates.crt',VALGRIND_LIB=str(work/'profiler/usr/libexec/valgrind'))
def prefix(mode,d):
    if mode=='native':return []
    if mode=='perf':return ['/usr/bin/perf','stat','--no-big-num','-x',';','-e','instructions:u','-o',str(d/'perf.stat'),'--']
    if mode=='dynamorio':return [str(work/'dynamorio/DynamoRIO-Linux-11.3.0-1/bin64/drrun'),'-follow_children','-t','drcachesim','-offline','-raw_compress','none','-outdir',str(d),'-L0I_filter','-L0I_size','0','-L0D_filter','-L0D_size','0','--']
    assert mode=='cachegrind';return [str(work/'profiler/usr/bin/valgrind'),'--tool=cachegrind','--trace-children=yes','--cachegrind-out-file='+str(d/'cachegrind.%p')]
def app_env(mode):
    d=out/('env-'+mode);d.mkdir();cmd=[*prefix(mode,d),'/usr/bin/env','-0']
    with (d/'stderr.log').open('xb') as f:p=subprocess.run(cmd,cwd=src,env=env(),stdout=subprocess.PIPE,stderr=f)
    values=dict(s.decode().split('=',1) for s in p.stdout.split(b'\0') if s);changed={k:[env().get(k),values.get(k)] for k in sorted(set(values)|set(env())) if env().get(k)!=values.get(k)};save(d/'app-env.json',values)
    result=dict(returncode=p.returncode,changed=changed,eligible=p.returncode==0 and not changed,command=cmd);save(d/'receipt.json',result);return result
def checkout():
    reg=bench/'cargo/registry';files=list((reg/'cache').glob('*/'+crate+'.crate'));assert len(files)==1 and sha(files[0])==checksum;name=files[0].parent.name
    for f in (files[0],reg/'index'/name/'config.json',reg/'index'/name/'.cache/he/ck/heck'):
        dst=home/'registry'/f.relative_to(reg);dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,dst)
    (src/'src').mkdir();(src/'Cargo.toml').write_text('[package]\nname = "ordinary-reuse-control"\nversion = "0.1.0"\nedition = "2021"\n[dependencies]\nheck = "=0.5.0"\n');f=src/'src/lib.rs';f.write_text('use heck::ToKebabCase;\nfn body(s: &str) -> String { format!("A{}", s.to_kebab_case()) }\npub fn run(s: &str) -> String { body(s) }\n')
    for label,args in [('lock',['generate-lockfile','--offline']),('build',['build','--locked','--offline','-j2'])]:
        with (out/(label+'.log')).open('x') as log:subprocess.run([str(stock),*args],cwd=src,env=env(),stdout=log,stderr=subprocess.STDOUT,check=True)
    assert (target/'.ohm-built-registry-ready').is_file();target.rename(root/'seed-target');mutable=root/'seed-home';mutable.mkdir()
    for f in home.iterdir():
        if f.name!='registry':subprocess.run(['cp','-a',str(f),str(mutable/f.name)],check=True)
    f=src/'src/lib.rs';f.write_text(f.read_text().replace('A{}','B{}'));w=root/'negative-compiler-wrapper';w.write_text('#!/bin/sh\nexec "$@"\n');w.chmod(0o500)
def stock_check(label,mode,wrapped=False):
    d=out/label;d.mkdir();assert not target.exists();shutil.copytree(root/'seed-target',target,symlinks=True,copy_function=shutil.copy2)
    for f in home.iterdir():
        if f.name!='registry':(shutil.rmtree(f) if f.is_dir() else f.unlink())
    for f in (root/'seed-home').iterdir():subprocess.run(['cp','-a',str(f),str(home/f.name)],check=True)
    en=env()
    if wrapped:en['RUSTC_WRAPPER']=str(root/'negative-compiler-wrapper')
    cmd=['/usr/bin/strace','-ff','-qq','-v','-s','1048576','-e','trace=execve,execveat','-o',str(d/'exec'),*prefix(mode,d),str(stock),'check','--locked','--offline','-j2']
    with (d/'cargo.log').open('x') as f:p=subprocess.run(cmd,cwd=src,env=en,stdout=f,stderr=subprocess.STDOUT)
    assert p.returncode==0,d;log=(d/'cargo.log').read_text();assert re.search(r'^\s*Finished ',log,re.M) and not re.search(r'^\s*(Running|Blocking|Updating|Downloading) ',log,re.M)
    apps=[];compiler=[]
    for f in d.glob('exec.*'):
        for line in f.read_text().splitlines():
            if not line.startswith(('execve(','execveat(')) or not line.endswith('= 0'):continue
            m=grammar.call.match(line) or grammar.at.match(line);assert m and m[1]!='""';program,argv,raw=(ast.literal_eval(v) for v in m.groups());apps.append([program,argv]);variables=dict(s.split('=',1) for s in raw)
            if program==rustc and '--crate-name' in argv:compiler.append(dict(argv=argv,environment=variables))
    compiler.sort(key=lambda r:r['argv']);packages=sorted(re.findall(r'^\s*(?:Checking|Compiling) (\S+) v',log,re.M));assert packages==(['heck','ordinary-reuse-control'] if wrapped else ['ordinary-reuse-control']),packages
    assert sorted(c['argv'][c['argv'].index('--crate-name')+1] for c in compiler)==(['heck','ordinary_reuse_control'] if wrapped else ['ordinary_reuse_control'])
    assert any(a.startswith('heck=') for c in compiler for a in c['argv']);products={str(f.relative_to(target)):sha(f) for f in target.rglob('*.rmeta') if 'incremental' not in f.relative_to(target).parts};assert products and (target/'.ohm-built-registry-ready').is_file()
    result=dict(compilers=compiler,packages=packages,public_metadata=products,ready_marker=True,source_sha256=sha(src/'src/lib.rs'),lock_sha256=sha(src/'Cargo.lock'));save(d/'workload.json',result);save(d/'exec-programs.json',apps);target.rename(root/('excluded-target-'+label));return result
def main():
    p=argparse.ArgumentParser();p.add_argument('--counter-window-released',action='store_true',required=True);p.parse_args();assert not (here.parent/'edited-roles/control/pause').exists();assert sorted(os.sched_getaffinity(0))==list(range(8,16));assert not root.exists() and not out.exists();root.mkdir(mode=0o700);out.mkdir();src.mkdir();home.mkdir(mode=0o700);(root/'env-home').mkdir(mode=0o700)
    freeze=json.loads((here/'registered.json').read_text());assert all(sha(here/k)==v for k,v in freeze['scripts'].items()) and sha(observer)==freeze['parser_sha256'];save(out/'programs.json',dict(cargo=sha(stock),rustc=sha(Path(rustc)),registration=sha(here/'registered.json'),affinity=sorted(os.sched_getaffinity(0)),start_ns=time.time_ns()))
    native=app_env('native');assert native['eligible'];results={m:app_env(m) for m in ('perf','dynamorio','cachegrind')};eligible=[m for m,r in results.items() if r['eligible']]
    if eligible:
        checkout();gold=stock_check('native-positive','native');stock_check('native-negative','native',True)
        for m in eligible:
            try:
                actual=stock_check('counted-'+m,m);changed=[k for k in gold if gold[k]!=actual[k]];results[m].update(stock_control_passed=not changed,differing_workload_fields=changed)
            except Exception as e:results[m].update(stock_control_passed=False,exclusion=str(e),traceback=traceback.format_exc())
    save(out/'summary.json',dict(observers=results,eligible_for_lifecycle_calibration=[m for m,r in results.items() if r.get('stock_control_passed')],treated_observations=0));print((out/'summary.json').read_text())
if __name__=='__main__':main()
