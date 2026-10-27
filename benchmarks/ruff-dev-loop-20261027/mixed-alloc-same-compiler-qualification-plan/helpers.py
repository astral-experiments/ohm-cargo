from pathlib import Path
import collections, hashlib, json, os, re, shutil, signal, subprocess, sys, tarfile, tomllib
from common import P, RUFF, TARGET, SHARED, CARGO_HOME, FROZEN, dump, load, need, sha
from state import H, BASE, PLAN, WASM, gate_free, source_clean, inputs, seed, set_source, source_binds
from namespace import skeleton, spawn_args
from processes import records
origin='registry+https://github.com/rust-lang/crates.io-index'
def dest(mode,tag,name):return out/'receipts'/mode/tag/name

def state(mode,tag):return out/'state'/mode/tag

def checked_launch(cmd):
    p=subprocess.Popen(cmd,start_new_session=True)
    try:
        while True:
            try:p.wait(timeout=3);break
            except subprocess.TimeoutExpired:gate_free(out)
        need(p.returncode==0,('worker returned',p.returncode,cmd[-11:]))
    except BaseException:
        if p.poll() is None:os.killpg(p.pid,signal.SIGTERM);p.wait(timeout=30)
        raise
    gate_free(out)

def command(st,arm,extra=()):
    subject=b['arms'][arm];prefix=spawn_args(mount,out,st,st/'registry-home',[],Path(subject['cargo']),Path(subject['driver']));at=prefix.index('--')
    return [*prefix[:at],*source_binds(st),*extra,*prefix[at:]]

def call(mode,state_tag,arm,level,name,edit,force=None):
    st=state(mode,state_tag);d=dest(mode,state_tag,name);d.parent.mkdir(exist_ok=True,parents=True);need(not d.exists(),('duplicate command',d))
    set_source(st,fixture,edit);cmd=[*command(st,arm),sys.executable,'-B',H/'worker.py','--arm',arm,'--mode',mode,'--state','edited' if edit else 'original','--phase',level,'--out',str(d),'--manifest',str(fixture/'manifest.json'),'--binding',str(binding)]
    if force:cmd+=['--force-from',str(force/'receipt.json')]
    known=st/'recorded-recipe-paths.json'
    if known.is_file():cmd+=['--known-recipes',str(known)]
    checked_launch(cmd);row=load(d/'receipt.json')
    if not known.exists() and (arm!='C' or len(row['recipe_after'])>=2):dump(known,sorted(row['recipe_after']))
    return row

def train(mode,tag,arm,edited=False):
    first=call(mode,tag,arm,'cold','cold',edited);need(first['product']['dirty'],'cold state')
    for i in range(1,5):
        row=call(mode,tag,arm,'train',f'train-{i}',edited)
        if row['fresh_units']==row['unit_count'] and not row['processes']['jobs']:break
    else:raise ValueError(('training never settled',mode,tag))
    fresh=call(mode,tag,arm,'detailed-fresh','initial-fresh',edited)
    need(fresh['product']['structural_roster']==first['product']['structural_roster'],'changed initial roster')
    return first,fresh

def check_row(r,ref):
    need(r['product']['structural_roster']==ref['product']['structural_roster'] and r['product']['messages']==ref['product']['messages'] and r['product']['diagnostics']==ref['product']['diagnostics'], ('own state/diagnostics changed',r['arm'],r['mode'],r['state']))

def storage_bytes(path):return int(subprocess.check_output(['du','-s','-B1',path]).split()[0])

def current_rows(d):return [json.loads(s) for s in (d/'stdout').read_bytes().splitlines() if s]

def clone(mode,event):
    src=state(mode,'C');st=state(mode,'forced-C');gate_free(out,int(storage_bytes(src)*1.12));need(not st.exists(),st)
    subprocess.run(['cp','-a','--reflink=auto','--',src,st],check=True)
    index={}
    for row in current_rows(event):
        if row.get('reason')!='compiler-artifact':continue
        for path in map(Path,row['filenames']):
            unit=next((n for n,p in [('target',TARGET),('shared',SHARED)] if path.is_relative_to(p)),None)
            need(unit is not None,('external advertised file',path))
            rel=path.relative_to(TARGET if unit=='target' else SHARED);base=src/unit/rel;copy=st/unit/rel
            need(base.is_file() and copy.is_file() and not base.samefile(copy),('private output not copied',base,copy))
            key=str(path)
            if key not in index:
                left,right=base.stat(),copy.stat()
                need((left.st_size,left.st_mtime_ns,left.st_mode,sha(base))==(right.st_size,right.st_mtime_ns,right.st_mode,sha(copy)),('output clone mismatch',path))
                index[key]={'sha256':sha(base),'mode':left.st_mode,'mtime_ns':left.st_mtime_ns,'different_inodes':True}
    need(len(index)>=PLAN['endpoints'][mode]['expected_units'],('incomplete clone inventory',mode,len(index)))
    dump(out/('cloned-artifacts-'+mode+'.json'),index)
    return st
def regulars(p):
    return sorted(f for f in p.rglob("*") if f.is_file() or f.is_symlink())

def unit_of(logical):
    f = Path(logical)
    if not f.is_relative_to(TARGET): return None
    rel = f.relative_to(TARGET)
    parts = rel.parts
    if len(parts) < 8 or parts[:3] != ("debug","build","workspaces") or parts[7] != "out": return None
    assert re.fullmatch("[0-9a-f]{16}", parts[3]) and re.fullmatch("v2-[0-9a-f]+-all-native-all", parts[4])
    assert re.fullmatch("[0-9a-f]{16}", parts[6])
    return Path(*parts[:7])

def units(stdout):
    reg, local, all_origins = {}, {}, []
    for line in stdout.read_bytes().splitlines():
        row = json.loads(line)
        if row["reason"] not in ("compiler-artifact", "build-script-executed"): continue
        package = row["package_id"]
        files = row.get("filenames") or [row["out_dir"]]
        all_origins.append([row["reason"], package, files])
        is_reg = package.startswith(origin + "#")
        assert is_reg or package.startswith("path+file:"), package
        for f in files:
            u = unit_of(f)
            if not u:
                assert not is_reg, (f,package)
                continue
            if is_reg:
                assert u.parts[-2] == package.split("#")[1].split("@")[0], (u,package)
            d = reg if is_reg else local
            assert d.get(u,package) == package
            d[u] = package
    assert not reg.keys() & local.keys() and len(reg) > 300 and local
    return reg, local, all_origins

def verify_packages(package_ids,registry):
    lock = tomllib.loads((RUFF/"Cargo.lock").read_text())
    locked = {(p["name"],p["version"]):p["checksum"] for p in lock["package"] if p.get("source")==origin}
    out={}
    for pid in sorted(package_ids):
        name,ver = pid.split("#")[1].split("@")
        req=locked[(name,ver)]
        archive, = (registry/"registry/cache").glob(f"*/{name}-{ver}.crate")
        root, = (registry/"registry/src").glob(f"*/{name}-{ver}")
        assert sha(archive)==req
        h=hashlib.sha256()
        files=0
        with tarfile.open(archive) as tf:
            for m in tf:
                if m.isdir(): continue
                assert m.isfile(), (pid,m.name)
                rel=Path(m.name).relative_to(root.name)
                assert ".." not in rel.parts
                extracted=root/rel
                assert extracted.is_file() and not extracted.is_symlink()
                dg=hashlib.file_digest(tf.extractfile(m),"sha256").hexdigest()
                assert sha(extracted)==dg,(pid,rel)
                h.update(os.fsencode(rel)+b"\0"+dg.encode()+b"\n");files+=1
        out[pid]={"crate_sha256":req,"extracted_files":files,"files_sha256":h.hexdigest()}
    return out

def filtered_argv_set(reg, origins, ref, require_full):
    compiled={unit_of(p) for reason,pkg,files in origins if reason=="compiler-artifact" and pkg.startswith(origin+"#") for p in files}
    run_dirs={unit_of(p) for reason,pkg,files in origins if reason=="build-script-executed" and pkg.startswith(origin+"#") for p in files}
    out={};helpers=[]
    for _, img, qa in records(ref):
        if Path(img).name!="rustc" or "--crate-name" not in qa or "--out-dir" not in qa:continue
        u=unit_of(qa[qa.index("--out-dir")+1])
        if u not in reg: continue
        role=qa[qa.index("--crate-name")+1]
        srcs=[x for x in qa if x.endswith(".rs") and not x.startswith("-")]
        if u in run_dirs and u not in compiled:
            assert "-" in qa or srcs,(role,qa)
            assert all(Path(p).is_relative_to(CARGO_HOME/"registry/src") or Path(p).is_relative_to(TARGET/u/"out") for p in srcs),(u,srcs)
            helpers.append({"crate_name":role,"package":reg[u],"build_script_run":str(u),"argv":qa})
            continue
        assert u in compiled,("unattributed rustc",u,role)
        assert srcs and all(Path(s).is_relative_to(CARGO_HOME/"registry/src") for s in srcs),(role,srcs)
        for i,x in enumerate(qa[:-1]):
            if x!="--extern" or "=" not in qa[i+1]:continue
            n,p=qa[i+1].split("=",1)
            if Path(p).is_absolute():
                assert unit_of(p) in reg,("registry-to-non-registry extern",u,n,p)
        out[str(u)]={"crate_name":role,"argv":qa}
    assert (not require_full or len(out)>300) and any(v["crate_name"]=="get_size_derive2" for v in out.values())
    return {"compilation":out,"registered_build_script_rustc_probes":helpers}

def project(reg, out, source):
    inv={}
    for u,pid in sorted(reg.items()):
        d=out/u;src=source/u;assert not d.exists() and src.is_dir() and not src.is_symlink()
        d.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["cp","-a","--reflink=auto","--",src,d],check=True)
        for f in regulars(src):
            q=d/f.relative_to(src); key=str(q.relative_to(out))
            assert key not in inv
            if f.is_symlink():
                assert q.is_symlink() and q.readlink()==f.readlink() and not f.readlink().is_absolute()
                assert f.resolve().is_relative_to(src) and q.resolve().is_relative_to(d), (u, f, q)
                inv[key]={"package":pid,"link":os.readlink(f)}
            else:
                a,aa=f.stat(),q.stat(); h=sha(f)
                assert (a.st_size,a.st_mtime_ns,a.st_mode)==(aa.st_size,aa.st_mtime_ns,aa.st_mode) and not f.samefile(q) and sha(q)==h
                inv[key]={"package":pid,"size":a.st_size,"mtime_ns":a.st_mtime_ns,"sha256":h,"independent_inode":True}
    assert set(inv)=={str(p.relative_to(out)) for p in regulars(out)}
    return inv
