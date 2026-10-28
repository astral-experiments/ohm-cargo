import sys,subprocess,json,os,fcntl,collections,re
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent));import setup as s
from profile import snap
H=s.H;D=H/'counter-sdk';B=H/'scoped-block';o=B/'rows';o.mkdir()
ref=json.loads((H/'dr-calibration/native-recovered/summary.json').read_bytes())
def run(i):
    d=o/str(i);d.mkdir()
    e=s.env();e.update(OHM_PRIVATE_DR_MODULE=str(B/'build/libscopecost.so'),OHM_PRIVATE_DR_OUT=str(d),OHM_PRIVATE_DR_TOOL='cargo',OHM_PRIVATE_DR_ROOT=str(D),LD_PRELOAD=str(H/'dr-calibration/dispatch.so'),SSL_CERT_FILE='/etc/ssl/certs/ca-certificates.crt',SSL_CERT_DIR='/usr/lib/ssl/certs')
    cmd=[s.CARGO,'+ohm','build','--lib','--locked','--offline','-j4']
    p=subprocess.run(cmd,cwd=s.SRC/'crates/ruff_linter',env=e,capture_output=True)
    (d/'stdout').write_bytes(p.stdout);(d/'stderr').write_bytes(p.stderr);assert p.returncode==0 and not p.stdout and b'Finished' in p.stderr and b'Compiling' not in p.stderr,(p.returncode,p.stderr[-340:])
    c,=d.glob('profile-*');rows=[v.split() for v in c.read_text().splitlines()]
    tids=sorted(r[1] for r in rows if r[0]=='T');end=sorted(r[1] for r in rows if r[0]=='F' and r[2]=='0')
    assert rows[0][0]=='B' and rows[-1]==['E',rows[0][1],'1'] and len(tids)==len(set(tids)) and tids==end,(rows[-2:],tids,end)
    table=collections.Counter()
    for r in rows:
        if r[0]=='I':table[int(r[2])]+=int(r[3])
    def cost(require,forbid=0):return sum(n for bits,n in table.items() if bits&require==require and not bits&forbid)
    groups={'all':cost(0),'output-graph':cost(1),'output-graph+parse':cost(3),'output-graph+decode':cost(5),'output-graph+pathhash':cost(17),'output-graph+pathcmp':cost(33),'freshness-parse':cost(2,1),'input-checksums':cost(8),'blake3-avx2-in-read':cost(72),'blake3-sse-in-read':cost(136),'output-hash-compare-no-parse':cost(17,2)+cost(33,2),'output-graph-exclusive-of-parse':cost(1,2)}
    assert 435e6<groups['all']<475e6 and snap()==ref['cache'] and s.sha(H/'target/debug/libruff_linter.rlib')==ref['rlib'],groups
    s.emit(d/'verified.json',dict(groups=groups,raw=s.sha(c),bins=table,threads=tids))
    print(i,groups,flush=True)
with (s.P/'member-build-native.lock').open('a') as l:
    fcntl.flock(l,fcntl.LOCK_EX);os.sched_setaffinity(0,range(8));run(0);run(1)
