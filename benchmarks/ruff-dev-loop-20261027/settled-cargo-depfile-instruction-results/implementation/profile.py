"""Measure Cargo's own executed instructions, keeping the ordinary release toolchain and source."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import fcntl,hashlib,json,os,re,subprocess
import setup as s
H=s.H;P=s.P
TOOL=P/'spaced-dirty-attribution-20261028/software-counters/callgrind'
def output(cmd,env=None,cwd=None):return subprocess.run(cmd,check=True,capture_output=True,text=True,env=env,cwd=cwd).stdout
def snap():
    git=Path(output(['git','-C',s.SRC,'rev-parse','--path-format=absolute','--git-path','index'],env=s.env()).strip())
    assert git.is_file()
    out={'index':s.sha(git)}
    for n in ('.ohm-git-index-sha1dc-v1','.ohm-registry-json-v2'):
        root=H/'cargo-home'/n
        assert root.is_dir() and len(ls:=sorted(p for p in root.iterdir() if p.is_file()))>0,(n,root)
        hashes=[(p.name,s.sha(p)) for p in ls]
        out[n]={'slots':len(ls),'digest':hashlib.sha256(json.dumps(hashes).encode()).hexdigest()}
    return out
def actual_processes():
    rx=re.compile(r'^execve\("([^"]+)".*= 0$')
    events=[]
    for f in sorted(H.glob('physical-job.*')):
        events.extend((f.name,match[1]) for l in f.read_text().splitlines() if (match:=rx.match(l)))
    assert len(events)==2 and Path(events[0][1])==s.CARGO and Path(events[1][1]).resolve()==s.SDK/'bin/cargo',events
    return events
def main():
    h=H/'discovery';h.mkdir();assert json.loads((H/'settled.json').read_bytes())['fresh']>160
    out=h/'openssl';out.mkdir();(out/'bin').mkdir();src=out/'bin/cargo-show-ssl-native'
    src.write_text('#!/bin/sh\nprintf "%s\\n" "${SSL_CERT_FILE-}" "${SSL_CERT_DIR-}"\n');src.chmod(0o700)
    e=s.env();e['PATH']=str(out/'bin')+':'+e['PATH'];ca=output([s.CARGO,'+ohm','show-ssl-native'],env=e).splitlines()
    assert ca==['/etc/ssl/certs/ca-certificates.crt','/usr/lib/ssl/certs'],ca
    s.emit(out/'observed.json',ca);expected=snap();s.emit(h/'start.json',{'before':expected,'native_exec':actual_processes()})
    subprocess.run(['/usr/bin/cc','-O2','-shared','-fPIC',H/'cg-shim.c','-o',h/'cg-shim.so'],check=True)
    for i in (1,2):
        d=h/str(i);d.mkdir()
        cmd=[s.CARGO,'+ohm','build','--lib','--locked','--offline','-j4']
        env=s.env();env.update(SSL_CERT_FILE=ca[0],SSL_CERT_DIR=ca[1],OHM_PRIVATE_CG_OUT=str(d),OHM_PRIVATE_CG_ROOT=str(TOOL),OHM_PRIVATE_CG_TOOL='cargo',LD_PRELOAD=str(h/'cg-shim.so'))
        run=subprocess.run(cmd,cwd=s.SRC/'crates/ruff_linter',env=env,capture_output=True)
        (d/'stdout').write_bytes(run.stdout);(d/'stderr').write_bytes(run.stderr)
        assert run.returncode==0 and not run.stdout and b'Compiling' not in run.stderr and b'Finished' in run.stderr,(i,run.returncode,run.stderr[-500:])
        f,=d.glob('callgrind.*');sdata=f.read_text().splitlines()
        assert 'events: Ir' in sdata
        val,=[int(l.split()[1]) for l in sdata if l.startswith('summary:')];final,=[int(l.split()[1]) for l in sdata if l.startswith('totals:')]
        assert val>20000000 and abs(val-final)<2000000,(val,final)
        args_files=list(d.glob('*-cargo.args'));assert len(args_files)==1
        actual=[os.fsdecode(b) for b in args_files[0].read_bytes().strip(b'\0').split(b'\0')]
        assert actual[1:]==cmd[2:] and Path(actual[0]).resolve()==s.SDK/'bin/cargo',actual
        end=snap()
        assert end==expected,(expected,end)
        s.emit(d/'verified.json',{'ir':val,'total':final,'released_cargo':s.sha(s.SDK/'bin/cargo'),'actual':actual,'profile':s.sha(f),'active_caches':end,'elf_sha':s.sha(h/'cg-shim.so')})
        for incl in ('no','yes'):
            with (d/('functions-'+incl+'.txt')).open('w') as w:
                subprocess.run([TOOL/'usr/bin/callgrind_annotate','--inclusive='+incl,'--auto=no','--show-percs=no','--threshold=100',f],stdout=w,check=True)
    print('complete')
if __name__=='__main__':
    os.umask(0o077);os.sched_setaffinity(0,range(8))
    with (P/'member-build-native.lock').open('a') as l:
        fcntl.flock(l,fcntl.LOCK_EX|fcntl.LOCK_NB);main()
