"""Verify the immutable registered study plus its single kernel-mount evidence amendment before execution."""
from pathlib import Path
import hashlib,json,os,sys
K=Path(__file__).resolve().parent.parent
def sh(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
def get(p):return json.loads(p.read_bytes())
def main():
    status=get(K/"binding/operational.json")
    design=K/"registration";extra=K/"operational-registration"
    assert status["original"]==sh(design/"SHA256SUMS") and status["amendment"]==sh(extra/"SHA256SUMS")
    for d in (design,extra):
        for line in (d/"SHA256SUMS").read_text().splitlines():
            digest,name=line.split("  ",1); f=Path(name);assert not f.is_absolute() and ".." not in f.parts and sh(d/f)==digest
    spec=get(design/"binding.json")["worker"];fixed=get(extra/"sources.json")["changed"]
    for name,h in spec.items():
        expected=fixed[name]["new"] if name in fixed else h
        assert sh(K/"ops"/name)==expected,name
    assert sh(Path(__file__))==sh(extra/"launch.py")
    assert Path(sys.argv[1]).name in ("suite.py","measure.py")
    args=["/usr/bin/python3","-IB",str(K/"ops"/sys.argv[1]),*sys.argv[2:]]
    os.execv(args[0],args)
if __name__=="__main__":main()
