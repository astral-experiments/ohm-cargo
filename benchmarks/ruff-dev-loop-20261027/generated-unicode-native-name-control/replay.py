"""Replay the same archive-name observation using the portable single-member input or complete original rlibs."""
from pathlib import Path
import argparse,gzip,hashlib,json,re,shutil,subprocess
root=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def run(args,cwd,check=True):
    z=subprocess.run(list(map(str,args)),cwd=cwd,capture_output=True)
    if check and z.returncode!=0:raise RuntimeError(str(args[:2])+": "+z.stderr.decode(errors="replace"))
    return z
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--wild",required=True,type=Path)
    p.add_argument("--workdir",required=True,type=Path,help="A new independently created work directory")
    p.add_argument("--archive-dir",type=Path,help="Complete private rlibs, named by their actual sha256 as in mapping.json")
    a=p.parse_args();work=a.workdir.resolve();work.mkdir(parents=False)
    wild=a.wild.resolve();expected=json.loads((root/"receipts/full/design.json").read_bytes())
    assert sha(wild)==expected["linker"]
    inputs=json.loads((root/"mapping.json").read_bytes());rows={}
    actual=gzip.decompress((root/"selected-object.bin.gz").read_bytes())
    lib=work/"libunicode_names2.rlib";obj=work/"observer.o";c=work/"observer"
    for nm in ("observer.s","layout.ld"):shutil.copyfile(root/nm,work/nm)
    run(["gcc","-c","-x","assembler","observer.s","-o","observer.o"],work)
    for phase in ("original","edited","restored"):
        e=inputs[phase];assert hashlib.sha256(actual).hexdigest()==e["object"]
        if a.archive_dir:
            donor=a.archive_dir.resolve()/e["full_archive"];assert sha(donor)==e["full_archive"];shutil.copyfile(donor,lib)
        else:
            native=work/e["name"];native.write_bytes(actual)
            if lib.exists():lib.unlink()
            run(["ar","crsD",lib,native.name],work)
        args=[wild,"-static","--gc-sections","--unresolved-symbols=ignore-all","--undefined="+expected["symbol"],"-T",work/"layout.ld","-o",c,obj,lib]
        run(args,work);n=run(["nm","-n",c],work).stdout
        loc={s.decode():int(v,16)for v,s in re.findall(rb"^([0-9a-f]+) \w (picked_(?:start|end))$",n,re.M)}
        assert loc.keys()=={"picked_end","picked_start"}
        d=loc["picked_end"]-loc["picked_start"]
        cc=run([c],work,check=False);assert cc.returncode==(42 if phase=="original" else 41) and not cc.stdout and not cc.stderr
        assert (d>=484 if phase=="original" else d==0)
        sy=run(["readelf","-sW",c],work).stdout
        assert re.search(rb"\b484 FUNC .*"+re.escape(expected["symbol"].encode())+rb"$",sy,re.M)
        shutil.copyfile(c,work/(phase+".elf"))
        rows[phase]={"code":cc.returncode,"span":d,"bounds":loc,"output":sha(c),"archive":sha(lib),"complete":bool(a.archive_dir),"member":e["name"],"function_bytes":e["function_size"]}
    (work/"result.json").write_text(json.dumps(rows,sort_keys=True,indent=2)+"\n");print(json.dumps(rows,sort_keys=True))
if __name__=="__main__":main()
