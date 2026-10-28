"""Exercise ordinary full/link-only decisions; no tool wrapper or project Rust flags."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def write(p, s):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s)


def jsonf(p, v):
    write(p, json.dumps(v, indent=2, sort_keys=True)+'\n')


def execs(path):
    procs=[]
    for tr in sorted(path.parent.glob(path.name+'.*')):
        lines=tr.read_text(errors='replace').splitlines()
        for line in lines:
            m=re.match(r'execve\(("(?:[^"\\]|\\.)*"), (\[.*\]), (?:0x[^ ]+ )?/\* [0-9]+ vars \*/\)\s+= 0$',line)
            if not m:
                continue
            executable=ast.literal_eval(m[1]); tokens=ast.literal_eval(m[2]); name=Path(executable).name
            if name=='rustc':
                if '--crate-name' not in tokens:continue
                unit=tokens[tokens.index('--crate-name')+1]
                if unit=='___':continue
                z=[t for a,t in zip(tokens,tokens[1:]) if a=='-Z']+[s[2:] for s in tokens if s.startswith('-Z') and s!='-Z']
                typ='link-only' if 'link-only' in z else 'full'
            elif name=='wild' or name.endswith('ld-wild') or '/wild-ld/' in executable:unit='';typ='wild'
            elif name.endswith('collect2'):unit='';typ='collect2'
            elif name in ('ld','ld.lld','rust-lld'):unit='';typ='ld'
            else:continue
            procs.append(dict(executable=executable,argv=tokens,type=typ,unit=unit,exit=lines[-1],pid=tr.suffix[1:]))
    return procs


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('state',type=Path,help='a new empty private work directory')
    ap.add_argument('--expect-eligible-skip',action='store_true',help='require the entirely unchanged repeat to skip the consumer')
    args=ap.parse_args()
    w=args.state.resolve()
    w.mkdir(mode=0o700)
    s=w/'source'; d=w/'target'; shared=w/'shared'; reports=w/'reports'
    external=w/'external'
    write(s/'Cargo.toml','[workspace]\nmembers=["tokens","observer","leaf","reader"]\nresolver="3"\n[profile.dev.package.leaf]\nincremental=false\n')
    crates={'tokens':'', 'observer':'[lib]\nproc-macro=true\n','leaf':'[dependencies]\ntokens={path="../tokens"}\nobserver={path="../observer"}\n','reader':'[dependencies]\nleaf={path="../leaf"}\n'}
    for c,extra in crates.items():
        write(s/c/'Cargo.toml',f'[package]\nname="{c}"\nversion="0.1.0"\nedition="2021"\n'+extra)
    write(s/'tokens/src/lib.rs','#[macro_export] macro_rules! observed { () => { ::observer::observe!(foreign_token) }; }\n')
    write(s/'observer/src/lib.rs','extern crate proc_macro;\nuse proc_macro::TokenStream;\n#[proc_macro] pub fn observe(t:TokenStream)->TokenStream { let s=t.into_iter().next().unwrap().span(); ::std::hint::black_box(format!("{s:?}")); "()".parse().unwrap() }\n')
    write(s/'leaf/build.rs','''use std::path::PathBuf;
fn main() {
    let external = PathBuf::from(std::env::var_os("CARGO_MANIFEST_DIR").unwrap()).parent().unwrap().parent().unwrap().join("external");
    println!("cargo:rerun-if-changed=build.rs");
    println!("cargo:rustc-link-search=native={}", external.join("first").display());
    println!("cargo:rustc-link-search=native={}", external.join("second").display());
}
''')
    leaf='const _: () = tokens::observed!();\n#[link(name="nativeguard",kind="static",modifiers="-bundle")] unsafe extern "C" {fn nativeguard_number()->i32;}\n#[inline(never)] pub fn answer()->i32 {unsafe { nativeguard_number() } + ADDEND}\n'
    leaf=leaf.replace('unsafe { nativeguard_number() } +','(unsafe { nativeguard_number() }) +')
    write(s/'leaf/src/lib.rs',leaf.replace('ADDEND','0'))
    write(s/'reader/src/main.rs','fn main(){println!("native-value={}",leaf::answer());}\n')
    env=os.environ.copy()
    for k in list(env):
        if k.startswith('CARGO_') or k in ('RUSTFLAGS','RUSTC','RUSTC_WRAPPER','RUSTC_WORKSPACE_WRAPPER','RUST_BACKTRACE'):
            env.pop(k,None)
    env.update(CARGO_HOME=str(w/'cargo-home'),CARGO_TARGET_DIR=str(d),CARGO_BUILD_BUILD_DIR=str(shared),CARGO_NET_OFFLINE='true')
    proxy=shutil.which('cargo'); assert proxy
    cargo=[proxy,'+ohm']
    def run(argv,cwd=s,**kw):
        return subprocess.run([str(t) for t in argv],cwd=cwd,env=env,check=True,capture_output=True,**kw)
    run(cargo+['generate-lockfile','--offline'])
    (external/'first').mkdir(parents=True)
    (external/'second').mkdir()
    def archive(name, value):
        a=external/name/'libnativeguard.a'
        src=external/'native.c';obj=external/'native.o'
        write(src,f'int nativeguard_number(void) {{return {value};}}\n')
        run(['cc','-fPIC','-c',src,'-o',obj]); run(['ar','rcsD',a,obj])
        return a
    archive('second',41)
    rows={}
    def phase(name, wanted):
        p=reports/name;p.mkdir(parents=True)
        cmd=cargo+['build','--workspace','--locked','--offline','-j2','--message-format=json']
        r=run(['strace','-ff','-q','-s','131072','-o',str(p/'exec'),'-e','trace=execve','--',*cmd]); (p/'stderr').write_bytes(r.stderr); (p/'stdout').write_bytes(r.stdout)
        units=[json.loads(l) for l in r.stdout.splitlines() if json.loads(l).get('reason')=='compiler-artifact']
        leaf_product=next(v for v in units if v['target']['name']=='leaf' and 'lib' in v['target']['kind'])
        rlib=next(Path(x) for x in leaf_product['filenames'] if x.endswith('.rlib'))
        ex=next(Path(v['executable']) for v in units if v['target']['name']=='reader')
        raw=run([ex]).stdout.decode().strip()
        procs=execs(p/'exec')
        (p/'native.txt').write_text(raw+'\n')
        jsonf(p/'processes.json',procs)
        files=[(t,v) for t,v in [('rlib',rlib),('rmeta',rlib.with_suffix('.rmeta')),('executable',ex),('first',external/'first/libnativeguard.a'),('second',external/'second/libnativeguard.a')] if v.exists()]
        meta={str(p):digest(p) for base in (shared,d) for p in base.rglob('libleaf-*.rmeta')}
        if meta:
            assert len(set(meta.values()))==1,meta
            f=Path(next(iter(meta)));files.append(('separate_rmeta',f));shutil.copyfile(f,p/'libleaf.rmeta')
        shutil.copyfile(rlib,p/'libleaf.rlib')
        manifests=sorted(x for b in (shared,d) for x in b.rglob('*.rlink'));fields=[(str(x.relative_to(w)),digest(x)) for x in manifests]
        row=dict(wanted=wanted,actual=raw,files={t:{'path':str(v),'sha256':digest(v),'size':v.stat().st_size} for t,v in files},
                 rustcs=[[v['type'],v['unit']] for v in procs if v['type'] in ('full','link-only')],
                 wild=sum(v['type']=='wild' for v in procs),collect2=sum(v['type']=='collect2' for v in procs),
                 fresh={v['target']['name']:v['fresh'] for v in units},rlinks=fields)
        rows[name]=row
        jsonf(p/'row.json',row);jsonf(reports/'all.json',rows)
        print(name,raw,row['rustcs'],row['wild'],row['files']['rlib']['sha256'][:12],flush=True)
        assert raw==f'native-value={wanted}',(name,raw,wanted)
        return row
    def gold(name,wanted):
        wd,ws=w/'retained-target',w/'retained-shared'
        d.rename(wd);shared.rename(ws)
        try: return phase(name+'-empty',wanted)
        finally:
            if d.exists(): shutil.rmtree(d)
            if shared.exists(): shutil.rmtree(shared)
            wd.rename(d);ws.rename(shared)
    original=phase('original',41)
    assert ['full','leaf'] in original['rustcs'] and ['full','reader'] in original['rustcs'],original['rustcs']
    repeat=phase('repeat',41)
    assert ['full','leaf'] in repeat['rustcs'], 'fixture did not schedule the true observing leaf'
    if args.expect_eligible_skip: assert all(v[1]!='reader' for v in repeat['rustcs']),repeat
    archive('first',83)
    first=phase('earlier-provider',83); gold('earlier-provider',83)
    (external/'first/libnativeguard.a').unlink()
    dt=phase('removed-provider',41);gold('removed-provider',41)
    old=external/'second/libnativeguard.a'
    st=old.stat();oldsha=digest(old);archive('second',83);assert old.stat().st_size==st.st_size and oldsha!=digest(old)
    os.utime(old,ns=(st.st_atime_ns,st.st_mtime_ns));assert old.stat().st_mtime_ns==st.st_mtime_ns
    stamp=phase('same-size-time-native',83);gold('same-size-time-native',83)
    exe=Path(stamp['files']['executable']['path']);data=exe.read_bytes();oldtag,newtag=b'native-value=',b'stale!-value='
    assert len(oldtag)==len(newtag) and data.count(oldtag)==1
    es=exe.stat()
    with exe.open('r+b') as f: f.seek(data.index(oldtag));f.write(newtag)
    os.utime(exe,ns=(es.st_atime_ns,es.st_mtime_ns))
    assert exe.stat().st_size==es.st_size and exe.stat().st_mtime_ns==es.st_mtime_ns
    assert run([exe]).stdout.strip()==b'stale!-value=83'
    repaired=phase('same-size-time-output',83)
    write(s/'leaf/src/lib.rs',leaf.replace('ADDEND','1'))
    body=phase('private-body',84);gold('private-body',84)
    same=[rows[n]['files']['rlib']['sha256'] for n in ('original','repeat','earlier-provider','removed-provider','same-size-time-native','same-size-time-output')]
    assert len(set(same))==1,(same,rows)
    assert body['files']['rlib']['sha256']!=same[0]
    jsonf(reports/'verified.json',{'pass':True,'exe':str(exe),'identical_rlib':same[0],'run_values':{k:v['actual'] for k,v in rows.items()}})

if __name__=='__main__': main()
