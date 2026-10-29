#!/usr/bin/env python3
"""Rebuild the ordinary Ruff warm/forced native-input discrepancy in a new private copy."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

PIN = '93526150df078af7dd8fc4226cdcc469539d2001'
EDIT = 'a50dc58628691ee00a21809e19bdea71958e4f3c'
NAMES = ('generate_inline_tests', 'fixtures')
FILE = 'crates/ruff_python_parser/src/parser/statement.rs'
SOURCE_RESOURCE = 'crates/ruff_python_parser/resources/inline/err/from_import_parenthesized_star.py'
SNAP = 'crates/ruff_python_parser/tests/snapshots/invalid_syntax@from_import_parenthesized_star.py.snap'

def hashfile(path):
    with path.open('rb') as src:
        return hashlib.file_digest(src, 'sha256').hexdigest()

def command(args):
    return subprocess.check_output([str(x) for x in args])

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for field in ('sdk','ruff_git','cargo_home','empty'):
        p.add_argument(field,type=Path)
    p.add_argument('--expect',choices=['skip','relink'],required=True)
    p.add_argument('--defaults-off',action='store_true')
    p.add_argument('--jobs',type=int,default=4)
    args=p.parse_args()
    s=args.empty.resolve();s.mkdir(parents=True,exist_ok=False)
    assert args.jobs>=1 and shutil.disk_usage(s).free>4*1024**3
    sdk=args.sdk.resolve(strict=True);repo=args.ruff_git.resolve(strict=True)
    git=lambda *a:command(['git','-C',repo,*a])
    src=s/'source';src.mkdir()
    with subprocess.Popen(['git','-C',repo,'archive',PIN],stdout=subprocess.PIPE) as proc:
        with tarfile.open(fileobj=proc.stdout,mode='r|') as archive:
            archive.extractall(src,filter='tar')
        assert proc.wait()==0
    alias=s/'rustup/toolchains';alias.mkdir(parents=True);(alias/'ohm').symlink_to(sdk,target_is_directory=True)
    registry=args.cargo_home.resolve(strict=True)/'registry';assert registry.is_dir()
    for part in ('index','cache'):
        donor=registry/part;assert donor.is_dir();dst=s/'home/registry'/part;dst.parent.mkdir(parents=True,exist_ok=True)
        subprocess.run(['cp','-aL','--reflink=auto',donor,dst],check=True)
    env={k:v for k,v in os.environ.items() if k not in {'RUSTC','RUSTC_WRAPPER','RUSTC_WORKSPACE_WRAPPER','RUSTFLAGS','CARGO_ENCODED_RUSTFLAGS'} and not k.startswith(('CARGO_','RUSTUP_'))}
    env.update(RUSTUP_HOME=str(s/'rustup'),CARGO_HOME=str(s/'home'),CARGO_TARGET_DIR=str(s/'target'),CARGO_BUILD_BUILD_DIR=str(s/'shared'),CARGO_NET_OFFLINE='true',INSTA_UPDATE='no')
    proxy=shutil.which('cargo');assert proxy
    prefix=[proxy,'+ohm']+(['-Zohm-defaults=no'] if args.defaults_off else [])
    start=git('show',f'{PIN}:{FILE}');old=git('show',f'{EDIT}^:{FILE}');new=git('show',f'{EDIT}:{FILE}')
    from difflib import SequenceMatcher
    before=old.splitlines(keepends=True);after=new.splitlines(keepends=True)
    change=[(c,d) for tag,a,b,c,d in SequenceMatcher(a=before,b=after,autojunk=False).get_opcodes() if tag=='insert'];(left,right),=change
    deletion=b''.join(after[left:right]);assert len(deletion.splitlines())==9 and start.count(deletion)==1
    def change_source(edited):
        (src/FILE).write_bytes(start.replace(deletion,b'') if edited else start)
        for item in (SOURCE_RESOURCE,SNAP):
            if edited:(src/item).unlink()
            else:(src/item).write_bytes(git('show',f'{PIN}:{item}'))
    records={}
    def run(label,names):
        d=s/label;d.mkdir()
        argv=prefix+['test','--locked','--offline','--no-run','-j',str(args.jobs),'-p','ruff_python_parser']
        for name in names:argv+=['--test',name]
        argv+=['--message-format=json']
        with (d/'stdout').open('wb') as out,(d/'stderr').open('wb') as er:
            cmd=subprocess.run(argv,cwd=src,env=env,stdout=out,stderr=er)
        rows=[json.loads(line) for line in (d/'stdout').read_bytes().splitlines()]
        dest={x['target']['name']:Path(x['executable']) for x in rows if x.get('executable') and (x['target']['name'] in names)}
        scripted=[x for x in rows if x.get('reason')=='build-script-executed' and x['package_id'].endswith('#psm@0.1.32')]
        for entry in scripted:assert entry['linked_paths']==['native='+entry['out_dir']]
        status={}
        for key,path in dest.items():
            got=subprocess.run([path,'--list'],stdout=subprocess.PIPE,stderr=subprocess.PIPE);(d/(key+'.list')).write_bytes(got.stdout)
            status[key]={'status':got.returncode,'raw_elf_sha256':hashfile(path),'listed':sum(l.endswith(b': test') for l in got.stdout.splitlines())}
        records[label]={'cargo_status':cmd.returncode,'programs':status,'cargo_output_sha256':hashfile(d/'stdout'),'cargo_error_sha256':hashfile(d/'stderr')}
        (s/'observations.json').write_text(json.dumps(records,indent=2,sort_keys=True)+'\n')
        return cmd.returncode,dest,status,scripted
    code,products,stats,scripts=run('01-original',NAMES);assert code==0 and stats[NAMES[0]]['status']==0
    script,=scripts;out=Path(script['out_dir']).resolve(strict=True);assert out.is_relative_to(s) and not out.is_symlink()
    injection=out/'libgcc_s.so';assert not injection.exists() and not injection.is_symlink()
    assembly=Path(__file__).with_name('provider.S');obj=s/'observer.o';subprocess.run(['as','--64',assembly,'-o',obj],check=True)
    gcc=Path(command(['gcc','-print-file-name=libgcc_s.so']).decode().strip()).resolve(strict=True)
    actual=products[NAMES[0]];assert actual.resolve().is_relative_to(s) and not actual.is_symlink()
    good=f'INPUT ( {obj} {gcc} )\n'.encode();bad=b'OHM_REJECT_UNRELATED_NATIVE_PROVIDER (\n'
    try:
        with injection.open('xb') as f:f.write(good)
        change_source(True)
        code,_,status,_=run('02-real-edit-with-provider',NAMES);assert code==0 and status['fixtures']['status']==83
        assert status[NAMES[0]]['status']==(0 if args.expect=='skip' else 83)
        actual.unlink();code,_,status,_=run('03-forced-provider',NAMES[:1]);assert code==0 and status[NAMES[0]]['status']==83
        assert injection.read_bytes()==good;injection.write_bytes(bad);change_source(False)
        code,_,status,_=run('04-real-restore-malformed',NAMES[:1]);assert code==(0 if args.expect=='skip' else 101)
        if code==0:assert status[NAMES[0]]['status']==83
        if actual.exists():actual.unlink()
        code,_,_,_=run('05-forced-malformed',NAMES[:1]);assert code==101 and 'libgcc_s.so' in (s/'05-forced-malformed/stdout').read_text()
        assert injection.read_bytes()==bad;injection.unlink()
        code,_,status,_=run('06-recovered',NAMES[:1]);assert code==0 and status[NAMES[0]]['status']==0 and status[NAMES[0]]['listed']==1
    finally:
        if injection.exists() and injection.read_bytes() in (good,bad):injection.unlink()
    print(json.dumps(records,indent=2,sort_keys=True))
if __name__=='__main__':main()
