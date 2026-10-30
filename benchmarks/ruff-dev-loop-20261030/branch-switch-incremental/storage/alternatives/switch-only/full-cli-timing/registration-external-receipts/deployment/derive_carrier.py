"""Derive the external-mount adapter only from the authenticated 6727fa64 original."""
from pathlib import Path
import hashlib
import sys

def replace(text,old,new):
    if text.count(old)!=1:raise ValueError("original carrier changed: "+old[:90])
    return text.replace(old,new)

def materialize(original,destination,site):
    check=original/"SHA256SUMS"
    if hashlib.sha256(check.read_bytes()).hexdigest()!="6727fa64c0f3c8d2fda18cd7a99a945b6f0bf7c2fa32f3e3cf1bc4b0ab5908b7":
        raise ValueError("original deployment not authenticated")
    text=(original/"carrier.sh").read_text()
    text=replace(text,"set -euo pipefail","set -euo pipefail\ntest -n \"$3\" && test \"$(readlink /proc/self/ns/mnt)\" != \"$3\"")
    text=replace(text,'mount --bind "$study" /var/tmp',
        "external="+str(site.parent)+'\ncase "$2" in qualification|scored) ;; *) exit 32;; esac\nspool="$external/spool/$2"\n'
        'test "$(findmnt -n -o FSTYPE -T "$external/receiver/store")" = ext4\n'
        'umount "$external/receiver"\nmount --bind "$spool" /var/tmp')
    text=replace(text,'mount --bind "$pilot/work/canonical" "$study/donor"',
         # The shell remains the independent namespace holder through all setup,
         # any failed native check and the validated acknowledgement.
         'hold() { local status=$?; trap - EXIT; set +e; '
         'exec /usr/bin/setpriv --reuid=1000 --regid=1000 --init-groups --no-new-privs '
         '/usr/bin/python3 -IB "$external/public/handoff.py" "$study/private/config.json" "$slot" "$status"; }\n'
         'slot="$1"; trap hold EXIT\nmount --bind "$pilot/work/canonical" "$study/donor"')
    start='"'+r'${ordinary[@]}'+'" /usr/bin/python3 -IB "$study/private/safe-worker.py" "$study/private/config.json" "$1" || rc=$?'
    text=replace(text,start,'if test -e "$study/logs/$1/stop-before-native"; then exit 121; fi\n'
        '/usr/bin/setsid /usr/bin/setpriv --reuid=1000 --regid=1000 --init-groups --no-new-privs '
        '/usr/bin/python3 -IB "$study/private/safe-worker.py" "$study/private/config.json" "$1" &\n'
        'worker=$!; printf "%s\\n" "$worker" | "${ordinary[@]}" /usr/bin/tee "$study/logs/$1/active-worker-pid" >/dev/null; wait "$worker" || rc=$?')
    (destination/"carrier.sh").write_text(text)
    g=(original/"mount-guard.py").read_text()
    g=replace(g,'assert r.stat().st_dev==scratch.stat().st_dev!=real_home.stat().st_dev',
       'assert len({r.stat().st_dev,scratch.stat().st_dev,real_home.stat().st_dev,canonical.stat().st_dev,(canonical/".allocation").stat().st_dev})==5\n'
       'assert outside["receiver_device"] not in [x.split()[2] for x in Path("/proc/self/mountinfo").read_text().splitlines()]\n'
       'assert not os.statvfs(r).f_flag & os.ST_RDONLY and shutil.disk_usage(r).total==384*2**20')
    g=replace(g,'if not readonly and (home or not allowed_receipt(candidate)):', 'if not readonly:')
    g=replace(g,'assert all(readonly or (not home and allowed_receipt(candidate)) for candidate,(_,readonly) in fixed.items())',
                    'assert all(readonly for _,readonly in fixed.values())')
    g=replace(g,'if action=="seal":sys.exit(0)','''if action=="seal":sys.exit(0)
import stat
receiver_dev=outside["receiver_device"]
for block in (Path("/dev/block")/receiver_dev, Path("/dev")/(Path("/sys/dev/block")/receiver_dev).resolve().name):
    if block.exists() and stat.S_ISBLK(block.stat().st_mode):
        assert not os.access(block,os.W_OK),"external backing block device writable by the measured user"
for descriptor in Path("/proc/self/fd").iterdir():
    try:
        fstat=descriptor.stat()
        line=Path("/proc/self/fdinfo",descriptor.name).read_text()
    except FileNotFoundError:continue
    flags=int(next(v.split()[1] for v in line.splitlines() if v.startswith("flags:")),8)
    if flags&os.O_ACCMODE!=os.O_RDONLY and stat.S_ISREG(fstat.st_mode):
        assert fstat.st_dev not in {real_home.stat().st_dev,scratch.stat().st_dev,outside["receiver_st_dev"]}
''')
    g=replace(g,'"writable_HOME_budget":0,','"writable_HOME_budget":0,"writable_scratch_budget":0,"external_receiver_inaccessible":True,')
    (destination/"mount-guard.py").write_text(g)
    for n in ["config.json","product.py","safe-worker.py"]:
        (destination/n).write_bytes((original/n).read_bytes())

if __name__=="__main__":materialize(*map(Path,sys.argv[1:]))
