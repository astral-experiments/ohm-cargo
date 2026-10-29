"""Run the three historical upgrade controls against an existing private SDK pair."""
import argparse,os,subprocess,sys
from pathlib import Path
args=argparse.ArgumentParser();args.add_argument("released_sdk",type=Path);args.add_argument("candidate_sdk",type=Path);args.add_argument("empty_dir",type=Path);a=args.parse_args()
old=a.released_sdk.resolve(strict=True);new=a.candidate_sdk.resolve(strict=True);out=a.empty_dir.resolve();out.mkdir(mode=0o700)
here=Path(__file__).resolve().parent
assert set(os.sched_getaffinity(0))==set(range(24,28))
alias=out/"old-rustup/toolchains";alias.mkdir(parents=True);(alias/"ohm").symlink_to(old,target_is_directory=True)
def run(*cmd):
    subprocess.run([sys.executable,"-IB",*cmd],check=True)
run(here/"drivers/check/replay.py",old,out/"check","provider-late","--replacement-sdk",new,"--replacement-verdict","101")
run(here/"drivers/build/replay.py",out/"build","--rustup-home",out/"old-rustup","--replacement-sdk",new)
for kind in ["valid","malformed"]:
    run(here/"native-provider.py",old,out/kind,"--stage-producer","provider","--replacement",new,"--poison",kind)
run(here/"assembler.py",old,new,out/"assembler")
