import hashlib,json,os,struct,subprocess,sys
from pathlib import Path
root=Path(sys.argv[1]).resolve();sdk=Path(sys.argv[2]);hdr=lambda f:hashlib.file_digest(f.open("rb"),"sha256").hexdigest()
trunk=Path(__file__).resolve().parent
for work in sorted(root.glob("*-inc")):
    prior=json.loads((work/"results.json").read_bytes())
    p=work/"forced-same-operand";p.mkdir()
    subject=json.loads((work/"subjects.json").read_bytes());var=work.name.split("-")[1]
    tc=work/"rustup/toolchains/ohm";src=work/"workspace";app=src/"app/src/main.rs";data=src/"app/input.txt"
    app.write_text(app.read_text()+"const _: u8=2;\n")
    env={"PATH":"/home/dev-user/.cargo/bin:/usr/bin:/bin","HOME":str(work/"home"),"RUSTUP_HOME":str(work/"rustup"),"CARGO_HOME":str(work/"cargo-home"),"CARGO_TARGET_DIR":str(work/"target"),"CARGO_BUILD_BUILD_DIR":str(work/"shared"),"LANG":"C.UTF-8","LC_ALL":"C.UTF-8","CARGO_NET_OFFLINE":"true","CARGO_BUILD_JOBS":"2","CARGO_TERM_COLOR":"never","RUSTUP_AUTO_INSTALL":"0","RUSTC":str(work/"rustc-entry.py"),"RUSTC_BOOTSTRAP":"probe","LD_LIBRARY_PATH":str(tc/"lib"),"OHM_JOIN_COORD":str(work/"coord"),"OHM_JOIN_OPERATION":var,"OHM_FRONTEND":str((sdk/"bin/rustc").resolve()),"OHM_HOLDOUT_SYSROOT":str(sdk),"OHM_PRELOAD_PATH":str(trunk/"runtime/libjoin-diagnostic.so"),"OHM_JOIN_RECEIPT":str(work/"native.log"),"OHM_JOB_LOG":str(p/"jobs.jsonl"),"OHM_JOIN_SYMBOL":subject["symbol"],"OHM_JOIN_DELTA":subject["delta"],"OHM_JOIN_BYTES":subject["instruction"]}
    with (p/"stdout").open("w") as out,(p/"stderr").open("w") as err:subprocess.run(["cargo","+ohm","build","--offline","-p","app","--message-format=json"],cwd=src,env=env,stdout=out,stderr=err,check=True)
    rows=[j for l in (p/"stdout").read_text().splitlines() if (j:=json.loads(l)).get("reason")=="compiler-artifact"]
    a=next(j for j in rows if j["target"]["name"]=="app")
    dso=next(Path(n) for j in rows if j["target"]["name"]=="probe" for n in j["filenames"] if n.endswith(".so"))
    trace=[json.loads(l)[0] for l in (p/"jobs.jsonl").read_text().splitlines()]
    assert not a["fresh"] and trace==["app"] and hdr(dso)==prior[-1]["external_image"],(work,trace)
    text=subprocess.check_output([a["executable"]],text=True).splitlines()
    assert text==["value=29",*prior[-1]["readback"]],text
    replaced=json.loads((work/"synchronized/replacement.json").read_bytes())
    more=None
    if work.name.startswith("dso"):
        after=dso.read_bytes()
        m=b"OHMJ_UNIQUE_FIXTURE_29END"
        assert after.count(m)==1
        before=after.replace(m,m.replace(b"29",b"17"))
        assert hashlib.sha256(before).hexdigest()==replaced["before"]["sha"] and hashlib.sha256(after).hexdigest()==replaced["after"]["sha"]
        def sections(b):
            off=struct.unpack_from("<Q",b,40)[0];width,n,i=struct.unpack_from("<HHH",b,58)
            hdrs=[struct.unpack_from("<IIQQQQIIQQ",b,off+j*width) for j in range(n)]
            tab=hdrs[i];names=b[tab[4]:tab[4]+tab[5]]
            return {names[h[0]:].split(bytes([0]))[0].decode():hashlib.sha256(b[h[4]:h[4]+h[5]]).hexdigest() for h in hdrs if h[1]!=8}
        x,y=sections(before),sections(after);assert x.keys()==y.keys()
        changed=[k for k in x if x[k]!=y[k]]
        assert changed==[".rodata"] and x[".rustc"]==y[".rustc"]
        more=dict(changed_section=changed,metadata=x[".rustc"],byte_offsets=[i for i,(a,b) in enumerate(zip(before,after)) if a!=b])
    else: assert hdr(data)==replaced["after"]["sha"]
    out=dict(phase="forced-on-identical-replacement",fresh=a["fresh"],actual_rustc_crates=trace,captured_dso=hdr(dso),runtime=text,source_data_section=more)
    (p/"result.json").write_text(json.dumps(out,indent=2)+"\n")
    print(work.name,out,flush=True)
