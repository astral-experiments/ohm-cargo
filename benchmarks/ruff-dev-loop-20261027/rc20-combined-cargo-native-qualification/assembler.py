#!/usr/bin/env python3
"""Compare assembler input acquisition across matched scheduler/reader settings."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from collections import defaultdict

PACKAGE='assembler_reader'
ORIGINAL=b'#[inline(never)]\npub fn observed(x: u8) -> u8 { x ^ 5 }\n'
PUBLIC=ORIGINAL+b'pub struct AddedByPublicEdit;\n'
PRIVATE=ORIGINAL.replace(b'x ^ 5',b'x ^ 9')
READER=r'''use core::arch::global_asm;
global_asm!(concat!(
    ".pushsection .rodata.ohm_assembly_input,\"a\",@progbits\n",
    ".globl ohm_assembly_input\n",
    ".type ohm_assembly_input,@object\n",
    "ohm_assembly_input:\n",
    ".incbin \"", env!("CARGO_MANIFEST_DIR"), "/payload.bin\"\n",
    ".size ohm_assembly_input,.-ohm_assembly_input\n",
    ".popsection\n"
));
unsafe extern "C" { static ohm_assembly_input: u8; }
#[test]
fn reads_the_assembled_input() {
    let native = unsafe { core::ptr::read_volatile(&raw const ohm_assembly_input) };
    println!("native-value={native},rust-value={}", RUST_VALUE);
}
'''

def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(path,value):path.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
def hashlib_line(s):return hashlib.sha256(s.encode()).hexdigest()

def trace_info(run,asset):
    process=[];readers=[];parents={};tool={};inc=set();target_names=set();dep_inputs={}
    for f in run.glob('trace.*'):
        pid=int(f.name.split('.')[-1])
        for line in f.read_text(errors='replace').splitlines():
            if 'execve(' in line and line.endswith('= 0'):
                m=re.search(r'execve\(("(?:[^"\\]|\\.)*"), (\[.*\]), (?:0x|NULL|\[)',line)
                if m is None:continue
                args=ast.literal_eval(m[2]);exe=Path(ast.literal_eval(m[1]));unit=args[args.index('--crate-name')+1] if '--crate-name' in args else None
                tool[pid]=(exe.name,unit)
                if exe.name=='rustc' and unit in (PACKAGE,'reader'):
                    paths=[str(Path(x.partition('=')[2]).resolve()) for x in args if x.startswith('incremental=')];is_link='-Zlink-only' in args or 'link-only' in args
                    if unit=='reader':
                        if not is_link:inc.update(paths)
                        out=args[args.index('--out-dir')+1] if '--out-dir' in args else None
                        extra=next((x.partition('=')[2] for x in args if x.startswith('extra-filename=')),'')
                        if out and extra:target_names.add(str(Path(out)/('reader'+extra)))
                    process.append({'type':'rustc','unit':unit,'pid':pid,'link_only':is_link,'incremental':bool(paths),'exe':sha(exe),'line':hashlib_line(line)})
                elif exe.name in ('ld','ld.bfd','ld.lld','rust-lld') and '-o' in args and Path(args[args.index('-o')+1]).name.startswith('reader-'):
                    process.append({'type':'linker','pid':pid,'exe':sha(exe),'name':exe.name,'line':hashlib_line(line)})
                continue
            if re.search(r'\b(?:clone3?|vfork|fork)\(|<\.\.\. (?:clone3?|vfork|fork) resumed>',line):
                match=re.search(r'=\s*(\d+)\s*$',line)
                if match:parents[int(match[1])]=pid
            if ('openat(' in line or 'open(' in line or 'openat2(' in line) and str(asset) in line and f'"{asset}"' in line:
                readers.append({'tid':pid,'open_successful':bool(re.search(r'=\s*\d+\s*$',line)),'missing':'ENOENT' in line,'line':hashlib_line(line)})
    for record in readers:
        ancestor=record['tid'];seen=set();ancestry=[]
        while ancestor and ancestor not in seen:
            seen.add(ancestor)
            if ancestor in tool:ancestry.append(tool[ancestor])
            ancestor=parents.get(ancestor)
        record['nearest_compiler']=next((unit for exe,unit in ancestry if exe=='rustc' and unit),'');record['nearest_executable']=ancestry[0][0] if ancestry else ''
    for n in target_names:
        for f in (Path(n+'.d'),):
            if f.is_file():raw=f.read_bytes();dep_inputs[f.name]={'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'mentions_payload':b'payload.bin' in raw,'mentions_reader_source':b'reader.rs' in raw}
    return process,readers,sorted(inc),sorted(target_names),dep_inputs

def one_case(root,sdk,incremental,off,relationship):
    root.mkdir();work=root/'fixture';(work/'src').mkdir(parents=True);(work/'tests').mkdir();(work/'Cargo.toml').write_text('[package]\nname = "assembler_reader"\nversion = "0.0.0"\nedition = "2024"\n');lib=work/'src/lib.rs';lib.write_bytes(ORIGINAL)
    test=work/'tests/reader.rs';test.write_text(READER.replace('RUST_VALUE','assembler_reader::observed(std::hint::black_box(3))' if relationship=='used-private' else '0u8'))
    asset=work/'payload.bin';asset.write_bytes(bytes([17]));home=root/'home';home.mkdir();alias=root/'rustup/toolchains';alias.mkdir(parents=True);(alias/'ohm').symlink_to(sdk,target_is_directory=True)
    env={k:v for k,v in os.environ.items() if not k.startswith(('RUST','CARGO_')) and k not in ('LD_LIBRARY_PATH','LIBRARY_PATH','LD_PRELOAD','GCC_EXEC_PREFIX','COMPILER_PATH')};env.update(RUSTUP_HOME=str(root/'rustup'),CARGO_HOME=str(home),CARGO_NET_OFFLINE='true',CARGO_INCREMENTAL=str(incremental));args=['cargo','+ohm']+(['-Zohm-defaults=no'] if off else [])+['test','--offline','--no-run','-j2','--test','reader','--message-format=json'];results={};known_elf=None;known_inc=set()
    def run(label,state='trained'):
        nonlocal known_elf
        assert shutil.disk_usage(root).free>24*2**30+600*2**20
        wr=root/state;fresh=not wr.exists();e=env|{'CARGO_TARGET_DIR':str(wr/'target'),'CARGO_BUILD_BUILD_DIR':str(wr/'shared')};p=root/label;p.mkdir();cmd=['strace','-ff','-qq','-s','131072','-e','trace=execve,open,openat,openat2,clone,clone3,vfork,fork','-o',str(p/'trace'),*args]
        with (p/'stdout').open('wb') as out,(p/'stderr').open('wb') as err:q=subprocess.run(cmd,cwd=work,env=e,stdout=out,stderr=err)
        records=[json.loads(v) for v in (p/'stdout').read_bytes().splitlines()];arts=[j for j in records if j['reason']=='compiler-artifact'];assert not [j for j in records if j['reason']=='build-script-executed'];process,readers,incrementals,names,depinfo=trace_info(p,asset);desc={n for n in names};proof={'status':q.returncode,'empty':fresh,'phase':label,'expected_incremental':incremental,'source':sha(lib),'asset':sha(asset) if asset.exists() else None,'target_source':sha(test),'processes':process,'asset_opens':readers,'depinfo':depinfo,'compiler_incremental_directories':incrementals,'typed':[(j['target']['name'],j['fresh']) for j in arts],'diagnostic_mentions_incbin':b'payload.bin' in (p/'stdout').read_bytes()+ (p/'stderr').read_bytes(),'raw':{f.name:sha(f) for f in p.iterdir() if f.is_file()}}
        for v in process:
            if v['type']=='rustc' and not v['link_only']:assert v['incremental']==bool(incremental),(label,v)
        if state=='trained':known_inc.update(incrementals)
        if q.returncode==0:
            x,=[Path(j['executable']) for j in arts if j.get('executable') and j['target']['name']=='reader'];assert x.is_file() and not x.is_symlink() and x.resolve().is_relative_to(wr)
            check=subprocess.run([x,'--exact','reads_the_assembled_input','--nocapture'],capture_output=True,env=e,cwd=work);assert check.returncode==0 and b'1 passed' in check.stdout
            (p/'test.stdout').write_bytes(check.stdout);values,=re.findall(rb'native-value=(\d+),rust-value=(\d+)',check.stdout);proof['native'],proof['rust']=map(int,values);proof['elf']=sha(x);proof['test_stdout_sha']=hashlib.sha256(check.stdout).hexdigest();rd=x.with_name(x.name+'.rlink-cache.json');proof['manifest']=sha(rd) if rd.is_file() else None;proof['unused']=json.loads(rd.read_bytes()).get('unused_extern_names') if rd.is_file() else None
            if state=='trained':known_elf=x
        put(p/'result.json',proof);results[label]=proof;print(root.name,label,proof['status'],proof.get('native'),proof.get('rust'),[(v.get('unit'),v.get('link_only')) for v in process if v.get('unit')=='reader'],sum(v['type']=='linker' for v in process),[(v['nearest_compiler'],v['open_successful'],v['missing']) for v in readers],flush=True);return proof
    def evict(name,inc=False):
        assert known_elf is not None and known_elf.resolve().is_relative_to(root/'trained');held=root/'retained'/name;held.mkdir(parents=True);items={}
        for suffix in ('','.rlink','.rlink-cache.json'):
            p=known_elf.with_name(known_elf.name+suffix)
            if p.exists():assert p.is_file() and not p.is_symlink();items[p.name]=sha(p);p.rename(held/p.name)
        if inc:
            for i,p in enumerate(sorted(map(Path,known_inc))):
                assert p.resolve().is_relative_to(root/'trained') and p!=root/'trained' and not p.is_symlink()
                if p.is_dir():p.rename(held/('test-incremental-'+str(i)));items['incremental-'+str(i)]=str(p.relative_to(root/'trained'))
        put(held/'receipt.json',items)
    initial=run('01-cold');assert initial['native']==17 and initial['rust']==(6 if relationship=='used-private' else 0) and any(a['nearest_compiler']=='reader' and a['open_successful'] for a in initial['asset_opens'])
    no=run('02-unchanged');assert no['native']==17 and not no['processes']
    lib.write_bytes(PRIVATE if relationship=='used-private' else PUBLIC);asset.write_bytes(bytes([29]));edit=run('03-edit-and-new-asset');assert edit['status']==0 and edit['native'] in (17,29) and edit['rust']==(10 if relationship=='used-private' else 0)
    clean=run('04-independent-clean','empty-good');assert clean['native']==29 and clean['empty'] and clean['rust']==edit['rust'] and any(a['open_successful'] and a['nearest_compiler']=='reader' for a in clean['asset_opens'])
    evict('retained-edit');forced=run('05-forced-full-keep-incremental');assert forced['status']==0 and forced['native'] in (17,29) and any(v.get('unit')=='reader' and not v['link_only'] for v in forced['processes'])
    if incremental:
        evict('drop-reader-incremental',inc=True);fresh_obj=run('06-forced-full-evacuated-incremental');assert fresh_obj['native']==29 and any(a['open_successful'] and a['nearest_compiler']=='reader' for a in fresh_obj['asset_opens'])
    else:assert forced['native']==29
    lib.write_bytes(ORIGINAL);asset.unlink();invalid=run('07-source-restore-missing-asset');assert invalid['status'] in (0,101)
    invalid_ref=run('08-independent-missing','empty-bad');assert invalid_ref['status']==101 and invalid_ref['diagnostic_mentions_incbin'] and any(a['missing'] and a['nearest_compiler']=='reader' for a in invalid_ref['asset_opens'])
    evict('retained-missing',inc=True);same=run('09-forced-same-missing');assert same['status']==101 and same['diagnostic_mentions_incbin']
    asset.write_bytes(bytes([17]));recover=run('10-recovered');assert recover['native']==17 and recover['rust']==initial['rust']
    put(root/'terminal.json',{'relationship':relationship,'incremental':incremental,'defaults_off':off,'cargo':sha(sdk/'bin/cargo'),'rustc':sha(sdk/'bin/rustc'),'holds':{d.parent.name:sha(d) for d in sorted((root/'retained').glob('*/receipt.json'))},'phases':{name:sha(root/name/'result.json') for name in results}})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('sdk',type=Path);p.add_argument('empty',type=Path);p.add_argument('--incremental',type=int,choices=[0,1],required=True);p.add_argument('--defaults-off',action='store_true');p.add_argument('--relationship',choices=['unused-public','used-private'],required=True);a=p.parse_args();one_case(a.empty.resolve(),a.sdk.resolve(strict=True),a.incremental,a.defaults_off,a.relationship)
