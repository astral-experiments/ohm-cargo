"""Synchronize publication of a new proc-macro library or rmeta with its already expanded old tokens."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

HERE = Path(__file__).resolve().parent
HOLD = '''extern crate proc_macro;
#[proc_macro]
pub fn native_offset(input: proc_macro::TokenStream) -> proc_macro::TokenStream {
    let marker = input.into_iter().next().unwrap().span();
    format!("{:?}", format!("{marker:?}")).parse().unwrap()
}
#[proc_macro]
pub fn wait_value(input: proc_macro::TokenStream) -> proc_macro::TokenStream {
    let marker = input.into_iter().next().unwrap().span();
    let column = marker.column();
    let _actual_observer = format!("{marker:?}");
    let seen = (if column < 256 { "17" } else { "29" }).to_string();
    let base = std::path::PathBuf::from(std::env::var_os("OHM_SYNC_DIR").unwrap());
    assert!(matches!(seen.as_str(), "17" | "29"));
    if base.join("armed").is_file() {
        std::fs::write(base.join("observed"), &seen).unwrap();
        let start = std::time::Instant::now();
        while !base.join("release").is_file() {
            assert!(start.elapsed().as_secs() < 60);
            std::thread::sleep(std::time::Duration::from_millis(5));
        }
    }
    (if seen == "17" { "17u16" } else { "29i16" }).parse().unwrap()
}
'''
def sha(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()

def stat(p):
    s=p.stat()
    return dict(inode=s.st_ino,device=s.st_dev,bytes=s.st_size,mtime_ns=s.st_mtime_ns,sha256=sha(p))

def write(p,x):
    p.write_text(json.dumps(x,sort_keys=True,indent=2)+'\n')

def maps(pid,live):
    wanted=live.stat().st_ino
    included=[]
    for proc in Path('/proc').glob('[0-9]*/maps'):
        try: lines=proc.read_text().splitlines()
        except (FileNotFoundError,PermissionError,ProcessLookupError):continue
        found=[]
        for line in lines:
            parts=line.split(maxsplit=5)
            if len(parts)==6 and parts[4]==str(wanted) and parts[5]==str(live):
                found.append(parts[1])
        if found:
            included.append(dict(pid=int(proc.parent.name),permissions=sorted(found),exe=Path(os.readlink(proc.parent/'exe')).name))
    return included

def case(root,sdk,kind,stamp):
    root.mkdir();work=root/'workspace';shutil.copytree(HERE/'fixture',work)
    (work/'hold_probe/src/lib.rs').write_text(HOLD)
    main=work/'hold_direct/src/main.rs'
    original=main.read_text();assert original.count('fn main(){')==1
    if kind=='rmeta':
        call='race_extern::sample!(wait_value)'
        cmd='check'
    else:
        call='race_extern::sample!()'
        cmd='build'
    main.write_text('use hold_probe::wait_value;\n'+original.replace('fn main(){','fn main(){let _: u16 = '+call+';'))
    rustup=root/'rustup';(rustup/'toolchains').mkdir(parents=True);(rustup/'toolchains/ohm').symlink_to(sdk)
    env=dict(HOME=str(root),PATH=os.environ['PATH'],USER=os.environ.get('USER','dev-user'),
             RUSTUP_HOME=str(rustup),RUSTUP_AUTO_INSTALL='0',CARGO_HOME=str(root/'cargo-home'),
             CARGO_NET_OFFLINE='true',CARGO_BUILD_JOBS='4',OHM_SYNC_DIR=str(root),LANG='C.UTF-8',LC_ALL='C.UTF-8')
    run=lambda args:subprocess.run(args,cwd=work,env=env,check=True,capture_output=True,timeout=120)
    assert Path(run(['rustc','+ohm','--print','sysroot']).stdout.decode().strip()).samefile(sdk)
    control=root/'inputs';control.mkdir();live=control/('librace_extern.'+('so' if kind=='dso' else 'rmeta'))
    src=root/'race.rs';built=root/live.name;next_input=root/'replacement';defs={}
    for value,dst in [(17,live),(29,next_input)]:
        if kind=='dso':
            src.write_text('extern crate proc_macro;\n#[proc_macro]\npub fn sample(_:proc_macro::TokenStream)->proc_macro::TokenStream{"wait_value!('+str(value)+')".parse().unwrap()}\n')
            opts=['--crate-type','proc-macro','--emit=link']
        else:
            definition='#[macro_export] macro_rules! sample { ($gate:ident) => { $gate!(same_token) }; }'
            gap=' '*(256-len(definition)-4)
            active='  '+definition+'  ';hidden='/*'+definition+'*/'
            src.write_text((active+gap+hidden if value==17 else hidden+gap+active)+'\n')
            opts=['--crate-type','rlib','--emit=metadata']
        run(['rustc','+ohm','--crate-name','race_extern','-Cmetadata=fixed-race-payload','-Cdebuginfo=0',*opts,str(src),'-o',str(built)])
        shutil.copyfile(built,dst);shutil.copyfile(src,root/('source-'+str(value)+'.rs'))
        if value==17:shutil.copyfile(built,root/'original-product')
        defs[str(value)]={'product':sha(dst),'source':sha(src),'bytes':dst.stat().st_size}
    src.write_bytes((root/'source-17.rs').read_bytes())
    root_facts={}
    for k,path in [('old',live),('new',next_input)]:
        canonical=control/'alias' / 'librace_extern.rmeta';canonical.parent.mkdir(exist_ok=True);shutil.copyfile(path,canonical)
        root_info=run(['rustc','+ohm','-Zls=root',str(canonical)]).stdout.decode()
        (root/(k+'-rmeta-root.txt')).write_text(root_info)
        m=re.search(r'^private hash (\w+) stable_crate_id StableCrateId\((\d+)\)\s*\npublic_hash (\w+)',root_info,re.M)
        assert m,root_info[:500];root_facts[k]={'svh':m[1],'stable_id':m[2],'public_hash':m[3]}
    write(root/'origins.json',root_facts)
    env['CARGO_ENCODED_RUSTFLAGS']='--extern\x1frace_extern='+str(live)
    before=stat(live);after=None;rows={};opened=None
    (root/'armed').write_text('1');assert defs['17']['product']!=defs['29']['product']
    for phase in ('initial','repeat','again','clean'):
        place=root/('fresh-independent' if phase=='clean' else 'warm');target=place/'target';shared=place/'shared'
        env.update(CARGO_TARGET_DIR=str(target),CARGO_BUILD_BUILD_DIR=str(shared));rec=root/phase;rec.mkdir()
        argv=['strace','-ff','-qq','-s','65535','-e','trace=execve','-o',str(rec/'exec'),'cargo','+ohm',cmd,'-p','hold_direct','--offline','--message-format=json']
        with (rec/'stdout').open('wb') as so,(rec/'stderr').open('wb') as se:
            p=subprocess.Popen(argv,cwd=work,env=env,stdout=so,stderr=se)
            if phase=='initial':
                deadline=time.monotonic()+80
                while p.poll() is None and not (root/'observed').exists() and time.monotonic()<deadline:time.sleep(.01)
                if not (root/'observed').exists():
                    if p.poll() is None:p.kill()
                    p.wait();raise AssertionError(('no prior token was materialized',kind,p.returncode,(rec/'stdout').read_text()[-3500:],(rec/'stderr').read_text()[-800:]))
                assert (root/'observed').read_text()=='17'
                opened=maps(p.pid,live)
                if kind=='dso':assert any('r-xp' in r['permissions'] for r in opened),opened
                replacement=live.with_name(live.name+'.next');shutil.copyfile(next_input,replacement)
                if stamp=='preserved':os.utime(replacement,ns=(live.stat().st_atime_ns,before['mtime_ns']))
                os.replace(replacement,live);after=stat(live)
                assert before['inode']!=after['inode'] and after['sha256']==defs['29']['product']
                assert after['mtime_ns']==before['mtime_ns'] if stamp=='preserved' else after['mtime_ns']>before['mtime_ns']
                (root/'release').write_text('1');(root/'armed').unlink()
            rc=p.wait(timeout=120)
        events=[json.loads(l) for l in (rec/'stdout').read_bytes().splitlines()]
        assert events[-1]=={'reason':'build-finished','success':rc==0}
        arts=[x for x in events if x.get('reason')=='compiler-artifact'];focus=[x for x in arts if x['target']['name']=='hold_direct']
        diag=[{'code':(x['message'].get('code') or {}).get('code'),'message':x['message']['message']} for x in events if x.get('reason')=='compiler-message' and x['message']['level']=='error']
        success=[];claims={}
        for f in sorted(rec.glob('exec.*')):
            for line in f.read_text().splitlines():
                if not line.endswith(' = 0') or not line.startswith('execve('):continue
                path=re.match(r'execve\("([^"]+)"',line).group(1);name=Path(path).name
                if name=='rustc' and '"--crate-name"' in line:
                    m=re.search(r'"--crate-name", "([^"]+)"',line)
                    success.append({'process':'rustc','crate':m.group(1) if m else None,'probe':False,'argv_sha256':hashlib.sha256(line.encode()).hexdigest()})
                elif name in ('ld.bfd','wild','wild-ld'):success.append({'process':'linker','image':name})
        value=None
        if rc==0:
            assert len(focus)==1
            if cmd=='build':
                exe=Path(focus[0]['executable']);program=run([exe]);assert not program.stderr
                value=int(re.search(rb'(?m)^sample=(\d+)$',program.stdout)[1]);assert value in (17,29)
        deps=[f for d in (target,shared) for f in d.rglob('hold_direct*.d') if f.parent.name=='out' and b'ohm-foreign-span-bytes' in f.read_bytes()]
        fps=[f for d in (target,shared) for f in d.rglob('dep-bin-hold_direct') if b'OBS1' in f.read_bytes()]
        if len(deps)==1 and len(fps)==1:
            data=deps[0].read_bytes();encoded=fps[0].read_bytes();assert encoded[-41:-37]==b'OBS1'
            nested=[x for x in data.splitlines() if x.startswith(b'# ohm-observer-inputs-v1 ')];assert len(nested)<=1
            full=bytes.fromhex(nested[0].split()[3].decode()) if nested else data
            checks=[line.split(maxsplit=3)[:3] for line in full.splitlines() if line.startswith(b'# checksum:') and line.endswith(str(live).encode())]
            claims={'complete':bool(encoded[-33]),'nested':bool(nested),'source_depfile':sha(deps[0]),'cargo_fingerprint':sha(fps[0]),'extern_checksums':[[x.decode() for x in line] for line in checks]}
            (rec/'rustc.d').write_bytes(data);(rec/'cargo.fingerprint').write_bytes(encoded)
        dep_all=[f for d in (target,shared) for f in d.rglob('hold_direct*.d') if f.parent.name=='out']
        fp_all=[f for d in (target,shared) for f in d.rglob('dep-bin-hold_direct') if f.is_file()]
        if len(dep_all)==1:
            (rec/'rustc-any.d').write_bytes(dep_all[0].read_bytes());claims['dep_any_sha256']=sha(dep_all[0])
            claims['regular_observer_marker']=b'ohm-foreign-span-bytes' in dep_all[0].read_bytes();claims['untrackable_marker']=b'ohm-untrackable-foreign-span' in dep_all[0].read_bytes()
        if len(fp_all)==1:
            data=fp_all[0].read_bytes();(rec/'fingerprint-any').write_bytes(data);claims['encoded_any_sha256']=sha(fp_all[0])
            claims['obs_tag']=data[-41:-37]==b'OBS1';claims['record_version']=int(data[5]) if len(data)>6 else None
        assert rc in (0,101)
        if rc==101:assert diag,(kind,phase,rc)
        result={'exit':rc,'value':value,'diagnostics':diag,'unit_fresh':focus[0]['fresh'] if focus else None,'all_fresh':bool(arts) and all(x['fresh'] for x in arts),'native':success,'claims':claims,'trace_sha256':{f.name:sha(f) for f in sorted(rec.glob('exec.*'))}}
        rows[phase]=result;write(rec/'result.json',result)
    assert after==stat(live)
    if kind=='rmeta':assert rows['clean']['exit']==101 and any(x['code']=='E0308' for x in rows['clean']['diagnostics']),rows['clean']
    else:assert rows['clean']['value']==29,rows['clean']
    record={'case':kind,'rmeta_roots':root_facts,'timestamp':stamp,'old_token_before_replacement':17,'old':before,'replacement':after,'compiled':defs,'observed_old_maps':opened,'rows':rows}
    write(root/'complete.json',record)
    return {k:(v['exit'],v['value'],v['unit_fresh'],v['claims'].get('complete'),[i['code'] for i in v['diagnostics']]) for k,v in rows.items()}

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--root',type=Path,required=True);ap.add_argument('--sdk',type=Path,required=True);a=ap.parse_args()
    a.root.mkdir();all_cases={}
    for k in ('rmeta',):
        for stamp in ('preserved','current'):
            label=k+'-'+stamp
            result=case(a.root/label,a.sdk,k,stamp);all_cases[label]=result;print(label,result,flush=True)
    write(a.root/'complete.json',all_cases)
