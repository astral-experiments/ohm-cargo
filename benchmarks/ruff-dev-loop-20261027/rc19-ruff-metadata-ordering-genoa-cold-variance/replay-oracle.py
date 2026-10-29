"""Compare the two retained native macro binaries with the same real rustc."""
import hashlib,json,os,shutil,subprocess,sys,tempfile
from pathlib import Path

here=Path(__file__).resolve().parent
evidence=json.loads((here/"native-macro.json").read_bytes())
images={k:Path(arg).resolve() for k,arg in zip(("A","B"),sys.argv[1:],strict=True)}
with tempfile.TemporaryDirectory(prefix="derive-comparison-") as tmp:
    tmp=Path(tmp)
    image=tmp/"libget_size_derive2-52dd06df2c000d98.so"
    source=tmp/"clash.rs"
    shutil.copyfile(here/"clash.rs",source)
    cmd=["rustc","+ohm","--crate-type=lib","--edition=2024","--error-format=json","--emit=metadata","--extern","get_size_derive2="+str(image),str(source),"-o",str(tmp/"clash.rmeta")]
    for arm,path in images.items():
        assert hashlib.sha256(path.read_bytes()).hexdigest()==evidence["ELF"][arm]["sha256"]
        shutil.copyfile(path,image)
        result=subprocess.run(cmd,cwd=tmp,capture_output=True,timeout=30)
        rows=[json.loads(line) for line in result.stderr.splitlines() if line.startswith(b"{")]
        msgs=[r["message"] for r in rows if "conflicts with mutually exclusive" in r["message"]]
        assert result.returncode==evidence["observed"][arm]["status"] and msgs==evidence["observed"][arm]["diagnostics"]
        print(arm,result.returncode,*msgs)
