"""Apply the existing pinned instruction counter to the verified genuine parser (same image only)."""
from pathlib import Path
import sys
root=Path(__file__).resolve().parent
program=root/"overhead-v3-r2/parser-overhead-v3.py"
sys.argv=[str(program),"qualify"]
sc={"__file__":str(program),"__name__":"__main__"}
exec(compile(program.read_text().split('with (P/"native-measure.lock")')[0],str(program),"exec"),sc)
globals().update({k:v for k,v in sc.items() if not k.startswith("__")})
from collections import Counter
import struct
base=O
O=J/"scoped-parser-instructions-aa1";dr=J/"parser-counter-sdk-v1"
def ar_contents(f):
    b=f.read_bytes();assert b[:8]==b"!<arch>\n";i=8;names=b""; rows=[];ids={};table=None
    while i<len(b):
        p=i;a=b[i:i+60];assert a[-2:]==b"`\n";n=a[:16].decode().strip();l=int(a[48:58].strip());x=b[i+60:i+60+l];i+=60+l+(l%2)
        if n=="//":names=x;continue
        if n in {"/","/SYM64/"}:assert n=="/";table=x;continue
        if n.startswith("/") and n[1:].isdigit():n=names[int(n[1:]):].split(b"/\n")[0].decode()
        n=n.removesuffix("/");ids[p]=len(rows)
        if n.endswith('.o'):group='object'
        elif n=='lib.rmeta':group='metadata'
        elif n=='lib.rmeta-link':group='member directory'
        else:group=n
        rows.append((group,hashlib.sha256(x).hexdigest() if group!='member directory' else None))
    assert table; num=int.from_bytes(table[:4],"big");idx=4+num*4
    syms=table[idx:].split(b'\x00')[:num];assert len(syms)==num
    normalized=b''.join(s+b'\x00'+ids[int.from_bytes(table[4+4*k:8+4*k],"big")].to_bytes(4,'little') for k,s in enumerate(syms))
    return {"rows":rows,"symbol_count":num,"symbol_to_ordinal_sha256":hashlib.sha256(normalized).hexdigest()}
with (P/"native-measure.lock").open("a") as lock:
    fcntl.flock(lock,fcntl.LOCK_EX);gate_free(J,2**30);O.mkdir(mode=0o700);skeleton_base=skeleton(O);sc.update(O=O,skeleton_base=skeleton_base)
    for n in ('parent',):
        (O/'qualification'/n).mkdir(parents=True);(O/'qualification'/n/'training').symlink_to(base/'qualification'/n/'training',target_is_directory=True)
    print('tool',sha(dr/'client/libpidcounter.so'),sha(dr/'sdk/bin64/drrun'),flush=True)
    assert sha(dr/'client/libpidcounter.so')==load(dr/'binary-shas.json')['client/libpidcounter.so']
    inner=inner.replace('p=subprocess.run(argv,stdout=f,stderr=e)',f'p=subprocess.run([{str(dr/"sdk/bin64/drrun")!r},"-no_follow_children","-c",{str(dr/"client/libpidcounter.so")!r},str(d/"counter.txt"),"--",{str(P/"rustup/toolchains/ohm/bin/rustc")!r},*argv[2:]],stdout=f,stderr=e,timeout=300)')
    (O/"inner.py").write_text(inner);rows=[]
    for i,h in enumerate(['empty','retained','retained','empty','empty','retained']):
        d=O/f"{i:02d}-{h}"
        z=run(d,"parent",h)
        gold=load(base/'qualification'/'parent'/h/'result.json');assert roots(z)==roots(gold),(i,'metadata did not match')
        glob=md.with_suffix('.rlib').name;old=ar_contents(base/'qualification'/'parent'/h/'out'/glob);new=ar_contents(d/'out'/glob);
        dump(d/'archive-oracle.json',{'native':old,'instrumented':new,'equal':old==new})
        assert old==new,(i,'native object/symbol oracle')
        ev=[(s,int(p),int(t),int(v)) for s,p,t,v in [s.split() for s in (d/'counter.txt').read_text().splitlines()]];pids={x[1] for x in ev}; typ=Counter(x[0] for x in ev)
        starts=Counter(t for s,p,t,v in ev if s=='T');ends=Counter(t for s,p,t,v in ev if s=='F')
        count=sum(v for s,p,t,v in ev if s=='F');assert ev[0][0]=='B' and ev[-1][0]=='P' and len(pids)==1 and starts==ends and len(ends)>=2 and count>100000000,(typ,starts,ends,count)
        z.update(instructions=count,thread_count=len(starts),record_counts=dict(typ),archive_verified=True);rows.append(z);dump(O/'observations.json',rows);print(i,h,count,len(starts),flush=True)
    dump(O/'complete.json',{'parent_only':True,'count':6,'rows':sha(O/'observations.json')})
