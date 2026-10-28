"""Make real Serde's existing imported-span derive change actual registry Ron serialization."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys

def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def snapshot(p):
    s=p.stat();return {'size':s.st_size,'sha256':sha(p),'mtime_ns':s.st_mtime_ns,'ctime_ns':s.st_ctime_ns,'dev':s.st_dev,'ino':s.st_ino}

def run(root):
    case=root/'serde-upstream';case.mkdir();ws=case/'source'; ws.mkdir();(ws/'src').mkdir();(ws/'.cargo').mkdir()
    shutil.copyfile(root/'registry/source/.cargo/config.toml',ws/'.cargo/config.toml')
    shutil.copyfile(root/'registry/source/Cargo.lock',ws/'Cargo.lock')
    shutil.copytree(root/'vendor/serde_derive-1.0.229',ws/'upstream')
    (ws/'Cargo.toml').write_text('[package]\nname="observe_ron_serde"\nversion="0.0.0"\nedition="2021"\n[dependencies]\nron="=0.12.0"\n[profile.dev]\nopt-level=1\ndebug="line-tables-only"\n[patch.crates-io]\nserde_derive={path="upstream"}\n')
    (ws/'src/main.rs').write_text('fn main() { let value=ron::extensions::Extensions::IMPLICIT_SOME; println!("{}",ron::ser::to_string_pretty(&value,ron::ser::PrettyConfig::new().struct_names(true)).unwrap()); }\n')
    path=ws/'upstream/src/ser.rs';original=path.read_bytes()
    from_=b'#func(__serializer, #type_name, #field_expr)';to=b'#func(__serializer, if #type_name == "Extensions" { "ChangedExtensions" } else { #type_name }, #field_expr)'
    assert original.count(from_)==1;changed=original.replace(from_,to);baseline={};rows=[]
    def build(label,expected,state_name='warm'):
        state=case/state_name;state.mkdir(exist_ok=True);out=case/label;out.mkdir()
        env={k:v for k,v in os.environ.items() if not k.startswith(('RUST','CARGO','OHM_'))}
        env.update(RUSTUP_HOME=str(root/'rustup'),RUSTUP_AUTO_INSTALL='0',CARGO_NET_OFFLINE='true',CARGO_TERM_COLOR='never',PATH=str(Path.home()/'.cargo/bin')+':/usr/local/bin:/usr/bin:/bin',CARGO_TARGET_DIR=str(state/'target'),CARGO_BUILD_BUILD_DIR=str(state/'shared'),CARGO_HOME=str(state/'cargo'))
        argv=['cargo','+ohm','build','--offline','-j8','--message-format=json']
        if label!='cold':argv+=['--locked']
        with (out/'stdout').open('xb') as so,(out/'stderr').open('xb') as se:
            cmd=subprocess.run(['strace','-ff','-qq','-e','trace=execve','-s','65535','-o',str(out/'trace')]+argv,cwd=ws,env=env,stdout=so,stderr=se,timeout=160)
        if cmd.returncode: raise RuntimeError((label,cmd.returncode,(out/'stderr').read_text()[-1400:],(out/'stdout').read_text()[-2000:]))
        records=[json.loads(i) for i in (out/'stdout').read_bytes().splitlines()]
        arts={r['target']['name']:r for r in records if r.get('reason')=='compiler-artifact' and r['target']['kind'] in (['lib'],['proc-macro'],['bin'])}
        product=Path(arts['observe_ron_serde']['executable']);value=subprocess.check_output([product],text=True).strip()
        assert value.startswith(expected+'('), (label,value,expected)
        if baseline: assert value==baseline['A'].replace('Extensions(',expected+'(',1),(value,baseline)
        else: baseline['A']=value
        assert not arts['ron']['fresh'] and arts['ron']['features']==['default','std'] and arts['ron']['package_id'].startswith('registry+')
        assert arts['serde_derive']['package_id'].startswith('path+')
        dso,=map(Path,arts['serde_derive']['filenames']);assert dso.is_file() and dso.resolve().is_relative_to(state)
        dep,=[p for p in (state/'target').rglob('ron-*.d') if p.parent.name=='out'];enc=dep.parent.parent/'fingerprint/dep-lib-ron'
        assert b'ohm-foreign-span-bytes' in dep.read_bytes() and enc.read_bytes()[-33]==0 and enc.read_bytes()[-41:-37]==b'OBS1'
        full=[];links=[];trace={}
        for f in sorted(out.glob('trace.*')):
            trace[f.name]=sha(f)
            for line in f.read_bytes().splitlines():
                if not line.endswith(b'= 0') or b'execve(' not in line:continue
                if b'/bin/rustc",' in line and b'"--crate-name", "' in line:
                    name=line.split(b'"--crate-name", "',1)[1].split(b'"',1)[0].decode()
                    if name!='___' and b'"-Zlink-only"' not in line:full.append(name)
                if b'/bin/wild-ld/ld.bfd",' in line:links.append(hashlib.sha256(line).hexdigest())
        assert full.count('ron')==1 and ('serde_derive' in full)==(not arts['serde_derive']['fresh'])
        rows.append({'phase':label,'physical_full':sorted(full),'stock_wild':len(links),'program':value,'source_sha256':sha(path),'program_sha256':sha(product),
            'dso':snapshot(dso),'dso_fresh':arts['serde_derive']['fresh'],'ron_marker':True,'ron_dep_info':sha(dep),'encoded_dep_info':sha(enc),
            'trace_sha256':trace,'rust_diagnostics':[m['message']['level'] for m in records if m.get('reason')=='compiler-message']})
        print(label,value,sorted(full),flush=True);return dso
    build('cold','Extensions');build('unchanged','Extensions')
    path.write_bytes(changed);dso=build('true-edit','ChangedExtensions');assert not rows[-1]['dso_fresh']
    b=dso.read_bytes();build('true-edit-repeat','ChangedExtensions');assert rows[-1]['dso_fresh']
    build('independent-edited','ChangedExtensions','clean-changed')
    path.write_bytes(original);dso_a=build('restore','Extensions');assert not rows[-1]['dso_fresh'] and dso==dso_a
    a=dso.read_bytes();assert a!=b;sz=max(len(a),len(b));a=a.ljust(sz,b'\0');b=b.ljust(sz,b'\0')
    orig=dso.stat();mode=stat.S_IMODE(orig.st_mode);tmp=dso.with_name(dso.name+'.private');tmp.write_bytes(a);tmp.chmod(mode);tmp.replace(dso);os.utime(dso,ns=(orig.st_atime_ns,orig.st_mtime_ns));assert dso.stat().st_nlink==1
    cinputs=[]
    def install(payload):
        prev=snapshot(dso)
        with dso.open('r+b',buffering=0) as f: assert f.write(payload)==sz;os.fsync(f.fileno())
        os.utime(dso,ns=(orig.st_atime_ns,orig.st_mtime_ns));n=snapshot(dso)
        assert all(prev[k]==n[k] for k in ('ino','dev','size','mtime_ns'));cinputs.append(n)
    build('same-size-A','Extensions');assert rows[-1]['dso_fresh']
    install(b);build('backdated-external-B','ChangedExtensions');assert rows[-1]['dso_fresh']
    build('unchanged-external-B','ChangedExtensions');assert rows[-1]['dso_fresh']
    install(a);build('backdated-external-A','Extensions');assert rows[-1]['dso_fresh']
    build('independent-restored','Extensions','clean-restored')
    result={'program_baseline':baseline['A'],'rows':rows,'artifact_replacements':cinputs,'padding_bytes':[sz-len(dso_a.read_bytes().rstrip(b'\0')),sz-len(b.rstrip(b'\0'))],'note':'The two synthetic on-disk producer variants have identical length, inode and mtime in the last alternating commands. ctime and SHA differ. Real upstream source edit is independent and its input is restored before any artifact mutation.'}
    # The original two lengths before padding are recorded in the authentic edit and restore rows.
    result.pop('padding_bytes')
    (case/'complete.json').write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
if __name__=='__main__':run(Path(sys.argv[1]))
