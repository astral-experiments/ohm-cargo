"""Exercise only the namespace and its two stock --version routes. No Cargo work is launched."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

def sha(path):
    with path.open("rb") as src:
        return hashlib.file_digest(src,"sha256").hexdigest()

def identity(path):
    v=path.stat()
    return [v.st_dev,v.st_ino,v.st_mode,v.st_nlink,v.st_size,v.st_mtime_ns,v.st_ctime_ns]

def main(root):
    entry=Path("/run/ohm-native-handoff-v1")
    binding=json.loads((root/"binding.json").read_bytes())
    mount_file=root/"bwrap-argv.json"
    assert sha(mount_file)==binding["mounts_sha256"]
    args=json.loads(mount_file.read_bytes())
    assert args[0::3]==["--ro-bind","--bind","--ro-bind","--ro-bind"] and len(args)==12
    old=Path(args[7])
    shim=root/"transport"
    blank=root/"capsule/ld.stock"
    assert blank.is_file() and not blank.is_symlink() and blank.stat().st_size==0
    original_id, shim_id = identity(old),identity(shim)
    assert sha(old)==binding["stock_sha256"] and sha(shim)==binding["transport_sha256"]
    working=Path("/run")
    entries=sorted(working.iterdir())
    assert entry not in entries
    command=["bwrap","--die-with-parent","--ro-bind","/","/","--dev","/dev","--proc","/proc",
             "--tmpfs","/run"]
    for p in entries:
        if p.is_symlink():
            command+=["--symlink",os.readlink(p),str(p)]
        else:
            command+=["--ro-bind",str(p),str(p)]
    command+=args+["--",sys.executable,"-IB",str(Path(__file__).resolve()),"--inside",
                    str(root),json.dumps(original_id),json.dumps(shim_id),str(len(entries))]
    cp=subprocess.run(command,capture_output=True,timeout=20)
    if cp.returncode:
        raise RuntimeError(cp.stderr.decode(errors="replace"))
    result=json.loads(cp.stdout)
    assert result["original"]==original_id and result["probe"]==shim_id
    assert identity(old)==original_id and identity(shim)==shim_id and blank.stat().st_size==0
    result.update(stock_sha256=binding["stock_sha256"],transport_sha256=binding["transport_sha256"],
                  script_sha256=sha(Path(__file__)),mounts_sha256=sha(mount_file))
    output=root/"namespace-verification.json"
    with output.open("x") as stream:
        json.dump(result,stream,indent=2,sort_keys=True);stream.write("\n")
    print(sha(output))

def inside(root,old,new,base_count):
    cap=Path("/run/ohm-native-handoff-v1")
    args=json.loads((root/"bwrap-argv.json").read_bytes())
    assert len(list(Path("/run").iterdir()))==base_count+1
    stock=cap/"ld.stock"
    probe=Path(args[-1])
    assert identity(stock)==old and identity(probe)==new
    mounts={l.split(" - ",1)[0].split()[4]:l.split(" - ",1)[0].split()[5].split(",")
            for l in Path("/proc/self/mountinfo").read_text().splitlines()}
    for p in (cap,stock,probe):assert "ro" in mounts[str(p)]
    assert "rw" in mounts[str(cap/"audit")]
    expected=sha(stock)
    policy=json.loads((cap/"policy.json").read_bytes())
    assert expected==policy["wild_sha256"] and sha(cap/"check")==policy["checker_sha256"]
    for width in policy["workers"].values():
        d=width["training_sha256"];assert sha(cap/"recipes"/(d+".json"))==d
    versions=[]
    for exe in (stock,probe):
        cmd=subprocess.run([exe,"--version"],capture_output=True,timeout=5)
        assert cmd.returncode==0 and not cmd.stderr and b"Wild 0.11.0" in cmd.stdout
        versions.append(cmd.stdout.decode().strip())
    assert versions[0]==versions[1]
    print(json.dumps({"original":old,"probe":new,"widths":sorted(map(int,policy["workers"])),
                      "existing_runtime_entries":base_count,"version_direct_and_via_probe":versions,
                      "audit_mount_writable":True,"capsule_and_both_tool_images_read_only":True}))

if __name__=="__main__":
    if sys.argv[1]=="--inside":
        inside(Path(sys.argv[2]),json.loads(sys.argv[3]),json.loads(sys.argv[4]),int(sys.argv[5]))
    else:
        main(Path(sys.argv[1]).resolve())
