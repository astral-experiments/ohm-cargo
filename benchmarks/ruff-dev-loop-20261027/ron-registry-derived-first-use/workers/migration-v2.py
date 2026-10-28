"""Real first-use of a foreign observation beside a previously green registry derive."""
import argparse, hashlib, json, os, re, shutil, struct, subprocess, sys, tarfile, time
from pathlib import Path

HERE=Path(__file__).resolve().parent
X=Path('/dev/shm/ohm-ron-consumed-v1-20261028')
SDK=Path('/dev/shm/ohm-published-member-h2-20261028/installed17')
FIXED=Path('/mnt/devbox-scratch/dev-user/ohm-observer-consumption-tools-20261028/fixed-cargo')
CARGOS={'official':SDK/'bin/cargo','261':FIXED,'known':X/'target-derive-guard/debug/cargo','v2':X/'target-default-guard/debug/cargo'}
EXPECTED={'official':'4e4065390403afbf4fb77b2f41fbc21c59afe3dda2337a5bbe29fda29a47dbb3','261':'0aa04df8023984b83ef676d1494d43e482472e1b2bccdb82a4d0bd390578a322'}
DRIVER='618ebac16b7d4ec01a2af89661d25b8f26ff347edbb69c6dcaa78f10115914a7'
FRONT='7ec5263869aed2fc9272ea7212aabbe7b272a4685f1b79af75c123daff09c02c'
def h(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def store(p,data):p.write_text(json.dumps(data,indent=2,sort_keys=True)+'\n')
def sections(path):
    a=path.read_bytes();assert a[:6]==b'\x7fELF\x02\x01';off=struct.unpack_from('<Q',a,40)[0];size,count,idx=struct.unpack_from('<HHH',a,58)
    rows=[struct.unpack_from('<IIQQQQIIQQ',a,off+n*size) for n in range(count)];s,l=rows[idx][4:6];names=a[s:s+l];out={}
    for r in rows:
        name=names[r[0]:].split(b'\0',1)[0].decode()
        if name in ('.rustc','.dynsym','.text'):out[name]=hashlib.sha256(a[r[4]:r[4]+r[5]]).hexdigest()
    assert len(out)==3;return out

def pack(p,name,cargo,files):
    root=p/'vendor'/(name+'-0.1.0');(root/'src').mkdir(parents=True)
    (root/'Cargo.toml').write_text('[package]\nname="'+name+'"\nversion="0.1.0"\nedition="2021"\n'+cargo)
    for dst,src in files.items():shutil.copyfile(HERE/src,root/dst)
    arc=p/(root.name+'.crate')
    with tarfile.open(arc,'w:gz') as t:t.add(root,arcname=root.name)
    fields={'package':h(arc),'files':{str(f.relative_to(root)):h(f) for f in root.rglob('*') if f.is_file()}}
    store(root/'.cargo-checksum.json',fields);return fields

def run(a,p):
    assert h(SDK/'bin/cargo')==a.cargo_sha and h(SDK/'bin/rustc')==FRONT and h(next((SDK/'lib').glob('librustc_driver*.so')))==DRIVER
    rustup=p/'rustup';(rustup/'toolchains').mkdir(parents=True);(rustup/'toolchains/ohm').symlink_to(SDK)
    packages={}
    for name,manifest,files in [('managed-macro','[lib]\nproc-macro=true\n',{'src/lib.rs':'macro.rs','build.rs':'build.rs'}),('managed-tokens','',{'src/lib.rs':'tokens.rs'}),('managed-api','[dependencies]\nmanaged-macro="=0.1.0"\nmanaged-tokens="=0.1.0"\n',{'src/lib.rs':'api.rs'})]:
        packages[name]=pack(p,name,manifest,files)
    store(p/'packages.json',packages)
    w=p/'ws';w.mkdir();(w/'.cargo').mkdir();(w/'.cargo/config.toml').write_text('[source.crates-io]\nreplace-with="verified"\n[source.verified]\ndirectory="'+str(p/'vendor')+'"\n')
    (w/'Cargo.toml').write_text('[workspace]\nresolver="2"\nmembers=["cli","precursor"]\n')
    for pkg,dep,code in [('cli','managed-api',(HERE/'original.rs').read_text()),('precursor','managed-macro','fn main(){}')]:
        d=w/pkg;(d/'src').mkdir(parents=True);(d/'Cargo.toml').write_text('[package]\nname="'+pkg+'"\nversion="0.0.0"\nedition="2021"\n[dependencies]\n'+dep+'="=0.1.0"\n');(d/'src/main.rs').write_text(code)
    b=p/'barrier';b.mkdir();log=b/'actual-derive-calls';record={'cargo':a.cargo_sha,'driver':DRIVER,'frontend':FRONT,'packages':packages,'source':[h(HERE/'original.rs'),h(HERE/'edited.rs')],'rows':{}};procs={}
    def start(state,name,gen,pkg):
        d=p/state;d.mkdir(exist_ok=True);r=p/name;r.mkdir()
        e={k:v for k,v in os.environ.items() if not k.startswith(('RUST','CARGO'))};e.update(PATH='/home/dev-user/.cargo/bin:'+e['PATH'],RUSTUP_HOME=str(rustup),CARGO_HOME=str(d/'cargo'),CARGO_TARGET_DIR=str(d/'target'),CARGO_BUILD_BUILD_DIR=str(d/'shared'),RUSTUP_AUTO_INSTALL='0',CARGO_NET_OFFLINE='true',OHM_SYNC_DIR=str(b),MANAGED_OBJECT_SOURCE=str(gen))
        if a.optout:e['CARGO_ENCODED_RUSTFLAGS']='-Zcache-proc-macros=no'
        argv=['strace','-ff','-qq','-s','65535','-e','trace=execve','-o',str(r/'exec'),'cargo','+ohm','build','--offline','--message-format=json','-j4','-p',pkg]
        expected=a.cargo_sha
        if name in ('upgrade','upgrade-repeat','up-again','empty'):
            candidate=X/'target-default-guard/debug/cargo';assert h(candidate)==a.new_sha
            expected=a.new_sha
        else:
            candidate=SDK/'bin/cargo'
        leaf=['strace','-ff','-qq','-s','65535','-e','trace=execve','-o',str(r/'exec'),'cargo','+ohm','build','--offline','--message-format=json','-j4','-p',pkg]
        host=['bwrap','--die-with-parent','--ro-bind','/','/','--dev','/dev','--proc','/proc','--ro-bind','/dev/shm','/dev/shm','--tmpfs','/tmp','--bind',str(X),str(X)]
        if name in ('upgrade','upgrade-repeat','up-again','empty'):host+=['--ro-bind',str(candidate),str(SDK/'bin/cargo')]
        argv=host+['--','bash','-c','set -eu; sha256sum "$1" > "$2"; shift 2; exec "$@"','physical-cargo',str(SDK/'bin/cargo'),str(r/'cargo.sha'),*leaf]
        (r/'expected-cargo').write_text(expected)
        oldlog=log.read_text().splitlines() if log.is_file() else []
        with (r/'out').open('wb') as so,(r/'err').open('wb') as se:
            q=subprocess.Popen(argv,cwd=w,env=e,stdout=so,stderr=se)
        procs[q]=(state,name,pkg,oldlog);return q
    def finish(q):
        state,name,pkg,oldlog=procs[q];r=p/name;rc=q.wait(timeout=120)
        if rc:raise RuntimeError((name,rc,(r/'out').read_text()[-2400:],(r/'err').read_text()[-1200:]))
        assert (r/'cargo.sha').read_text().split()[0]==(r/'expected-cargo').read_text()
        events=[json.loads(l) for l in (r/'out').read_bytes().splitlines()];assert events[-1]=={'reason':'build-finished','success':True}
        arts=[m for m in events if m['reason']=='compiler-artifact'];macro,=[m for m in arts if m['target']['name']=='managed_macro'];ids={m['target']['name']:m['package_id'] for m in arts};assert all(i.startswith('registry+') for n,i in ids.items() if 'managed_' in n)
        def rows():
            for f in sorted(r.glob('exec.*')):
                for l in f.read_text().splitlines():
                    if not l.endswith(' = 0') or '"--crate-name",' not in l:continue
                    n=re.search(r'"--crate-name", "([^"]+)"',l)[1]
                    if n=='___':continue
                    yield {'unit':n,'cache_flags':re.findall(r'"(-Zcache-proc-macros(?:=no|=yes)?)"',l),'externs':re.findall(r'"--extern", "([^"]+)"',l),'full':not re.search(r'"-Z\s?link-only|"link-only=',l),'argv_sha':hashlib.sha256(l.encode()).hexdigest()}
        values=None;marker=None;fp=None;raw=None
        if pkg=='cli':
            target,=[m for m in arts if m['target']['name']=='cli'];values=subprocess.check_output([target['executable']]).decode().splitlines();assert len(values)==1 and re.fullmatch(r'\d+/\d+',values[0]),values
            fps=sorted((p/state).rglob('dep-bin-cli'));assert len(fps)==1,fps
            dps=[fps[0].parent.parent/'out/cli.d'];assert dps[0].is_file(),dps
            raw=dps[0].read_bytes();fp=fps[0].read_bytes();marker=b'ohm-foreign-span-bytes' in raw;assert marker==(b'OBS1' in fp)
            (r/'rustc.d').write_bytes(raw);(r/'encoded.bin').write_bytes(fp)
        calls=log.read_text().splitlines() if log.exists() else []
        result={'rc':rc,'stdout':None if values is None else values[0],'calls':calls[len(oldlog):],'fresh':{m['target']['name']:m['fresh'] for m in arts},'package_ids':ids,'macro':macro['filenames'][0],'rustc':list(rows()),'marker':marker,'d_sha':h(r/'rustc.d') if raw is not None else None,'fp_sha':h(r/'encoded.bin') if fp is not None else None,'logs':{f.name:h(f) for f in r.iterdir() if f.is_file()}};record['rows'][name]=result;store(r/'row.json',result);store(p/'partial.json',record)
        print(name,result['stdout'],result['marker'],result['calls'],flush=True);return result
    src=w/'cli/src/main.rs'
    if a.observed:shutil.copyfile(HERE/'edited.rs',src)
    seed=finish(start('warm','seed',17,'cli'));old=Path(seed['macro']);snapshot=p/'original-dso';shutil.copyfile(old,snapshot)
    assert seed['stdout']==('17/17' if a.observed else '17/0') and seed['calls']==['17'] and seed['marker']==a.observed,seed
    finish(start('warm','seed-repeat',17,'cli'))
    if not a.observed:shutil.copyfile(HERE/'edited.rs',src)
    assert h(src)==record['source'][1]
    names=[('warm','first-edit',29),('warm','upgrade',29),('warm','upgrade-repeat',29),('warm','downgrade',29),('warm','up-again',29),('independent','empty',29)]
    for state,name,gen in names:finish(start(state,name,gen,'cli'))
    now=Path(record['rows']['first-edit']['macro']);s,t=sections(snapshot),sections(now);assert s['.text']!=t['.text'] and s['.rustc']==t['.rustc'] and s['.dynsym']==t['.dynsym'],(s,t)
    assert record['rows']['empty']['stdout']=='29/29' and record['rows']['empty']['calls']==['29']
    record['sections']=[s,t];record['old_dso']=h(snapshot);record['new_dso']=h(now);record['same_output_path']=old==now;record['observed_seed']=a.observed;record['no_user_binary_writes_or_timestamp_changes']=True
    store(p/'complete.json',record)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('arm',choices=CARGOS);ap.add_argument('tag');ap.add_argument('--optout',action='store_true');ap.add_argument('--observed',action='store_true');ap.add_argument('--cargo-sha');ap.add_argument('--new-sha',required=True);ap.add_argument('--child',action='store_true');a=ap.parse_args();assert re.fullmatch(r'[a-z0-9-]+',a.tag);p=X/('migrate-natural-'+a.tag)
    if a.child:run(a,p)
    else:
        cargo=CARGOS[a.arm];sha=h(cargo);assert sha==(a.cargo_sha or EXPECTED[a.arm]);p.mkdir();args=['bwrap','--die-with-parent','--ro-bind','/','/','--dev','/dev','--proc','/proc','--ro-bind','/dev/shm','/dev/shm','--tmpfs','/tmp','--bind',str(X),str(X)]
        if a.arm!='official':args+=['--ro-bind',str(cargo),str(SDK/'bin/cargo')]
        args+=['--','taskset','-c','8-11',sys.executable,'-B',__file__,a.arm,a.tag,'--cargo-sha',sha,'--new-sha',a.new_sha,'--child'];args+=['--optout'] if a.optout else [];args+=['--observed'] if a.observed else [];sys.exit(subprocess.run(args).returncode)
