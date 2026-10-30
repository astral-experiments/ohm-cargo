#!/bin/bash
set -euo pipefail
q=$1
orig=$2
sdk=$3
proxies=$4
realhome=$5
other=$6
otherwrite=$7
pub=$(dirname "$(readlink -f "$0")")
test -n "${ORIGINAL_MOUNT_NS:-}" && test "$(readlink /proc/self/ns/mnt)" != "$ORIGINAL_MOUNT_NS"
test -d "$otherwrite" -a -d "$other" -a -f "$sdk/bin/rustc" -a -e "$proxies/cargo"
test "$(stat -c %d "$q")" != "$(stat -c %d "$other")"
test "$(stat -c %d "$otherwrite")" = "$(stat -c %d "$other")"
test "$(awk '/^MemAvailable:/ {print int($2/1024/1024)}' /proc/meminfo)" -ge 16
test "$(id -u)" = 0
test -d "$q" -a ! -e "$q/receiver-result.json"
test "$(stat -c %u "$q")" = 1000
umask 077
F="$q/frame"
mkdir "$F"
mount --make-rprivate /
mount -t tmpfs -o size=2M,nodev,nosuid,uid=1000,gid=1000,mode=0700 qa-frame "$F"
for tag in backing work spool target receiver spool-limit; do install -d -m700 -o 1000 -g 1000 "$F/$tag"; done
for tuple in backing:32M work:96M spool:48M target:96M spool-limit:2M; do
  label=${tuple%:*}
  mount -t tmpfs -o "size=${tuple#*:},nodev,nosuid,uid=1000,gid=1000,mode=0700" "qa-$label" "$F/$label"
done
run=(/usr/bin/setpriv --reuid=1000 --regid=1000 --init-groups --no-new-privs)
"${run[@]}" /usr/bin/python3 -IB -c 'import sys; from pathlib import Path;sys.path.insert(0,sys.argv[1]);import receiver as r;r.reserve_file(Path(sys.argv[2]),16*2**20)' "$pub" "$F/backing/receiver.ext4"
"${run[@]}" /usr/sbin/mkfs.ext4 -F -q -m0 -E nodiscard,lazy_itable_init=0,lazy_journal_init=0 "$F/backing/receiver.ext4"
"${run[@]}" /usr/bin/python3 -IB -c '
import hashlib,json,os,sys
from pathlib import Path
p=Path(sys.argv[1]);out=Path(sys.argv[2])
def snap():
    st=p.stat()
    with p.open("rb") as src: h=hashlib.file_digest(src,"sha256").hexdigest()
    return [st.st_size,st.st_blocks*512,h]
a=snap()
with p.open("r+b") as f:
    os.posix_fallocate(f.fileno(),0,p.stat().st_size);os.fsync(f.fileno())
b=snap();assert a[0]==b[0] and a[2]==b[2] and b[1]>=b[0],(a,b)
out.write_text(json.dumps({"after_mkfs":a,"reserved_after_mkfs":b})+"\n")
' "$F/backing/receiver.ext4" "$q/image-allocation.json"
mount -t ext4 -o loop,nodev,nosuid,noexec,nodiscard "$F/backing/receiver.ext4" "$F/receiver"
install -d -o 1000 -g 1000 -m700 "$F/receiver/store"
dev=$(/usr/bin/findmnt -n -o MAJ:MIN -T "$F/receiver/store")
export HOME="$realhome"
"${run[@]}" /usr/bin/strace -qq -yy -s 256 -e trace=fsync,fdatasync,link,linkat -o "$F/spool/receiver.trace" /usr/bin/python3 -IB "$pub/test_receiver.py" "$F/work" "$F/spool" "$F/receiver/store" "$F/backing" "$other" "$F/backing/receiver.ext4" "$q/tiny-durable" "$q/receiver-result.json" "$F/spool-limit" </dev/null
/usr/bin/setpriv --reuid=1000 --regid=1000 --init-groups /usr/bin/python3 -IB "$pub/test_nested_handoff.py" "$F" "$q" </dev/null
unshare -m --propagation private /bin/bash -euo pipefail -c '
    q=$1;f=$2;pub=$3;orig=$4;dev=$5;sdk=$6;proxies=$7;realhome=$8;other=$9;otherwrite=${10}
    mount --make-rprivate /
    umount "$f/receiver"
    for m in "$realhome" "$other" "$f/backing" /run/user/1000 /dev/shm; do
        mount --bind "$m" "$m";mount -o remount,bind,ro "$m"
    done
    mount -o remount,bind,ro /
    exec /usr/bin/setpriv --reuid=1000 --regid=1000 --init-groups --no-new-privs /usr/bin/strace -qq -s 512 -o "$f/spool/parent.trace" -e trace=wait4,openat,openat2 /usr/bin/python3 -IB "$pub/test_io.py" "$orig" "$f/work" "$f/spool" "$f/target" "$f/backing" "$q" "$otherwrite" "$sdk" "$proxies" "$dev" </dev/null >"$f/spool/io.out" 2>"$f/spool/io.err"
' worker "$q" "$F" "$pub" "$orig" "$dev" "$sdk" "$proxies" "$realhome" "$other" "$otherwrite" || {
    "${run[@]}" cp -- "$F/spool/io.err" "$q/io-failure.stderr"
    "${run[@]}" /usr/bin/python3 -IB -c 'from pathlib import Path;import sys;x=Path(sys.argv[1]);print([(f.name,f.stat().st_size) for f in x.rglob("*") if f.is_file() and (f.name.endswith(".json") or f.name=="cargo.stderr")][-35:]);print((x/"io.err").read_text()[-2300:])' "$F/spool"
    exit 72
}
"${run[@]}" /usr/bin/python3 -IB -c '
from pathlib import Path
import json,sys,hashlib,re
q,f=map(Path,sys.argv[1:3])
result=json.loads((f/"spool/io/io-result.json").read_bytes())
trace=(f/"spool/parent.trace").read_text()
for phase in ("cold","edit","fresh","invalid","repair"):
 p=f/"spool/io"/phase
 line=next(x for x in trace.splitlines() if str(p/"cargo.stdout") in x and "O_CREAT" in x)
 pos=trace.index(line)
 previous=trace[:pos].split("wait4(")[-1]
 assert re.match(r"[0-9]+, .*WEXITSTATUS.* = [0-9]+",previous.splitlines()[0]),previous[:160]
boundary={"every_named_output_after_own_blocking_wait":True,"physical_wait4_and_open_trace":hashlib.sha256(trace.encode()).hexdigest(),"bytes":len(trace),"contents":result}
(q/"io-result.json").write_text(json.dumps(boundary,sort_keys=True,indent=2)+"\n")
' "$q" "$F"
"${run[@]}" /usr/bin/python3 -IB -c '
from pathlib import Path
import subprocess,sys,hashlib,os,json
q,f=map(Path,sys.argv[1:3]);out=q/"bounded-raw.tar.zst"
entries=[p.relative_to(f).as_posix() for base in [f/"receiver/store",f/"work/provider",f/"spool/io"] for p in base.rglob("*") if p.is_file()]
entries.extend(["spool/parent.trace","spool/receiver.trace","spool/uncompressible","spool-limit/first-stop.json"])
assert not any("filler" in x or x.endswith("receiver.ext4") for x in entries)
# The deliberately incompressible ENOSPC source and its incomplete archive
# are retained in this small, independent local QA record as well.
entries.sort();assert sum((f/p).stat().st_size for p in entries)<20*2**20
tar=subprocess.Popen(["tar","-cf","-","-C",f,"--",*entries],stdout=subprocess.PIPE)
with out.open("xb") as b: z=subprocess.run(["zstd","-q","-T1","-3","-c"],stdin=tar.stdout,stdout=b);b.flush();os.fsync(b.fileno())
tar.stdout.close();assert tar.wait()==z.returncode==0
for p in entries:
 with (f/p).open("rb") as t: expected=hashlib.file_digest(t,"sha256").hexdigest()
 rd=subprocess.Popen(["tar","--zstd","-xOf",out,"--",p],stdout=subprocess.PIPE)
 with rd.stdout as t: actual=hashlib.file_digest(t,"sha256").hexdigest()
 assert actual==expected and rd.wait()==0
(q/"raw.json").write_text(json.dumps({"members":len(entries),"size":out.stat().st_size,"sha256":hashlib.sha256(out.read_bytes()).hexdigest(),"all_original_bytes_reopened":True})+"\n")
' "$q" "$F"
printf 'All private receiver, fail-stop, FD and actual Cargo controls completed.\n'
