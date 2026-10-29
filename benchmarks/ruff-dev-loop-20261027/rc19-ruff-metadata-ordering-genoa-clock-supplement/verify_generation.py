"""Reopen both selected Ruff product sets only after an adjacent pair finishes."""
from pathlib import Path
import hashlib, json, os, re, subprocess, sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/"admin-pgo-ops"))
from admin_ctl import R, live, work, proxy, env, sha, save, lock, old, new, cohort, require_source, typed
HERE=Path(__file__).resolve().parent
QA_MANIFEST="ed552d17bd94cc464d4eea6addaa2427225cd3ddd8ef2caba9dfe805ab250b6d"
OLD_PROTOCOL="5ef08a85860887a0eb92c12bf51174a6264ab806989f807e2fb9c2f78bfb274e"
EXCEPTION_NAMES={"libruff_linter-b6d3cd0bff22fbfa.rmeta","libruff_source_file-e58055ef29b03e8c.rlib","libruff_python_trivia-93ff9c45c823e6e1.rlib","libruff_text_size-48bf6883a673a9b0.rlib"}
get=lambda p:json.loads(p.read_bytes())
hash_bytes=lambda b:hashlib.sha256(b).hexdigest()
def root_info(f):
    q=subprocess.run([str(proxy.parent/"rustc"),"+ohm","-Zls=root",str(f)],cwd=R,env=env(),capture_output=True,timeout=25)
    assert q.returncode==0,(f.name,q.stderr)
    creds=re.search(rb"^private hash ([a-f0-9]{32}) stable_crate_id StableCrateId\(([0-9]+)\)\s*\npublic_hash ([a-f0-9]{32})",q.stdout,re.M)
    assert creds,(f.name,q.stdout[:600])
    return q.stdout,tuple(v.decode() for v in creds.groups())
def nonce(archive):
    assert archive.startswith(b"!<arch>\n");pos=8;rec=None
    while pos<len(archive):
        header=archive[pos:pos+60];assert header[-2:]==b"`\n"
        n=int(header[48:58]);data=archive[pos+60:pos+60+n]
        if header[:16].strip()==b"//":
            assert rec is None
            obj=[x.removesuffix(b"/") for x in data.splitlines() if x.endswith(b".rcgu.o/")]
            found=[re.fullmatch(rb".+[.]([0-9a-z]{7})[.]rcgu[.]o",s) for s in obj]
            assert obj and all(found);values={x.group(1) for x in found}
            assert len(values)==1;rec=next(iter(values))
        pos+=60+n+n%2
    assert pos==len(archive) and rec;return rec
def copy_raw(p,stash,h):
    stash.mkdir(parents=True,exist_ok=True);dest=stash/h
    if dest.is_file():assert sha(dest)==h;return
    with p.open("rb") as a,dest.open("xb") as b:
        while part:=a.read(1024*1024):b.write(part)
    assert sha(dest)==h
def validate_products(reference,output_relpaths,raw_root):
    changes={};allfiles={}
    assert set(reference)==output_relpaths and len(reference)==597
    preserved=R/"same-donor-actual-products/replicated";idx=get(preserved/"receipt.json")
    for rel,oldinfo in reference.items():
        p=live/rel;assert not Path(rel).is_absolute() and ".." not in Path(rel).parts and p.is_file() and not p.is_symlink()
        rec={"bytes":p.stat().st_size,"sha256":sha(p)};h=rec['sha256'];allfiles[rel]=rec
        if p.name not in EXCEPTION_NAMES:
            assert rec==oldinfo,(rel,oldinfo,rec);continue
        basis=oldinfo['sha256'];g=preserved/idx["objects"][basis]["file"]
        assert sha(g)==basis and rec['bytes']==oldinfo['bytes']
        prior=g.read_bytes();actual=p.read_bytes();assert hash_bytes(actual)==h
        if p.suffix==".rmeta":
            _,creds=root_info(p);sg=idx['objects'][basis]['root']['credentials']
            assert creds[1:]==tuple(sg[1:])==("11340730689575692863","e80292fb4eb85b137360e3f0c75d6d62")
            off=12_165_345;raw=bytes.fromhex(creds[0])[::-1];s0=bytes.fromhex(sg[0])[::-1]
            assert len(actual)==12_166_054 and actual[off:off+16]==raw and prior[off:off+16]==s0
            assert actual[:off]==prior[:off] and actual[off+16:]==prior[off+16:]
            proof={"private":creds[0],"stable_id":creds[1],"public":creds[2],"offset":off}
        else:
            left=nonce(prior);right=nonce(actual)
            assert prior.replace(left,right)==actual,(p.name,"non-name archive difference")
            proof={"baseline_component":left.decode(),"raw_component":right.decode(),"literal_occurrences":actual.count(right)}
        copy_raw(p,raw_root,h);changes[p.name]={"reference_sha256":basis,"actual":rec,"check":proof}
    assert changes.keys()==EXCEPTION_NAMES and len(allfiles)==597
    return allfiles,changes
def actual_reader(d,top):
    geo=get(R/"real-linter-readers-v1/geometry.json")
    use=next(iter(geo['cases'].values()))['units'];ms={}
    for label in ('ruff_graph','ruff_workspace','ruff_linter'):
        f=live/use[label]['rel'];assert f.is_file() and top[use[label]['rel']]['sha256']==sha(f)
        stdout,ident=root_info(f);(d/(label+".root.txt")).write_bytes(stdout)
        line=[v.decode() for v in stdout.splitlines() if b" ruff_linter-" in v and b" hash " in v]
        if label!='ruff_linter':assert len(line)==1 and " hash e80292fb4eb85b137360e3f0c75d6d62 " in line[0],(label,line)
        ms[label]={"raw":sha(f),"credentials":ident,"linter_dependency":line}
    poss=set()
    for row in geo['actual_search_flags']:
        k,path=row.split("=",1)
        if k=='dependency':
            assert Path(path).is_relative_to(live)
            poss.update(p for p in Path(path).glob("libruff_linter-*") if p.suffix in (".rmeta",".rlib",".so"))
    assert poss=={live/use['ruff_linter']['rel']}
    src=d/"current.rs";out=d/"libgenoa_reader.rmeta";calls={}
    cmd=[str(proxy.parent/"rustc"),"+ohm","--edition=2024","--crate-type=lib","--crate-name","genoa_reader","--error-format=json","--emit=metadata"]
    for label in ('ruff_linter','ruff_workspace','ruff_graph'):cmd+=["--extern",f"{label}={live/use[label]['rel']}"]
    for f in geo['actual_search_flags']:cmd+=["-L",f]
    cmd+=["-Cincremental="+str(d/"inc"),str(src),"-o",str(out)]
    for stage,source,code in (("valid","natural.rs",None),("invalid","bad.rs","E0609"),("recovered","natural.rs",None)):
        src.write_bytes((HERE/source).read_bytes());assert sha(src)==sha(HERE/source)
        if out.exists():out.rename(d/(stage+"-previous.rmeta"))
        q=subprocess.run(cmd,cwd=d,env=env(),capture_output=True,timeout=40)
        (d/(stage+".out")).write_bytes(q.stdout);(d/(stage+".err")).write_bytes(q.stderr)
        errs=[j['code']['code'] for x in q.stderr.splitlines() if x.startswith(b'{') for j in [json.loads(x)] if j.get('level')=='error' and j.get('code')]
        assert errs==([] if code is None else [code]) and q.returncode==int(code is not None) and out.is_file()==(code is None),(stage,q.stderr[-1400:])
        calls[stage]={"status":q.returncode,"codes":errs,"source":sha(src),"stderr":hash_bytes(q.stderr),"output":sha(out) if out.is_file() else None}
    assert calls['valid']['output']==calls['recovered']['output']
    return {"inputs":ms,"argv":cmd,"calls":calls}
def measure_generation(d,direction,admitted,source_rev,raw_store,typed_file):
    d.mkdir();v=admitted["endpoints"][direction]
    require_source(source_rev)
    gold=R/v['reference'];assert sha(gold)==v['reference_sha256'];ref=get(gold)
    rows,units=typed(typed_file)
    assert len(units)==510 and rows[-1]=={"reason":"build-finished","success":True}
    rel={str(Path(f).relative_to(live)) for u in units for f in u["filenames"]}
    files,ex=validate_products(ref,rel,raw_store)
    save(d/"raw-products.json",files);save(d/"raw-exception-files.json",ex)
    actual={p:sha(work/p) for p in cohort()[source_rev]};assert len(actual)==30 and sha(work/"Cargo.lock")==lock
    assert actual==v['source_files'];save(d/"source-files.json",actual)
    reader=actual_reader(d,files);save(d/"reader.json",reader)
    result={"raw":sha(d/"raw-products.json"),"sources":sha(d/"source-files.json"),"exceptions":sha(d/"raw-exception-files.json"),"reader":sha(d/"reader.json"),"mode":"ordinary-current","source":source_rev}
    save(d/"accepted.json",result)
