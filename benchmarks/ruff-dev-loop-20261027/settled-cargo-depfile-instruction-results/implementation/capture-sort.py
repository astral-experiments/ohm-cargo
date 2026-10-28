import fcntl, json, os, re, subprocess
from pathlib import Path
import setup as s
from profile import snap
H=s.H; D=H/'output-path-study'; output=H/'target/debug/libruff_linter.d'; artifact=H/'target/debug/libruff_linter.rlib'
with (s.P/'member-build-native.lock').open('a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);os.sched_setaffinity(0,range(8)); D.mkdir(exist_ok=False)
    before=[snap(),s.sha(output),output.stat().st_mtime_ns,s.sha(artifact)]
    proc=subprocess.run(['strace','-f','-qq','-s','2000','-e','trace=openat,execve','-o',D/'opens',s.CARGO,'+ohm','build','--lib','--locked','--offline','-j4'],cwd=s.SRC/'crates/ruff_linter',env=s.env(),capture_output=True)
    (D/'stderr').write_bytes(proc.stderr);assert proc.returncode==0 and b'Compiling' not in proc.stderr and not proc.stdout
    assert before==[snap(),s.sha(output),output.stat().st_mtime_ns,s.sha(artifact)]
    txt=(D/'opens').read_text().splitlines()
    opens=[Path(m[1]) for line in txt if (m:=re.search(r'openat\(AT_FDCWD, "([^"]+/fingerprint/dep-[^"]+)", O_RDONLY\|O_CLOEXEC\)\s+= \d+',line))]
    deps=[p for p in opens[-29:]]
    assert len(deps)==29 and len(set(deps))==29,(len(opens),deps)
    assert deps[0].name=='dep-lib-ruff_linter',deps
    units={json.loads(l)['package_id']:json.loads(l) for l in (H/'native/edited-fresh-json/stdout').read_bytes().splitlines() if json.loads(l).get('reason')=='compiler-artifact'}
    local={Path(u['manifest_path']).parent.name:Path(u['manifest_path']).parent for u in units.values() if u['package_id'].startswith('path+')}
    records=[]
    for p in deps:
        data=p.read_bytes();assert data[:6] in (b'\x01\x00\x00\x00\xff\x04',b'\x01\x00\x00\x00\xff\x02')
        i=6
        def take(n):
            global i
            result=data[i:i+n];i+=n;assert len(result)==n;return result
        def n4():return int.from_bytes(take(4),'little')
        def tab():return take(n4())
        f=[]
        for _ in range(n4()):
            kind=take(1)[0];raw=tab().decode();checks=take(1)[0]
            if checks: take(8);tab()
            pkg=local[p.parents[2].name]
            absolute=str(pkg if kind==0 else H/'target')+'/'+raw if raw and not raw.startswith('/') else (raw or str(pkg if kind==0 else H/'target'))
            f.append(absolute)
        records.append(dict(depinfo=str(p),sha256=s.sha(p),files=f))
    golden=output.read_text().rstrip('\n').split(': ',1)[1].split(' ')
    found={v for r in records for v in r['files']};extra=[v for v in golden if v not in found]
    assert len(golden)==1243 and set(golden).issuperset(found),(len(found),list(found-set(golden))[:4],len(extra))
    s.emit(D/'capture.json',dict(all_depinfo_opens=len(opens),records=records,extra=extra,anchors=before))
    (D/'input').write_text('\n'.join('\n'.join(r['files'])+'\n' for r in records)+'\n'.join(extra)+'\n')
    (D/'output').write_text('\n'.join(golden)+'\n')
    print('opens',len(opens),'records',len(records),'covered',len(found),'extra',len(extra), 'final',len(golden))
