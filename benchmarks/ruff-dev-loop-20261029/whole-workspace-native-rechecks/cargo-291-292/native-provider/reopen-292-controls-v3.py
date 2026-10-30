#!/usr/bin/env python3
"""Reopen the kernel exec records, every submitted Cargo stream, tested images and enrolled outcomes."""
import argparse
import ast
import collections
import fcntl
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def hb(b):return hashlib.sha256(b).hexdigest()
def read(p):return json.loads(Path(p).read_bytes())
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':')).encode()
def module(n,p):
    s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def arg(v,k):return v[v.index(k)+1] if k in v else None
def compressed(path,data):
    with path.open('xb') as f,gzip.GzipFile(filename='',mode='wb',mtime=0,fileobj=f) as g:g.write(canonical(data)+b'\n')
E2E='ty_server/test/e2e'
FRONT='fa2ed3ec44adb4455d5323c4ee582becd5307cb4aae6b5cfc3cdc289b3140512'
REL={'./conftest','./include/jemalloc/internal/private_symbols.sh','./include/jemalloc/internal/public_namespace.sh','./include/jemalloc/internal/public_unnamespace.sh','./include/jemalloc/jemalloc_rename.sh','./include/jemalloc/jemalloc_mangle.sh','./include/jemalloc/jemalloc.sh'}
def scan_live_opens(trace, wildpids, slot, obj):
    family={};opens={}
    for f in trace.glob('exec.*'):
        tid=int(f.suffix[1:]);kids=set();hits=[];pending=None
        for row in f.read_text().splitlines():
            if row.endswith('<unfinished ...>'):assert pending is None;pending=row[:row.rfind('<unfinished ...>')];continue
            if row.startswith('<... '):
                start,sep,tail=row.partition(' resumed>');assert pending and sep and pending.split('(',1)[0]==start[5:];row=pending+tail;pending=None
            m=re.match(r'(?:clone3?|fork|vfork)\(.*\)\s+= ([1-9]\d*)$',row)
            if m:kids.add(int(m[1]))
            m=re.match(r'openat\([^,]+, ("(?:[^"\\]|\\.)*"), O_RDONLY.*\)\s+= (\d+)$',row)
            if m:
                path=ast.literal_eval(m[1])
                if path==slot:hits.append('script')
                if path==obj:hits.append('object')
        assert pending is None
        family[tid]=kids;opens[tid]=hits
    todo=list(wildpids);allp=set(todo)
    while todo:
        new=family.get(todo.pop(),set())-allp;allp.update(new);todo.extend(new)
    return collections.Counter(n for t in allp for n in opens.get(t,()))
def native_case(p,s,stem,mode,tag,state,provider,forced,fixed,parser,role,body_catalog):
    d=p/('control-'+mode)/tag
    v=read(d/'complete.json');e=read(d/'entered.json');b=read(d.parent/'binding.json')
    assert (v['arm'],v['mode'],v['label'],v['source'],v['provider'])==(p.name,mode,tag,state,provider)
    assert set(v['forced'])==set(e['forced']) and bool(v['forced'])==forced
    src=Path(b['env']['CARGO_TARGET_DIR']).parent/'source'; assert b['driver']==s['driver'] and b['wild']==s['wild'] and b['cargo']==s['arms'][stem]['sha256']
    assert not {'RUSTFLAGS','RUSTC','RUSTC_WRAPPER','RUSTC_WORKSPACE_WRAPPER','WILD_LOG','CARGO_ENCODED_RUSTFLAGS'} & b['env'].keys()
    rows=[json.loads(v) for v in (d/'cargo.stdout').read_bytes().splitlines()];st=v['cargo'];code=st['exit']
    for io in ('stderr','stdout'):assert sha(d/('cargo.'+io))==st[io]
    assert rows[-1]=={'reason':'build-finished','success':code==0} and code==(101 if provider=='malformed' or state=='invalid' else 0)
    arts=[a for a in rows if a['reason']=='compiler-artifact'];assert v['typed']==len(arts) and v['fresh']==sum(a['fresh'] for a in arts)
    if not code:assert len(arts)==(619 if mode=='provider50' else 300)
    if mode=='empty' or mode=='focus' and tag=='01-original':assert not v['fresh']
    n=v['native'];assert sha(d/'native-jobs.json.gz')==n['native_jobs'];jobs=json.load(gzip.open(d/'native-jobs.json.gz'))
    real,ch,files,res=parser.collect_execs(d/'trace')
    erased=collections.Counter();relative=collections.Counter()
    for (literal,argv),k in real.items():
        absolute=literal
        if not Path(literal).is_absolute():
            assert literal in REL and argv[0]==literal;absolute=str(src/literal);relative[literal]+=k
            assert not any(j['path']==absolute and j['kind']!='other' for j in jobs)
        erased[(absolute,argv)]+=k
    assert erased==collections.Counter((j['path'],tuple(j['args'])) for j in jobs)
    assert (files,ch)==(n['raw_pid_files'],n['raw_sha256'])
    native=[];wild=[];logical=collections.Counter()
    for job in jobs:
        path=job['path'];a=job['args'];label=job['kind'];hx=hb(b'\x00'.join(os.fsencode(x) for x in a)+b'\x00');assert hx==job['argv_sha256']
        img=n['images'].get(path,{}).get('sha256');rid=None;nm=None
        if img==s['arms'][stem]['sha256']:
            assert label=='cargo' and a[1:]==b['call'][2:];rid='cargo'
        elif img==FRONT:
            nm=arg(a,'--crate-name');yes,spelling,recipes=role(a)
            probe=not nm or any(t=='--print' or t.startswith('--print=') for t in a) and not any(t=='--emit' or t.startswith('--emit=') for t in a)
            rid='cached' if yes else 'probe' if probe else 'full'
            assert (rid!='cached' or spelling=='split' and len(recipes)==1) and (rid=='probe' or label in ('rustc-full','rustc-cached'))
        elif img==s['wild']:
            assert label=='wild' and '-o' in a;rid='wild';wild.append(job)
        elif label in ('collect2','gcc'):
            assert img;rid=label
        if rid is not None:
            logical[rid]+=1;native.append([rid,nm,hx,img])
    assert logical['cargo']==1 and (logical['full']+logical['cached'],logical['wild'])==(v['full']+v['link_only'],v['wild'])
    witness=v['actual_selected_linkers'];assert set(witness.values())<=set(j['argv_sha256'] for j in wild) and len(set(witness.values()))==len(witness)
    selected={}
    # Use each target's actual Cargo manifest, including packages whose targets have a different spelling.
    root=p.parents[1];checkout=root/'view/source'
    assert checkout.stat().st_ino==(root/'inputs/ruff').stat().st_ino and os.statvfs(checkout).f_flag&os.ST_RDONLY
    package_context={}
    for unit in arts:
        if not unit.get('executable') or not unit['profile']['test'] or len(unit['target']['kind'])!=1:continue
        manifest=Path(unit['manifest_path'])
        if not manifest.is_relative_to(src):continue
        manifest_relative=manifest.relative_to(src);actual=checkout/manifest_relative
        assert actual.samefile(root/'inputs/ruff'/manifest_relative) and actual.resolve().is_relative_to(checkout)
        package=tomllib.loads(actual.read_text())['package']['name']
        key='/'.join((package,unit['target']['kind'][0],unit['target']['name']))
        if key in v['outputs']:
            assert key not in package_context;package_context[key]=str(manifest_relative.parent)
    assert set(package_context)==set(v['outputs'])
    for name,bb in v['outputs'].items():
        assert name in fixed and (mode=='provider50' or name==E2E) and (name in witness)==bb['was_linked']
        prog=Path(bb['list_file'])
        assert prog.parent.parent==d and sha(prog)==bb['listed'] and sha(prog.parent/'list.stderr')==bb['stderr']
        elf=p/'objects'/(bb['sha256']+'.zst');assert elf.is_file()
        key=(str(elf),bb['sha256']);old=body_catalog.setdefault(key,{'bytes':bb['size'],'outputs':set(),'expected':{},'contexts':set()});old['contexts'].add(package_context[name])
        assert old['bytes']==bb['size'];old['outputs'].add(name);old['expected'].setdefault(bb['list_exit'],set()).add(bb['listed'])
        if provider=='valid':
            assert bb['list_exit']==83 and bb['listed']==bb['stderr']==hb(b'') and name in witness
        else:
            assert bb['list_exit']==0
        item={'body':bb['sha256'],'bytes':bb['size'],'list_exit':bb['list_exit'],'list':bb['listed'],'linked':bb['was_linked']}
        if name==E2E and provider!='valid':
            assert sum(x.endswith(b': test') for x in prog.read_bytes().splitlines())==200 and item['list']==s['inventory']
            item['tests']={}
            for ix,case in enumerate(s['cases']):
                data=(prog.parent/f'case-{ix}.stdout').read_bytes();err=prog.parent/f'case-{ix}.stderr'
                assert ('test '+case+' ... ok').encode() in data.splitlines() and b'199 filtered out' in data
                item['tests'][case]={'stdout':data.decode(),'sha256':hb(data),'stderr_sha256':sha(err),'stderr_bytes':err.stat().st_size}
        selected[name]=item
    if code==0:assert set(selected)==(set(fixed) if mode=='provider50' else {E2E})
    else:assert not selected
    returned={'arm':stem,'mode':mode,'case':tag,'source':state,'source_SHA256':e['source_sha256'],'provider':provider,'provider_SHA256':e['provider_sha'],'forced':sorted(v['forced']),'cargo':code,'typed':len(arts),'fresh':v['fresh'],'native':native,'counts':dict(logical),'selected_native':witness,'outputs':selected,'raw':{'complete':sha(d/'complete.json'),'stdout':st['stdout'],'stderr':st['stderr'],'trace_files':files,'kernel_commitment':ch,'jobs':n['native_jobs'],'resumed_syscalls':res,'relative_non_native':dict(relative)}}
    for name,rec in v['forced'].items():
        assert sha(d/rec['backup'])==rec['sha256']
    if 'opens' in v:
        slot=e['provider_path'];hook=str(Path(b['env']['TMPDIR'])/('qualified-h9-recheck-'+mode+'.o'))
        actual=scan_live_opens(d/'trace',{j['tid'] for j in wild},slot,hook)
        assert dict(actual)==v['opens']['counts'] and actual['script']>=1 and bool(actual['object'])==(provider=='valid')
        returned['actual_Wild_family_successful_opens']=dict(actual)
    if 'coherent' in v:
        stderr=(d/'coherent.stderr').read_bytes()
        assert sha(d/'coherent.rmeta')==v['coherent']['result'] and not any(line.startswith(b'error') for line in stderr.splitlines())
        returned['same_generation_reader']={**v['coherent'],'stderr_sha256':hb(stderr)}
    if provider=='malformed':
        assert b'OHM_REJECT_BAD_WORKSPACE_TEST_LINK_SCRIPT' in (d/'cargo.stdout').read_bytes()+(d/'cargo.stderr').read_bytes() and wild
        returned['native_diagnostic']='OHM_REJECT_BAD_WORKSPACE_TEST_LINK_SCRIPT'
    if state=='invalid':
        assert E2E not in witness
        diag=[j for a in rows for j in [a.get('message') or {}] if (j.get('code') or {}).get('code')=='E0308' and any(z['is_primary'] and z['line_start']==22 and z['file_name'].endswith('crates/ty_server/tests/e2e/inlay_hints.rs') for z in j['spans'])]
        assert diag==v['diagnostic'];returned['invalid']=[{'code':x['code']['code'],'message':x['message'],'original_diagnostic_sha256':hb(canonical(x)),'primary_spans':[{k:z[k] for k in ('line_start','line_end','column_start','column_end','label','text')} for z in x['spans'] if z['is_primary']]} for x in diag]
    return returned
def reopen(objects, prior, checkout):
    opened={};scope={}
    with tempfile.TemporaryDirectory(prefix='run-products-',dir=prior) as sandbox:
        priv=Path(sandbox)
        for (file,digest),rec in objects.items():
            assert sorted(rec['expected']) in ([0],[83]);compressed_sha=sha(file);snap=opened.get(digest)
            fd=os.memfd_create('qualified-native-program',os.MFD_CLOEXEC|os.MFD_ALLOW_SEALING|getattr(os,'MFD_EXEC',0x0010))
            try:
                z=subprocess.Popen(['zstd','-dcq','--',file],stdout=subprocess.PIPE)
                with os.fdopen(os.dup(fd),'wb') as w:shutil.copyfileobj(z.stdout,w,1024*1024)
                z.stdout.close();assert z.wait()==0;os.lseek(fd,0,os.SEEK_SET);os.fchmod(fd,0o500)
                fcntl.fcntl(fd,fcntl.F_ADD_SEALS,fcntl.F_SEAL_WRITE|fcntl.F_SEAL_GROW|fcntl.F_SEAL_SHRINK|fcntl.F_SEAL_SEAL)
                with os.fdopen(os.dup(fd),'rb') as f:assert f.read(4)==b'\x7fELF';f.seek(0);assert hashlib.file_digest(f,'sha256').hexdigest()==digest
                assert os.fstat(fd).st_size==rec['bytes']
                for relative in sorted(rec['contexts']):
                    manifest=checkout/relative/'Cargo.toml'
                    assert manifest.is_file() and manifest.resolve().is_relative_to(checkout) and os.statvfs(manifest).f_flag&os.ST_RDONLY
                    env={'HOME':str(priv),'TMPDIR':str(priv),'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C',
                         'CARGO_MANIFEST_DIR':str(manifest.parent),'CARGO_MANIFEST_PATH':str(manifest)}
                    q=subprocess.run(['/proc/self/fd/'+str(fd),'--list'],pass_fds=(fd,),cwd=manifest.parent,env=env,capture_output=True,timeout=30)
                    assert q.returncode in rec['expected'] and hb(q.stdout) in rec['expected'][q.returncode] and not q.stderr,(rec['outputs'],relative,q.returncode,q.stderr[:160])
                    if snap:assert q.returncode==snap['returncode'] and hb(q.stdout)==snap['stdout']
                if not snap:opened[digest]={'copies':1,'bytes':rec['bytes'],'returncode':q.returncode,'stdout':hb(q.stdout),'compressed_copies':[compressed_sha],'package_directories':sorted(rec['contexts'])}
                else:
                    snap['copies']+=1;snap['compressed_copies'].append(compressed_sha)
                    snap['package_directories']=sorted(set(snap['package_directories'])|rec['contexts'])
            finally:os.close(fd)
    return opened
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('root',type=Path);ap.add_argument('out',type=Path);ap.add_argument('--lane',action='append',choices=['K-focus','K-edited-clean','U-focus','U-edited-clean','K','U']);ap.add_argument('--no-execute',action='store_true',help='diagnostic source-only readback');a=ap.parse_args()
    root=a.root.resolve(strict=True);reg=root/'ops/qualification';plan=read(root/'ops/conditional/control-plan.json');s=read(reg/'study.json');parser=module('kernel_events',reg/'independent-native-parser.py');role=module('native_role',root/'reports/primary-public-v1/native_role.py').role;fixed={'/'.join((x['package'],x['kind'],x['target'])) for x in read(reg/'fifty-targets.json')};assert len(fixed)==50
    targets=a.lane or ['K-focus','K-edited-clean','U-focus','U-edited-clean','K','U']
    a.out.mkdir(mode=0o700);allrows={};files={};terms={}
    for key in targets:
        mode='focus' if key.endswith('-focus') else 'empty' if key.endswith('-edited-clean') else 'provider50';stem=key[0];p=root/'state'/key
        term=p/('control-'+mode)/'terminal.json';t=read(term);assert t['pass'] and t['stock_script']==plan['stock_script_sha256']
        branch=[];opts=plan['orders'][mode]
        assert set(t['cases'])=={x[0] for x in opts}
        for tag,state,provider,forced in opts:
            assert sha(term.parent/tag/'complete.json')==t['cases'][tag]
            branch.append(native_case(p,s,stem,mode,tag,state,provider,forced,fixed,parser,role,files))
        allrows[key]=branch;terms[key]=sha(term)
    opened={} if a.no_execute else reopen(files,a.out,root/'view/source')
    compressed(a.out/'observations.json.gz',{'lanes':allrows,'bodies':opened})
    result={'study':'source-matched W with #291 and #292, native and historical correctness','lanes':terms,'num_commands':sum(map(len,allrows.values())),'native_trace_files':sum(v['raw']['trace_files'] for x in allrows.values() for v in x),'physical_reopened_native_products':len(opened),'physical_full_source_qualified':not a.no_execute and len(targets)==6,'source_sha256sums':sha(root/'ops/conditional/SHA256SUMS'),'actual_six_primary_bundle':'5b4c1c1da6e45939c1d0e7b4bbbbd3f31cde60662475512731258add3514ee39','native_argv_projection':sha(a.out/'observations.json.gz')}
    if len(targets)==6:
        for arm in ('K','U'):
            fok={r['case']:r for r in allrows[arm+'-focus']};cold=allrows[arm+'-edited-clean'][0]
            assert fok['02-edited']['outputs'][E2E]['body']==cold['outputs'][E2E]['body'] and cold['fresh']==0
            group={r['case']:r for r in allrows[arm]}
            for name in fixed:
                assert group['01-native-valid']['outputs'][name]['body']==group['03-forced-valid']['outputs'][name]['body']
                normal={group[k]['outputs'][name]['body'] for k in ('02-remove','05-remove','07-final-remove')};assert len(normal)==1 and group['01-native-valid']['outputs'][name]['body'] not in normal
        for xa,xb in [('K-focus','U-focus'),('K-edited-clean','U-edited-clean'),('K','U')]:
            for x,y in zip(allrows[xa],allrows[xb]):
                assert x['case']==y['case'] and x['cargo']==y['cargo'] and set(x['outputs'])==set(y['outputs'])
                for n in x['outputs']:
                    for k in ('body','list','list_exit','bytes'):assert x['outputs'][n][k]==y['outputs'][n][k],(n,x['case'],k)
                if x.get('invalid'):assert x['invalid']==y['invalid']
    with (a.out/'receipt.json').open('x') as f:json.dump(result,f,indent=2,sort_keys=True);f.write('\n')
    print(json.dumps(result,sort_keys=True))
if __name__=='__main__':main()

