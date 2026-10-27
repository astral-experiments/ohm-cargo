"""Exercise cached rlibs and compile an independent external caller before building the clean reference."""
import argparse
import gzip
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

H = Path(__file__).resolve().parent
SOURCE = H / 'original'
CASES = ['files', 'types', 'files_types', 'byteoff', 'newline', 'column', 'expn',
         'files-shrink', 'foreign-expn-shrink', 'local-expn-shrink', 'foreign-expn-disappears', 'local-expn-disappears']

def digest(data):
    return hashlib.sha256(data).hexdigest()

def records(data):
    return [json.loads(line) for line in data.splitlines() if line.startswith(b'{')]

def compiler_identity(args):
    return {name: digest(path.read_bytes()) for name, path in
            [('cargo', args.cargo), ('frontend', args.sysroot/'bin/rustc'), ('driver', args.driver)]}

def fixture(ws, case, changed, caller):
    base = (SOURCE/'leaf/src/lib.rs').read_text()
    defs = (SOURCE/'leaf/src/defs.rs').read_text()
    body = (SOURCE/'bundle/src/lib.rs').read_text()
    app = (SOURCE/'app/src/main.rs').read_text()
    if case in ['files', 'types', 'files_types', 'files-shrink']:
        n = 9 if case == 'files-shrink' else 1
        enabled = not changed if case == 'files-shrink' else changed and 'files' in case
        decls = ''.join(f'#[cfg({"all" if enabled else "any"}())] mod p{i};\n' for i in range(n))
        base = base.replace('#[cfg(any())] mod p0;\n', decls)
        for i in range(n):
            path=ws/f'leaf/src/p{i}.rs'
            if not path.is_file() or path.read_text()!='const _:() = ();\n':
                path.write_text('const _:() = ();\n')
        if 'types' in case and changed:
            base = base.replace('type Item = u8;', 'type Item = i8;')
    else:
        base = 'pub mod defs;\npub fn indirect(x:i32)->i32 { 42/x }\n'
        defs = ('#[inline(always)] pub fn gg<T>(_: T, x:i32) -> i32 { 21/x }\n'
                '#[inline(always)] pub fn hh<T>(_: T, x:i32) -> i32 { crate::indirect(x) }\n')
        if case == 'expn' or '-expn-' in case:
            active = changed if case == 'expn' else (not changed if case == 'foreign-expn-shrink' else True)
            defs += ('#[allow(unused_macros)] macro_rules! before {() => { const _:()=(); }}\n'
                     'macro_rules! public {() => {pub struct Public { pub x:i32 }}}\n'
                     f'#[cfg({"all" if active else "any"}())] before!();\n')
            if case == 'foreign-expn-disappears':
                defs += f'#[cfg({"any" if changed else "all"}())] public!();\n#[cfg({"all" if changed else "any"}())] pub struct Public {{ pub x:i32 }}\n'
            else:
                defs += 'public!();\n'
        else:
            variants = {'byteoff': ('// a\n','// aaaaaaaaaaaaaaaaa\n'),
                        'newline': ('/*first second*/\n','/*first\nsecond*/\n'),
                        'column': (' ',' '*257)}
            defs += variants[case][changed] + 'pub struct Public { pub x:i32 }\n'
    if '-expn-' in case:
        active = not changed if case == 'local-expn-shrink' else True
        body += ('#[allow(unused_macros)] macro_rules! local_before {() => { const _:()=(); }}\n'
                 'macro_rules! own {() => { pub struct Own {pub y:i32} }}\n'
                 f'#[cfg({"all" if active else "any"}())] local_before!();\n')
        if case == 'local-expn-disappears':
            body += f'#[cfg({"any" if changed else "all"}())] own!();\n#[cfg({"all" if changed else "any"}())] pub struct Own {{pub y:i32}}\n'
        else:
            body += 'own!();\n'
        app = app.replace('bundle::','facade::').replace('println!("{}",facade::Public{x:7}.x);',
                                    'println!("{}",facade::Public{x:7}.x + facade::Own{y:2}.y);')
    if caller:
        app = app.replace('struct External;', 'struct External; #[derive(Debug)] struct Distinct;')
        app = app.replace('::nested(External', '::nested(Distinct').replace('x:7','x:11')
    for path,text in [('leaf/src/lib.rs',base),('leaf/src/defs.rs',defs),('bundle/src/lib.rs',body),('app/src/main.rs',app)]:
        f=ws/path
        if f.read_text()!=text: f.write_text(text)

def verify_case(args, root, case):
    root.mkdir()
    ws=root/'workspace';shutil.copytree(SOURCE,ws)
    if '-expn-' in case:
        (ws/'facade/src').mkdir(parents=True)
        (ws/'facade/src/lib.rs').write_text('pub use bundle::*;\n')
        (ws/'facade/Cargo.toml').write_text('[package]\nname="facade"\nversion="0.1.0"\nedition="2024"\n[dependencies]\nbundle={path="../bundle"}\n')
        f=ws/'Cargo.toml';f.write_text(f.read_text().replace('"app"]','"app","facade"]'))
        f=ws/'app/Cargo.toml';f.write_text(f.read_text().replace('bundle={path="../bundle"}','facade={path="../facade"}'))
    ext='facade' if '-expn-' in case else 'bundle'
    error=ws/'outside-error.rs'
    error.write_text(f'fn main() {{ let _ = {ext}::Public {{}}; let _ = {ext}::gg(7); }}\n')
    roster=root/'record-argv';roster.write_text('''#!/usr/bin/env python3
import os,sys
from pathlib import Path
a=sys.argv[1:]
if '--crate-name' in a:
 (Path(os.environ['CALLS'])/(str(os.getpid())+'.argv')).write_bytes(b'\\0'.join(map(os.fsencode,a)))
os.execv(a[0],a)
''');roster.chmod(0o755)
    env=dict(os.environ, RUSTUP_HOME=str(args.rustup), RUSTUP_TOOLCHAIN='ohm', RUSTUP_AUTO_INSTALL='0',
             CARGO_HOME=str(root/'cargo-home'), CARGO_INCREMENTAL='1', CARGO_BUILD_JOBS='4', GIT_OPTIONAL_LOCKS='0',
             RUSTC=str(args.sysroot/'bin/rustc'), RUSTC_WRAPPER=str(roster))
    for key in ('RUSTFLAGS','CARGO_ENCODED_RUSTFLAGS','RUSTC_WORKSPACE_WRAPPER'):
        env.pop(key,None)
    soname, = (args.sysroot/'lib').glob('librustc_driver*.so')
    ns=['taskset','-c',args.cpu,'bwrap','--ro-bind','/','/','--dev','/dev','--proc','/proc','--tmpfs','/tmp',
        '--bind',str(root),str(root),'--ro-bind',str(args.cargo),str(args.sysroot/'bin/cargo'),
        '--ro-bind',str(args.driver),str(soname),'--chdir',str(ws),'--']
    def command(rec, cmd, e=env):
        p=subprocess.run([*ns,*cmd],env=e,capture_output=True)
        (rec.with_suffix('.stdout.gz')).write_bytes(gzip.compress(p.stdout,mtime=0))
        (rec.with_suffix('.stderr.gz')).write_bytes(gzip.compress(p.stderr,mtime=0))
        return p
    def build(phase, store):
        target=root/(store+'-target');shared=root/(store+'-build')
        rec=root/phase;rec.mkdir(); calls=rec/'calls'; calls.mkdir()
        e=dict(env,CARGO_TARGET_DIR=str(target),CARGO_BUILD_BUILD_DIR=str(shared),CALLS=str(calls))
        cargo=[str(Path.home()/'.cargo/bin/cargo'),'+ohm','build','--offline','--message-format=json','-p','app']
        r=command(rec/'cargo',cargo,e)
        artifacts={m['target']['name']:m for m in records(r.stdout) if m['reason']=='compiler-artifact'}
        child=[]
        for f in calls.glob('*.argv'):
            av=f.read_bytes().split(b'\0'); name=av[av.index(b'--crate-name')+1].decode()
            if name!='___':child.append([name, b'-Zlink-only' in av or b'link-only' in av])
        obs={'cargo_exit':r.returncode,'actual_children':sorted(child),'reported_fresh':{k:v['fresh'] for k,v in artifacts.items()}}
        hashes=sorted(target.rglob('lib-leaf.public-api-hash'))
        if hashes:obs['leaf_public_hash']=json.loads(hashes[0].read_bytes())
        if r.returncode==0:
            exe=artifacts['app']['executable'];p=command(rec/'run-app',[exe],e)
            obs['app']={'exit':p.returncode,'out':p.stdout.decode().splitlines(),'elf':digest(Path(exe).read_bytes())}
        else:
            obs['cargo_failure']=[s[:200] for s in r.stderr.decode(errors='replace').splitlines() if any(x in s for x in ['unstable fingerprints','missing source file','panicked at','Missing SyntaxContext'])]
        locs={}
        for k in ('leaf','bundle','facade'):
            if k not in artifacts:continue
            fs={Path(x).suffix:Path(x) for x in artifacts[k]['filenames'] if Path(x).suffix in ('.rlib','.rmeta')}
            if '.rlib' in fs:locs[k]=fs
        obs['artifacts']={k:{ext:digest(p.read_bytes()) for ext,p in files.items()} for k,files in locs.items()}
        return rec,obs,locs
    def outside(rec,obs,paths):
        if ext not in paths:return
        # Supply only rlibs from this exact run. One empty new output directory per invocation prevents caller-side incremental reuse.
        e=dict(env);e.pop('RUSTC_WRAPPER',None)
        out=rec/'outside';out.mkdir()
        cmd=[str(Path.home()/'.cargo/bin/rustc'),'+ohm','--edition=2024','--crate-name','external_witness','--sysroot',str(args.sysroot),
             '--extern',f"{ext}={paths[ext]['.rlib']}",'-C','metadata=independent-release-control','-C','opt-level=1','-C','debuginfo=line-tables-only']
        for fs in paths.values():cmd.extend(['-L',f"dependency={fs['.rlib'].parent}"])
        for label,source in [('good',ws/'app/src/main.rs'),('error',error)]:
            p=command(rec/('outside-'+label),[*cmd,'--error-format=json',str(source),'-o',str(out/'caller')],e)
            diags=[{'level':m['level'],'code':(m.get('code') or {}).get('code'),'message':m['message'],
                    'spans':m['spans'],'children':m['children']} for m in records(p.stderr) if m.get('$message_type')=='diagnostic']
            ent={'exit':p.returncode,'diagnostics':diags,'ice':any(s in p.stderr for s in [b'unstable fingerprints',b'unexpectedly panicked',b'missing source file'])}
            if label=='good' and p.returncode==0:
                x=command(rec/'outside-run',[str(out/'caller')],e);ent.update(run=x.returncode,output=x.stdout.decode().splitlines(),elf=digest((out/'caller').read_bytes()))
            obs['outside_'+label]=ent
    rows=[]
    for phase,edit,caller in [('prime',False,False),('change',True,False),('caller',True,True),('restore',False,True),('caller-restore',False,False)]:
        fixture(ws,case,edit,caller)
        rec,warm,p=build(phase,'warm')
        if phase in ('caller','caller-restore'):
            outside(rec,warm,p)
            ref,clean,cp=build(phase+'-clean',phase+'-clean');outside(ref,clean,cp)
        else:clean=None
        rows.append({'phase':phase,'warm':warm,'clean':clean})
        (root/'observations.json').write_text(json.dumps(rows,sort_keys=True,indent=2)+'\n')
    return rows

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--sysroot',type=Path,required=True);p.add_argument('--rustup',type=Path,required=True)
    p.add_argument('--cargo',type=Path,required=True);p.add_argument('--driver',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--cpu',default='0-3')
    p.add_argument('cases',nargs='*',default=CASES)
    a=p.parse_args();a.out=a.out.absolute();a.out.mkdir(exist_ok=True)
    for f in ['sysroot','rustup','cargo','driver']:setattr(a,f,getattr(a,f).absolute())
    assert (a.rustup/'toolchains/ohm').resolve()==a.sysroot.resolve()
    (a.out/'toolchain.json').write_text(json.dumps(compiler_identity(a),indent=2)+'\n')
    for case in a.cases:
        assert case in CASES
        rows=verify_case(a,a.out/case,case)
        print(case,[(r['phase'],r['warm']['cargo_exit'], r['warm'].get('outside_good',{}).get('exit'),
                    r['warm'].get('outside_error',{}).get('exit'), r['clean']['cargo_exit'] if r['clean'] else None)for r in rows],flush=True)
if __name__=='__main__':main()
