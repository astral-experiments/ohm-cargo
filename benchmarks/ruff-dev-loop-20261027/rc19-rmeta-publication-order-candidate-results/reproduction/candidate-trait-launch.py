from pathlib import Path
import os,sys,subprocess,hashlib
root=Path(__file__).resolve().parent
image=Path(sys.argv[1]).resolve()
with image.open("rb") as f:assert hashlib.file_digest(f,"sha256").hexdigest()==sys.argv[2]
link=root/"sdk/bin/cargo";original=link.resolve()
assert original==Path.home()/".cache/ohm-rlib-origin-product-20261029/cargo-A"
next=link.parent/"private-selected-cargo"
next.symlink_to(image);next.replace(link)
try:
    x=subprocess.run([sys.executable,"-IB",str(root/"trait-candidate.py")],cwd=root)
    raise SystemExit(x.returncode)
finally:
    next.symlink_to(original);next.replace(link)
