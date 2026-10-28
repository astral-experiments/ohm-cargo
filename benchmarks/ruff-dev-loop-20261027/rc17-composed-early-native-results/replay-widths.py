"""Replay captured cached-link rustc commands in a private namespace and run real stock Wild widths."""
import collections
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import socket
import stat
import subprocess
import sys
import traceback

HERE=Path(__file__).resolve().parent
BASE=Path('/mnt/devbox-scratch/dev-user/ohm-combined-prs-20261028')
STORE=BASE/'wall-native-proofs'
assert HERE==STORE/'width-v2' and socket.gethostname()=='charlie-ohm-c5-check-1025'
W=BASE/'ruff-evaluation-v2'; K=BASE/'protocol-v3'; WDIG='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'
WIDTHS=[1,8,2,4,16,3,5,6,7,9,10,11,12,13,14,15]
HISTORICAL={'document','ty_python_semantic','e2e','fixtures','ruff_db','simple_tokenizer'}


def sha(f):
    with f.open('rb') as inp:return hashlib.file_digest(inp,'sha256').hexdigest()


def digest(o):
    return hashlib.sha256(json.dumps(o,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def read(f):return json.loads(f.read_bytes())


def write(f,o):
    temp=f.with_suffix('.pending')
    with temp.open('x') as out:json.dump(o,out,separators=(',',':'),sort_keys=True)
    os.replace(temp,f)


def shim():
    args=sys.argv[2:];cube=Path(os.environ['CAPTURE_HERE']);stock=HERE/'stock-wild'
    actual_name=os.environ['CAPTURE_ARGV0']
    if '-o' not in args:os.execv(str(stock),[actual_name,*args])
    output=Path(args[args.index('-o')+1]);assert str(output)==os.environ['CAPTURE_OUTPUT']
    assert not any(v.startswith(('--threads','--dependency-file')) for v in args)
    assert sha(stock)==WDIG and set(os.sched_getaffinity(0))==set(range(16))
    write(cube/'private-native-argv.json',[actual_name,*args])
    canonical=[actual_name,*args];canonical[canonical.index('-o')+1]='<output>'
    argv_sha=digest(canonical)
    candidates=set()
    for i,v in enumerate(args):
        if i and args[i-1]=='-o':continue
        if v.startswith('@'):raise ValueError('Unexpected response operand')
        if not v.startswith('-') and Path(v).is_file():candidates.add(Path(v))
        if v.startswith('-plugin-opt=') and Path(v.split('=',1)[1]).is_file():candidates.add(Path(v.split('=',1)[1]))
    assert len(candidates)>8
    def depfile(f):
        data=f.read_text();lines=data.splitlines();pre=str(output)+': '
        assert lines[0].startswith(pre) and '\\' not in lines[0]
        paths=[Path(v) for v in lines[0][len(pre):].split()]
        assert set(lines[1:])-{''}=={str(p)+':' for p in paths}
        assert len(paths)==len(set(paths)) and len(paths)>30
        return set(paths)
    def full(inputs):
        entries={}
        for f in sorted(inputs):
            s=f.stat();assert stat.S_ISREG(s.st_mode)
            entries[str(f)]={'resolved':str(f.resolve()),'bytes':s.st_size,'sha256':sha(f)}
        return entries
    def bookkeeping(out):
        p=cube/'bodies'/sha(out)
        if not p.is_file():shutil.copyfile(out,p)
        assert sha(p)==p.name
        return p
    original=None;rows=[];actual={}
    for width in WIDTHS:
        # Capture actual resolved input bytes from Wild. Plain links use no diagnostic arguments.
        dep=cube/(str(width)+'.d')
        prefix=[actual_name,*args,'--threads='+str(width)]
        subprocess.run([*prefix,'--dependency-file='+str(dep)],executable=stock,check=True)
        params=depfile(dep)|candidates
        if original is None:
            original=full(params);write(cube/'private-inputs.json',original)
            assert any(Path(p).name.startswith('libgcc_s.so')for p in original) and any(Path(p).name.startswith('libc.so')for p in original)
        assert set(original)==set(map(str,params))
        first=sha(output)
        subprocess.run(prefix,executable=stock,check=True)
        f=bookkeeping(output);assert f.name==first
        actual[width]=f.name
        receipt=cube/(str(width)+'.json')
        write(receipt,{'target':str(output),'exit':0,'threads':width,'elf_sha256':f.name,'wild_sha256':WDIG,
             'same_verified_inputs':True,'resolved_input_bytes_sha256':digest(original),'argv_except_width_and_output_sha256':argv_sha,
             'with_depfile_sha256':first,'positive_paths':len(original),'depfile':sha(dep)})
        rows.append({'receipt':str(receipt.relative_to(STORE)),'receipt_sha256':sha(receipt),'elf':str(f.relative_to(STORE))})
    assert original==full(set(map(Path,original)))
    seen=set();minimal=[]
    for row in rows:
        sig=Path(row['elf']).name
        if sig not in seen:seen.add(sig);minimal.append(row)
    assert len(minimal)<=12
    write(cube/'all-widths.json',{'widths':actual,'replays':minimal,'all_16_receipts':rows,
          'input_digest':digest(original),'inputs':len(original),'bytes':sum(v['bytes'] for v in original.values()),'argc':len(args),
          'plain_and_diagnostic_equal_at_every_width':True,'hashed_before_and_after':True})


def run():
    assert all((K/(r+'.exit')).read_text()=='0' for r in ('observer','composed'))
    assert sha(K/'ruff_worker.py')=='9c2e4138072679b8ffff20d417fffad8f6bcd3cba1b0dd15309e2d935cbc0813'
    assert shutil.disk_usage(HERE).free>45*2**30
    spec=importlib.util.spec_from_file_location('native',K/'ruff_worker.py');n=importlib.util.module_from_spec(spec);spec.loader.exec_module(n)
    records={};names={};digests={}
    for phase in ('seed-cold','seed-repeat1','seed-repeat2','selected-observer','repeat-observer','selected-composed','repeat-composed'):
        d=W/phase;row=read(d/'products.json')
        for v in map(json.loads,(d/'stdout').read_bytes().splitlines()):
            if v['reason']=='compiler-artifact' and v['package_id'].startswith('path+'):
                for f in [*v['filenames'],v['executable']]:
                    if f and f in row['native']:
                        names[f]=[Path(v['manifest_path']).parent.name,v['target']['name'],v['target']['kind']]
                        digests.setdefault(f,{})[phase]=row['native'][f]
        records[phase]=row
    genuine=set(records['selected-observer']['native'])
    nearby={name for name,h in digests.items() if len(set(h.values()))>1} & genuine
    repeat=read(W/'repeat-observer/physical.json');recipes={}
    for task in repeat:
        if task['kind']!='link-only':continue
        recipe,=[Path(f) for f in task['argv'] if f.endswith('.rlink')]
        out=str(recipe.with_suffix(''));assert out in genuine and out not in recipes
        recipes[out]=(recipe,task)
    prior={name for name in recipes if names[name][1] in HISTORICAL}
    possible=sorted(nearby|prior)
    assert 1<=len(possible)<=12 and set(possible)<=set(recipes),(len(possible),set(possible)-set(recipes))
    write(HERE/'policy.json',{'observed':sorted(nearby),'prior_history':sorted(prior),'targets':possible,'widths':WIDTHS,
          'all':{n:digests[n] for n in possible},'receipts':{p:sha(W/p/'products.json') for p in records}})
    stock=n.sdk/'lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd';assert sha(stock)==WDIG
    shutil.copy2(stock,HERE/'stock-wild');assert sha(HERE/'stock-wild')==WDIG
    sh=HERE/'stock-capture';sh.write_text('#!/bin/sh\nexec /usr/bin/python3 -IB '+shlex.quote(str(HERE/'replay.py'))+' shim "$@"\n');sh.chmod(0o700)
    state=W/'state-observer';variants={};terminal={}
    for i,chosen in enumerate(possible):
        cube=HERE/(str(i).zfill(2)+'-'+Path(chosen).name);cube.mkdir();(cube/'bodies').mkdir();(cube/'tmp').mkdir()
        assert shutil.disk_usage(HERE).free>38*2**30
        recipe,j=recipes[chosen];source=n.actual(str(recipe.parent),state);before=sha(source/recipe.name)
        subprocess.run(['cp','-a','--reflink=auto','--',source,cube/'private-out'],check=True)
        assert sha(cube/'private-out'/recipe.name)==before
        ns,env,_=n.invocation(state,'observer',True,cube)
        for pos,token in enumerate(ns):
            if token=='--bind' and Path(ns[pos+1]).is_relative_to(state):ns[pos]='--ro-bind'
        dash=ns.index('--chdir')
        ns[dash:dash]=['--bind',str(cube/'private-out'),str(recipe.parent),'--bind',str(cube/'tmp'),str(n.can/'tmp'),'--ro-bind',str(sh),str(stock)]
        env.update({'CAPTURE_HERE':str(cube),'CAPTURE_ARGV0':str(stock),'CAPTURE_OUTPUT':chosen})
        with (cube/'rustc.stdout').open('xb') as so,(cube/'rustc.stderr').open('xb') as se:
            proc=subprocess.run([*ns,*j['argv']],env=env,stdout=so,stderr=se,timeout=600)
        assert proc.returncode==0,(chosen,(cube/'rustc.stderr').read_text()[-1500:])
        assert sha(source/recipe.name)==before
        result=read(cube/'all-widths.json');valid=set(result['widths'].values())
        observed={v for tag,v in digests[chosen].items() if tag.startswith(('selected-','repeat-'))}
        assert observed<=valid,(chosen,'historical whole command hashes not reproduced',observed-valid)
        # Also require seed variants of an unchanged output to be accounted for when used for anticipation.
        if chosen in nearby:
            assert set(digests[chosen].values())<=valid,(chosen,'excluded-seed output not reproduced')
        terminal[chosen]={'target':names[chosen],'actual':digests[chosen],'raw_replayed':result['widths'],'inputs':result['inputs'],
            'bytes':result['bytes'],'closure_sha256':result['input_digest'],'source_rustc_exec':j['raw'],'rlink_sha256':before,
            'input_manifest':sha(cube/'private-inputs.json'),'args_manifest':sha(cube/'private-native-argv.json'),'cube':cube.name}
        if len(valid)>1:variants[chosen]={'replays':result['replays']}
        write(cube/'target.json',terminal[chosen])
        # All private products needed to attest any arm hash remain in bodies; the copied Rust working set is disposable.
        compact=cube/'private-out';assert compact.parent==cube and cube.parent==HERE
        shutil.rmtree(compact)
        print(len(terminal),len(possible),names[chosen][:2],len(valid),flush=True)
    write(HERE/'variants.json',variants);write(HERE/'terminal.json',terminal);assert not (STORE/'variants.json').exists();write(STORE/'variants.json',variants)


if __name__=='__main__':
    if sys.argv[1:2]==['shim']:
        shim()
    else:
        try:
            os.sched_setaffinity(0,set(range(16)))
            with (BASE/'combined-native-measure.lock').open('a') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX)
                run()
        except BaseException:
            (HERE/'failure.txt').write_text(traceback.format_exc());raise
