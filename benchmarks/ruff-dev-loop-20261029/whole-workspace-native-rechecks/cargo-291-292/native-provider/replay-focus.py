#!/usr/bin/env python3
"""Reproduce the 300-unit historical source and native-search checks with a caller-supplied Linux Ohm SDK."""
import argparse
import collections
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
import tomllib
import importlib.util

HERE=Path(__file__).resolve().parent
BASE='93526150df078af7dd8fc4226cdcc469539d2001'
LOCK='c9e345325bec5ff08dbbe3916edd39ad0c3d1c7797a8c241ae32f62754e764bf'
ORACLE='76d24b892727ff181fdf019636ef5e928d741eb8df4f58f06dcc626d0bf67c52'
TESTS=('inlay_hints::default_inlay_hints','notebook::hover_past_end_of_cell','notebook::inlay_hints_range_past_end_of_cell')
ORDER=(('original','original','absent',False),('edited','edited','absent',False),('unchanged','edited','absent',False),('invalid','invalid','absent',False),('recovery','edited','absent',False),('restored','original','absent',False),('provider','original','valid',False),('forced-provider','original','valid',True),('malformed','original','malformed',False),('remove','original','absent',False),('forced-malformed','original','malformed',True),('final-remove','original','absent',False))
CARGO=['cargo','+ohm','test','--locked','--offline','--no-run','-j4','-p','ty_server','--test','e2e','--message-format=json']
def load_module(name):
    spec=importlib.util.spec_from_file_location(name,HERE/(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(p,v):
    with p.open('x') as f:json.dump(v,f,indent=2,sort_keys=True);f.write('\n')
def get(p):return json.loads(p.read_bytes())
def native(tr,rustc,wild):
    proc,commit,total,resumed=load_module('trace_exec').collect_execs(tr)
    role=load_module('native_role').role
    full=[];cached=[];links=[];queries=0
    for (path,args),n in proc.items():
        exe=Path(path)
        if not exe.is_absolute() or not exe.is_file():continue
        if exe.samefile(rustc):
            enabled,_,_=role(args)
            flag='--crate-name'
            if not enabled and (flag not in args or any(x=='--print' or x.startswith('--print=') for x in args) and not any(x=='--emit' or x.startswith('--emit=') for x in args)):
                queries+=n;continue
            (cached if enabled else full).extend([args[args.index(flag)+1]]*n)
        elif exe.samefile(wild):links.extend([args]*n)
    return {'full':full,'cached':cached,'probes':queries,'wild':len(links),'raw_commitment':commit,'raw_pid_files':total,'resumed':resumed},links
def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for n in ('ruff','registry','sdk','cargo','work'):ap.add_argument('--'+n,type=Path,required=True)
    ap.add_argument('--cpus',required=True,help='Four available logical CPU IDs, for example 0,1,2,3')
    ap.add_argument('--min-free-gib',default=8,type=int);ap.add_argument('--min-memory-gib',default=4,type=int)
    a=ap.parse_args();work=a.work.absolute();cpus={int(x) for x in a.cpus.split(',')};free=a.min_free_gib*2**30;memory=a.min_memory_gib*2**30
    def mem():
        return int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:')))*1024
    if os.uname().sysname!='Linux' or os.uname().machine!='x86_64' or os.geteuid()==0 or work.exists() or len(cpus)!=4 or not cpus<=os.sched_getaffinity(0) or not work.parent.is_dir() or free<1 or memory<1 or mem()<=memory+8*2**30 or shutil.disk_usage(work.parent).free<=free+18*2**30:
        ap.error('Use an ordinary Linux x86-64 account, four usable CPUs and a new work path with 18 GiB and 8 GiB above the disk and memory floors')
    assert all(shutil.which(k) for k in ['rustup','cc','strace','git']);os.sched_setaffinity(0,cpus)
    work.mkdir(mode=0o700);view=work/'view';view.mkdir();src=view/'source';sdk=view/'sdk';reports=work/'observations';reports.mkdir()
    proxy=Path(shutil.which('rustup')).absolute().parent
    subprocess.run(['git','clone','--quiet','--no-checkout','--local',a.ruff.resolve(strict=True),src],check=True)
    subprocess.run(['git','-C',src,'checkout','--quiet','--detach',BASE],check=True)
    assert sha(src/'Cargo.lock')==LOCK and subprocess.check_output(['git','-C',src,'rev-parse','HEAD^{tree}'],text=True).strip()=='62d3f106c5e41f6022847f26ff8c7dc00139f7b1'
    source=get(HERE/'source.json');subject=src/source['sole_historical_git_path'];subjects={k:(HERE/(k+'.rs')).read_bytes() for k in ('original','edited','invalid')}
    assert {k:hashlib.sha256(v).hexdigest() for k,v in subjects.items()}==source['source_sha256'] and subject.read_bytes()==subjects['original']
    shutil.copytree(a.sdk.resolve(strict=True),sdk,symlinks=True);assert not (sdk/'bin').is_symlink();tmpcargo=sdk/'bin/cargo.private-new';assert not tmpcargo.exists()
    shutil.copyfile(a.cargo.resolve(strict=True),tmpcargo);tmpcargo.chmod(0o755);os.replace(tmpcargo,sdk/'bin/cargo')
    rustc=sdk/'bin/rustc';wild=sdk/'lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd';assert rustc.is_file() and wild.is_file();versions={}
    for nm in ('home','tmp','target','shared','cargo-home','rustup'): (view/nm).mkdir(mode=0o700)
    (view/'rustup/toolchains').mkdir();(view/'rustup/toolchains/ohm').symlink_to(sdk)
    reg=a.registry.resolve(strict=True);ch=view/'cargo-home/registry';ch.mkdir();shutil.copytree(reg/'index',ch/'index',symlinks=False);(ch/'cache').mkdir();(ch/'src').mkdir()
    wanted={p['name']+'-'+p['version']+'.crate':p['checksum'] for p in tomllib.loads((src/'Cargo.lock').read_text())['package'] if 'checksum' in p};assert len(wanted)==498
    for idx in sorted((ch/'index').iterdir()):
        if not idx.is_dir():continue
        dr=ch/'cache'/idx.name;dr.mkdir()
        for n,dig in wanted.items():
            f=next((f for f in (reg/'cache').glob('*/'+n) if f.is_file() and sha(f)==dig),None);assert f,n;shutil.copyfile(f,dr/n)
    env={'HOME':str(view/'home'),'TMPDIR':str(view/'tmp'),'RUSTUP_HOME':str(view/'rustup'),'CARGO_HOME':str(view/'cargo-home'),'CARGO_TARGET_DIR':str(view/'target'),'CARGO_BUILD_BUILD_DIR':str(view/'shared'),'CARGO_NET_OFFLINE':'true','RUSTUP_AUTO_INSTALL':'0','LC_ALL':'C','LANG':'C','INSTA_UPDATE':'no','PATH':str(proxy)+':/usr/local/bin:/usr/bin:/bin'}
    def execute(d,tag,args,expected,cwd=src,extra=None):
        with (d/(tag+'.stdout')).open('xb') as o,(d/(tag+'.stderr')).open('xb') as e:
            p=subprocess.Popen(args,cwd=cwd,env={**env,**(extra or {})},stdout=o,stderr=e,start_new_session=True)
            try:
                start=time.monotonic()
                while p.poll() is None:
                    if mem()<=memory or shutil.disk_usage(work).free<=free or time.monotonic()-start>4200:raise RuntimeError('resource or duration guard')
                    time.sleep(.4)
            finally:
                if p.poll() is None:
                    os.killpg(p.pid,signal.SIGTERM)
                    try:p.wait(10)
                    except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
        save(d/(tag+'.exit.json'),{'expected':expected,'exit':p.returncode,'args':[str(x) for x in args]})
        assert p.returncode==expected,(tag,p.returncode,expected)
        return (d/(tag+'.stdout')).read_bytes()
    for tool,p in [('cargo',sdk/'bin/cargo'),('rustc',rustc)]:
        assert Path(subprocess.check_output(['rustup','which','--toolchain','ohm',tool],env=env,text=True).strip()).samefile(p)
        versions[tool]=execute(reports,tool+'-version',[tool,'+ohm','-Vv'],0).decode()
    assert any(ref in versions['cargo'] for ref in ('84af87848a5a952ba61ae6a2cc5b22da24130200','98d431a99779ccfbcfe42dfa74dd541de3a92d05'))
    st=Path(subprocess.check_output(['cc','-print-file-name=libgcc_s.so'],env=env,text=True).strip())
    if not st.is_absolute() or not st.is_file() or b'libgcc_s.so.1' not in st.read_bytes():raise ValueError('requires the Linux GNU multilib linker script')
    stock=sha(st);hook=view/'tmp/provider.o';execute(reports,'assemble',['cc','-c',HERE/'provider.s','-o',hook],0)
    assert not any(chpath.isspace() for chpath in str(hook)+str(st)), 'Use a work path without shell or linker-script whitespace'
    valid=('INPUT ( '+str(hook)+' '+str(st)+' )\n').encode();bad=b'OHM_REJECT_BAD_WORKSPACE_TEST_LINK_SCRIPT (\n';slot=None;exe=None;gold={};seen={};ident='ty_server'
    save(reports/'tools.json',{'cargo':sha(sdk/'bin/cargo'),'wild':sha(wild),'rustc':sha(rustc),'driver':{p.name:sha(p) for p in (sdk/'lib').glob('librustc_driver-*.so')},'versions':versions,'stock_script':stock,'Ruff':BASE})
    def write_subject(variant):
        if subject.read_bytes()!=subjects[variant]:subject.write_bytes(subjects[variant])
    def set_provider(data):
        nonlocal slot
        if slot is None:assert data=='absent';return
        assert slot.resolve(strict=False).is_relative_to(view/'target') or slot.resolve(strict=False).is_relative_to(view/'shared')
        if os.path.lexists(slot):
            assert slot.is_file() and not slot.is_symlink() and slot.read_bytes() in (valid,bad);slot.unlink()
        if data!='absent':
            with slot.open('xb') as f:f.write(valid if data=='valid' else bad)
    def visit(name,variant,provider,force):
        nonlocal slot,exe
        write_subject(variant);set_provider(provider);d=reports/name;d.mkdir(mode=0o700);tr=d/'trace';tr.mkdir()
        if force:
            assert exe and exe.is_file() and not exe.is_symlink() and exe.is_relative_to(view/'target')
            shutil.copyfile(exe,d/'prior.elf');assert sha(exe)==sha(d/'prior.elf');exe.unlink()
        expect=101 if provider=='malformed' or variant=='invalid' else 0
        observed=name in ('provider','malformed')
        syscalls='execve,execveat,exit_group'+(',clone,clone3,openat' if observed else '')
        stdout=execute(d,'cargo',['strace','-ff','-qq','-s','524288','-e','trace='+syscalls,'-o',tr/'exec',*CARGO],expect)
        rows=[json.loads(row) for row in stdout.splitlines()];assert rows[-1]=={'reason':'build-finished','success':not expect}
        physical,links=native(tr,rustc,wild);arts=[a for a in rows if a['reason']=='compiler-artifact'];info={'source':variant,'cargo':expect,'provider':provider,'physical':physical,'typed':len(arts),'fresh':sum(x['fresh'] for x in arts)}
        if observed:
            # Identify stock Wild via its successful exec, then join returned open fds across its actual workers.
            class SingleThread:
                def __init__(self,path):self.path=path
                def glob(self,_):return (self.path,)
            parser=load_module('trace_exec');seeds=[]
            for thread in tr.glob('exec.*'):
                ev,*_=parser.collect_execs(SingleThread(thread))
                if any(Path(path).is_file() and Path(path).samefile(wild) for path,_ in ev):
                    seeds.append(int(thread.suffix[1:]))
            counts=load_module('reopen-292-controls').scan_live_opens(tr,seeds,str(slot),str(hook))
            assert counts['script']>0 and bool(counts['object'])==(provider=='valid')
            info['actual_stock_Wild_successful_file_opens']=dict(counts)
        if expect:
            if variant=='invalid':
                assert any((m.get('message',{}).get('code') or {}).get('code')=='E0308' and any(z['is_primary'] and z['line_start']==22 for z in m['message']['spans']) for m in rows if m['reason']=='compiler-message')
            else:assert links and b'OHM_REJECT_BAD_WORKSPACE_TEST_LINK_SCRIPT' in stdout+(d/'cargo.stderr').read_bytes()
        else:
            assert len(arts)==300
            x,=[x for x in arts if x.get('executable') and x['target']['name']=='e2e' and Path(x['manifest_path']).parent.name==ident]
            exe=Path(x['executable']);assert exe.is_relative_to(view/'target') and not exe.is_symlink()
            targets=[a for a in links if a[a.index('-o')+1]==str(exe) or (Path(a[a.index('-o')+1]).is_file() and exe.samefile(a[a.index('-o')+1]))]
            assert len(targets)==1
            options=targets[0];pos,=[i for i,a in enumerate(options) if a.startswith('-L') and 'psm' in Path(a[2:]).parts and Path(a[2:]).name=='out'];assert pos<options.index('-lgcc_s')
            new=Path(options[pos][2:])/'libgcc_s.so';assert new.is_relative_to(view/'target') or new.is_relative_to(view/'shared')
            if slot is None:slot=new;assert not os.path.lexists(slot)
            else:assert slot==new
            extra={'CARGO_MANIFEST_DIR':str(Path(x['manifest_path']).parent),'CARGO_MANIFEST_PATH':x['manifest_path']};pkg=Path(x['manifest_path']).parent
            listing=execute(d,'list',[exe,'--list'],83 if provider=='valid' else 0,pkg,extra)
            info['ELF']=sha(exe);info['list']=hashlib.sha256(listing).hexdigest()
            if provider=='valid':assert not listing
            else:
                assert info['list']==ORACLE and sum(t.endswith(b': test') for t in listing.splitlines())==200
                for ix,test in enumerate(TESTS):
                    body=execute(d,'case-'+str(ix),[exe,'--exact',test],0,pkg,extra);assert ('test '+test+' ... ok').encode() in body and b'199 filtered out' in body
                stable=gold.setdefault(variant,info['ELF']);assert info['ELF']==stable
                def metadata(crate):
                    paths={Path(f) for unit in arts if unit['target']['name']==crate and unit['target']['kind']==['lib'] for f in unit['filenames'] if f.endswith('.rmeta')}
                    result,=paths;return result
                parser,db=metadata('ruff_python_parser'),metadata('ruff_db')
                folders=sorted({str(Path(f).parent) for unit in arts for f in unit['filenames'] if Path(f).suffix in ('.so','.rlib','.rmeta')})
                reader=d/'coherent.rmeta'
                execute(d,'coherent',['rustc','+ohm','--edition=2024','--crate-name','root_source_coherent','--crate-type','rlib','--emit','metadata',HERE/'coherent-consumer.rs','--extern','ruff_python_parser='+str(parser),'--extern','ruff_db='+str(db),*(v for folder in folders for v in ('-L','dependency='+folder)),'-o',reader],0)
                assert reader.is_file() and reader.stat().st_size
                info['actual_same_generation_reader']={'parser':sha(parser),'db':sha(db),'result':sha(reader)}
            if name in ('original','edited','provider','independent-edited'):
                shutil.copyfile(exe,d/'product.elf');assert sha(d/'product.elf')==info['ELF']
        save(d/'result.json',info);seen[name]=info;print(name,info['typed'],len(physical['full']),len(physical['cached']),physical['wild'],expect,flush=True)
    try:
        for spec in ORDER:visit(*spec)
        assert gold['original']!=gold['edited'] and seen['forced-provider']['ELF']==seen['provider']['ELF']!=gold['original']
        # Recreate every target, shared cache and previously extracted dependency source independently at the same literal roots.
        cold=work/'retained-warm';cold.mkdir()
        for p in [view/'target',view/'shared',ch/'src',view/'tmp']:
            name='registry-src' if p==ch/'src' else p.name;os.rename(p,cold/name);p.mkdir(mode=0o700)
        slot=None;exe=None;visit('independent-edited','edited','absent',False)
        assert seen['independent-edited']['fresh']==0 and seen['independent-edited']['ELF']==seen['edited']['ELF']
        subprocess.run(['cmp','-s',reports/'edited/product.elf',reports/'independent-edited/product.elf'],check=True)
        assert sha(st)==stock;save(work/'terminal.json',seen)
    finally:
        write_subject('original')
        if slot is not None and slot.exists():set_provider('absent')
if __name__=='__main__':main()

