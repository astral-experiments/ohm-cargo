"""Run a tiny real GNU-driver/Wild link with the search directories observed on Ruff."""
import argparse,hashlib,json,re,shutil,subprocess
from pathlib import Path
ap=argparse.ArgumentParser()
ap.add_argument("--work",type=Path,required=True)
ap.add_argument("--wild",type=Path,required=True)
a=ap.parse_args()
root=a.work.resolve();root.mkdir(exist_ok=False);ld=a.wild.resolve()
def sha(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
assert sha(ld)=="0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5"
(root/"main.c").write_text("int main(void){return 41;}\n")
(root/"hook.c").write_text("#include <unistd.h>\n__attribute__((constructor)) static void early(void){_exit(83);}\n")
for n in ("main","hook"):subprocess.run(["cc","-c","-fPIC",n+".c","-o",n+".o"],cwd=root,check=True)
gcc_s=Path(subprocess.check_output(["cc","-print-file-name=libgcc_s.so"],text=True).strip()).resolve();assert gcc_s.is_file()
names=["gcc_s","util","rt","pthread","m","dl","c"]
out={}
for classes in [("psm",),("psm","zstd"),("psm","zstd","jemalloc")]:
    name="-".join(classes);case=root/name;case.mkdir();early=case/"psm"
    dirs=[case/"raw-dylibs",*[case/n for n in classes]]
    for d in dirs:d.mkdir()
    output=case/"program";dep=case/"lookup.d"
    target=early/"libgcc_s.so"
    argv=["cc","-fuse-ld=bfd","-B"+str(ld.parent),*[str("-L"+str(n)) for n in dirs],str(root/"main.o"),"-Wl,--as-needed","-Wl,--threads=1",*[str("-l"+n) for n in names],"-Wl,--dependency-file="+str(dep),"-o",str(output)]
    baseline=None;res=[]
    for phase in ("original","new-earlier-input","invalid-earlier-input","restored"):
        if phase=="new-earlier-input":target.write_text("INPUT ( "+str(root/"hook.o")+" "+str(gcc_s)+" )\n")
        if phase=="invalid-earlier-input":target.write_text("THIS_IS_NOT_A_LINKER_SCRIPT_FEATURE(\n")
        if phase=="restored":target.unlink()
        if baseline is not None: assert all(p.is_file() and sha(p)==h for p,h in baseline.items()),phase
        tr=case/(phase+".exec")
        p=subprocess.run(["strace","-f","-qq","-s","65535","-e","trace=execve","-o",str(tr),*argv],capture_output=True,text=True)
        trace=tr.read_text()
        lines=[l for l in trace.splitlines() if f'execve("{ld}"' in l and re.search(r'= 0$',l)]
        assert len(lines)==1,(argv,trace)
        actual={"wild":sha(ld),"raw_exec_sha256":sha(tr),"successful_wild_execs":len(lines)}
        if phase=="invalid-earlier-input":
            assert p.returncode!=0 and "libgcc_s.so" in p.stderr,(phase,p)
            res.append(dict(phase=phase,**actual,link=p.returncode,stderr_sha256=hashlib.sha256(p.stderr.encode()).hexdigest(),baseline_inputs_unchanged=True));continue
        assert p.returncode==0,(phase,p.stderr)
        raw=dep.read_text();rhs=raw.split(":",1)[1].split("\n\n",1)[0]
        paths=[Path(s) for s in re.findall(r"[^\s\\]+",rhs)];assert len(paths)>7
        if phase=="original":
            # GCC and the plugin can generate temporary inputs; fail closed if an input vanishes.
            assert all(p.is_file() for p in paths),[str(p) for p in paths if not p.is_file()]
            baseline={p:sha(p) for p in paths}
            assert gcc_s in {p.resolve() for p in baseline} and not target.exists()
        ec=subprocess.run([str(output)]).returncode
        assert ec==(83 if phase=="new-earlier-input" else 41)
        res.append(dict(phase=phase,**actual,link=0,program=ec,elf=sha(output),actual_inputs=len(paths),baseline_inputs_unchanged=all(sha(p)==h for p,h in baseline.items())))
    assert res[0]["elf"]==res[-1]["elf"]!=res[1]["elf"]
    out[name]=res
(root/"observations.json").write_text(json.dumps(out,indent=2)+"\n")
print(json.dumps({k:[s.get("program","link failed") for s in rows] for k,rows in out.items()}))
