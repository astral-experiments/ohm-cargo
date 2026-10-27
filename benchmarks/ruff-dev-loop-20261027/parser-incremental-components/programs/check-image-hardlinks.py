"""Read the exact recipient files and match Cargo's lifted rlib to the path rustc mmap'd."""
from pathlib import Path
import hashlib,json
p=Path("/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027")
j=p/"mixed-registry-only-pilot";out={}
for arm in "AB":
    out[arm]={};rbase=j/"parser-component-open-audit"/arm
    for state in ["all","empty"]:
        context=rbase/f"{state}-caller-{state}";headers=json.loads((context/"decoded-images.json").read_bytes())
        maps=json.loads((context/"observed-paths.json").read_bytes())
        st=j/"parser-incremental-components"/arm/state/"physical/target";ids={}
        for ext in [".rmeta",".rlib"]:
            alias,=[Path(k) for k in headers if k.endswith(ext)]
            read_path,=[Path(k) for k in maps if Path(k).name.startswith("libruff_python_parser-") and k.endswith(ext)]
            a=st/alias.relative_to(p/"native-target");b=st/read_path.relative_to(p/"native-target")
            av,bv=a.stat(),b.stat();digest=hashlib.sha256(b.read_bytes()).hexdigest()
            assert digest==headers[str(alias)]["sha"]==maps[str(read_path)]["sha256"]
            ids[ext]={"Cargo_advertised":str(alias),"rustc_mapped":str(read_path),"sha256":digest,"Cargo_dev_ino":[av.st_dev,av.st_ino],"rustc_dev_ino":[bv.st_dev,bv.st_ino],"same_inode":a.samefile(b)}
        out[arm][state]=ids
print(json.dumps(out,indent=2,sort_keys=True))
