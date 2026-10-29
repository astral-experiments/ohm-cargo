"""Verify the -17 addendum using the digest-pinned four-crate core packet."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("--core",type=Path,required=True,help="downloaded core packet directory")
args=parser.parse_args()
core=args.core.resolve(strict=True)
here=Path(__file__).resolve().parent
digest=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
assert digest(core/"SHA256SUMS")=="53e1b6d317a749982edd6ff1cbb9362e865734a67cfcfa094c02c804654070ea"
for folder in (core,here):
    subprocess.run(["sha256sum","-c","--status","SHA256SUMS"], cwd=folder, check=True)
sdk=json.loads((here/"distribution.json").read_bytes())
assert sdk["tag"]=="ohm-1.99.0-17" and sdk["github_release_asset_id"]==683546983
assert (sdk["bytes"],sdk["archive_sha256"])==(359683716,"163267d26889b1bd2c467d7db97efee42cd2ac9dc9af2abc3a56ade8da9a9572")
assert sdk["installer_sha256"]=="72807761d932e9ea33ac98208ab00ce7f9cd5eee3dbe86cd911007358ac71b01"
result=json.loads((here/"official-17.json").read_bytes())
assert sdk["images"]==result["images"]|{"wild":"0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5"}
subprocess.run([sys.executable,"-IB",core/"verify.py","--add-17",here/"official-17.json"],check=True)
