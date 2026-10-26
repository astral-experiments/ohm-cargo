#!/usr/bin/env python3
"""Check the historical RDR candidate against independently built clean cross-crate consumers."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess


def invoke(cwd,env,mode,target,expected_error,tag):
    args=['bwrap','--ro-bind','/','/','--dev','/dev','--proc','/proc','--tmpfs','/tmp','--bind',cwd.parent,cwd.parent,'--ro-bind',env['ACTUAL_CARGO'],Path(env['OHM_SYSROOT'])/'bin/cargo','--chdir',cwd,'--',shutil.which('cargo'),'+ohm',mode,'--offline','--message-format=json']
    p=subprocess.run(args,env=env,capture_output=True)
    rows=[json.loads(line) for line in p.stdout.splitlines()]
    diagnostics=[r['message'] for r in rows if r['reason']=='compiler-message']
    codes={d['code']['code'] for d in diagnostics if d['code'] and d['level']=='error'}
    assert (p.returncode==0)==(expected_error is None) and (not expected_error or expected_error in codes),(cwd,tag,expected_error,codes,p.stderr[-2000:])
    elf=run_output=None
    if mode=='build' and not expected_error:
        exe=next(Path(r['executable']) for r in rows if r['reason']=='compiler-artifact' and r['target']['name']=='consumer')
        elf=hashlib.sha256(exe.read_bytes()).hexdigest();run_output=subprocess.check_output([exe],text=True).strip()
        assert run_output==('1' if tag=='base' else '2')
    return {'diagnostics':[{k:v for k,v in d.items() if k!='rendered'} for d in diagnostics],'executable_sha256':elf,'stdout':run_output,'aggregate_public_hashes':{str(q.relative_to(target)):q.read_text().strip() for q in target.rglob('*.public-api-hash')}}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['sysroot','cargo','control','treatment','state']:p.add_argument('--'+name,required=True,type=Path)
    a=p.parse_args();state=a.state.resolve();assert not state.exists();state.mkdir(parents=True)
    rt=a.sysroot.resolve(strict=True);cargo=a.cargo.resolve(strict=True);A=a.control.resolve(strict=True);B=a.treatment.resolve(strict=True)
    rustup=state/'rustup';(rustup/'toolchains').mkdir(parents=True);(rustup/'toolchains/ohm').symlink_to(rt);(rustup/'settings.toml').write_text('version = "12"\nprofile = "minimal"\n')
    rows=json.loads((Path(__file__).resolve().parent/'language-and-elf.json').read_text())['visibility_cases'];assert len(rows)==24
    wrap=state/'wrapper';wrap.write_text('''#!/bin/sh
case " $* " in *" --crate-name "*)
  dir="$CONTROL"
  case " $* " in *" --crate-name upstream "*) dir="$SUBJECT";; esac
  export LD_LIBRARY_PATH="$dir:$OHM_SYSROOT/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
  set -- "$@" --sysroot "$OHM_SYSROOT";;
esac
exec "$@"
''');wrap.chmod(0o755)
    for arm,driver in [('A',A),('B',B)]:
        for r in rows:
            case=state/arm/r['name'];cwd=case/'workspace';target=case/'store';target.mkdir(parents=True);(case/'cargo-home').mkdir();cwd.mkdir()
            (cwd/'Cargo.toml').write_text('[workspace]\nmembers=["contract","upstream","consumer"]\nresolver="3"\n')
            for package,deps,srcname,contents in [('contract',[],'lib',r['contract']),('upstream',['contract'],'lib',r['upstream_before']),('consumer',['contract','upstream'],'main',r['consumer'])]:
                d=cwd/package;(d/'src').mkdir(parents=True);(d/'src'/(srcname+'.rs')).write_text(contents)
                (d/'Cargo.toml').write_text(f'[package]\nname="{package}"\nversion="0.1.0"\nedition="2024"\n[dependencies]\n'+''.join(f'{dep}={{path="../{dep}"}}\n' for dep in deps))
            env=dict(os.environ,RUSTUP_HOME=str(rustup),RUSTUP_TOOLCHAIN='ohm',CARGO_HOME=str(case/'cargo-home'),CARGO_TARGET_DIR=str(target/'target'),CARGO_BUILD_BUILD_DIR=str(target/'shared'),CARGO_BUILD_JOBS='2',RUSTFLAGS='-Zincremental-verify-ich=yes',RUSTC=str(rt/'bin/rustc'),RUSTC_WRAPPER=str(wrap),OHM_SYSROOT=str(rt),ACTUAL_CARGO=str(cargo),CONTROL=str(A.parent),SUBJECT=str(driver.parent),CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST='all',CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST='all');invoke(cwd,env,r['mode'],target,None,'base');(cwd/'upstream/src/lib.rs').write_text(r['upstream_after']);warm=invoke(cwd,env,r['mode'],target,r['expected_error'],'edited');target.rename(case/'retired');target.mkdir();cold=invoke(cwd,env,r['mode'],target,r['expected_error'],'clean')
            assert warm['diagnostics']==cold['diagnostics'] and warm['executable_sha256']==cold['executable_sha256'] and warm['stdout']==cold['stdout'],(arm,r['name'])
            if not r['expected_error']:assert warm['aggregate_public_hashes']==cold['aggregate_public_hashes']
            (case/'outcomes.json').write_text(json.dumps({'warm':warm,'cold':cold},indent=2)+'\n');print(arm,r['name'],flush=True)

if __name__=='__main__':main()
