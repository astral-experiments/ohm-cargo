"""Relink one retained example from the same objects under each small explicit stock Wild width."""
from pathlib import Path
import ast, hashlib, json, os, re, shutil, struct, subprocess

q=Path(__file__).resolve().parent
state=q/"coverage-v1";test=q/"elf-width-diagnostic-v1";test.mkdir(mode=0o700)
sdk=state/"sdk";name="only_bin_ex-547429450b4e677b"
old="ae9d4177eb75d37a3c23f30e8e46df0a499df3eb9207eaa4c95d376d6452d708"
new="1573893f42fac1a46a7700fec22cd0fd7ed25e7e1f84fcbb263f1f0d926f02c1"
def sha(f):
    with f.open("rb") as s:return hashlib.file_digest(s,"sha256").hexdigest()
def j(path):return json.loads(path.read_bytes())
def put(path,data):path.write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")
def cmds(path):
    for l in path.read_text(errors="replace").splitlines():
        m=re.fullmatch(r'execve\(("(?:[^"\\]|\\.)*"), (\[.*\]), (?:0x|NULL|\[).*= 0',l)
        if m:yield Path(ast.literal_eval(m[1])),ast.literal_eval(m[2])
def actual(key):
    match=[]
    for t in (state/key).glob("exec.*"):
        for exe,a in cmds(t):
            if exe.name=="rustc" and "--crate-name" in a and a[a.index("--crate-name")+1]=="only_bin_ex":
                assert exe.samefile(sdk/"bin/rustc");match.append(a)
    one,=match
    return one

argv=actual("parent-native-1")
assert argv==actual("candidate-native-1")
out=Path(argv[argv.index("--out-dir")+1])
assert sha(out/name)==new
src,=[x for x in argv if x.endswith(".rs")]
rlink=out/(name+".rlink")
inputs={str(f.relative_to(out)):sha(f) for f in out.rglob("*") if f.is_file()}
env={"HOME":str(state/"home"),"RUSTUP_HOME":str(state/"rustup"),"RUSTUP_AUTO_INSTALL":"0",
     "PATH":str(Path(shutil.which("rustup")).parent)+":/usr/bin:/bin","CARGO_HOME":str(state/"cargo-home"),"LANG":"C","LC_ALL":"C",
     "CARGO_INCREMENTAL":"0","CARGO_NET_OFFLINE":"true"}
rows={};files={}
for width in range(1,5):
    work=test/str(width);work.mkdir();copy=work/"out";shutil.copytree(out,copy)
    command=["rustc","+ohm",*argv[1:]]
    command[command.index(src)]=str(rlink)
    command+=["-Z","link-only","-C",f"link-arg=-Wl,--threads={width}"]
    listing=["bwrap","--ro-bind","/","/","--dev-bind","/dev","/dev","--proc","/proc","--tmpfs","/tmp","--bind",copy,out,
             "--chdir",state/"work","--","strace","-ff","-qq","-s","131072","-e","trace=execve","-o",out/"replayed.exec",*command]
    with (work/"stdout").open("xb") as so,(work/"stderr").open("xb") as se:
        rc=subprocess.run(listing,stdout=so,stderr=se,env=env,timeout=60).returncode
    row={"exit":rc,"stdout":sha(work/"stdout"),"stderr":sha(work/"stderr"),"requested_width":width}
    actual_links=[]
    for trace in copy.glob("replayed.exec.*"):
        for exe,a in cmds(trace):
            if exe.name=="ld.bfd" and "-o" in a:
                actual_links.append({"sha":sha(exe),"width_flags":[x for x in a if x.startswith("--threads=")],
                                   "output":Path(a[a.index("-o")+1]).name,"trace":sha(trace)})
    row["stock_links"]=actual_links;rows[width]=row
    if rc==0:
        elf=copy/name;row["elf"]=sha(elf)
        assert len(actual_links)==1 and actual_links[0]["width_flags"]==[f"--threads={width}"]
        assert actual_links[0]["sha"]=="0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5"
        results={}
        for label,extra in (("listing",["--list"]),("execute",["--test-threads=1"])):
            res=subprocess.run([elf,*extra],capture_output=True,env=env,cwd=state/"work",timeout=10)
            results[label]={"rc":res.returncode,"stdout":res.stdout.decode(),"stderr":res.stderr.decode()}
        row["runtime"]=results;files[row["elf"]]=elf
    put(work/"result.json",row)
    print(width,rc,row.get("elf"),row["stock_links"],flush=True)
assert {str(f.relative_to(out)):sha(f) for f in out.rglob("*") if f.is_file()}==inputs
result={"training_status":1,"incoming_elf_sha":new,"previous_elf_sha":old,"rows":rows,"original_inputs":inputs,
        "full_argv_identical":True,"reconstructed":[x for x in (old,new) if x in files]}
put(test/"result.json",result)
if not {old,new}<=files.keys():raise SystemExit("at least one original raw digest was not reconstructed")
a=files[old].read_bytes();b=files[new].read_bytes()
assert len(a)==len(b) and a[:6]==b[:6]==b"\x7fELF\x02\x01"
def spans(body):
    shoff=struct.unpack_from("<Q",body,40)[0];width,count,strid=struct.unpack_from("<HHH",body,58)
    assert width==64
    records=[struct.unpack_from("<IIQQQQIIQQ",body,shoff+i*width) for i in range(count)]
    stroff,size=records[strid][4:6];strings=body[stroff:stroff+size]
    locations={}
    for i,s in enumerate(records):
        name=strings[s[0]:].split(b"\x00",1)[0].decode()
        if name==".rodata":locations["rodata_entsize"]=(shoff+i*width+56,8)
        if name==".note.gnu.build-id":
            off=s[4];ns,ds,kind=struct.unpack_from("<III",body,off)
            assert body[off+12:off+12+ns]==b"GNU\0" and kind==3
            locations["build_id"]=(off+12+((ns+3)//4)*4,ds)
    return locations
sa=spans(a);sb=spans(b);assert sa==sb and len(sa)==2
recreated=bytearray(a);values={}
for k,(pos,size) in sa.items():
    values[k]={"offset":pos,"bytes":size,"old":a[pos:pos+size].hex(),"new":b[pos:pos+size].hex()}
    recreated[pos:pos+size]=b[pos:pos+size]
result["only_known_bytes"]=bytes(recreated)==b;result["fields"]=values;result["size"]=len(a)
put(test/"result.json",result)
assert result["only_known_bytes"],"the original ELFs differ outside the two vetted fields"
