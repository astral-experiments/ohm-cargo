"""One explicit cached-codegen sensitivity control on the new Cargo and compiler."""
import hashlib,json,sys
from pathlib import Path

sdk,dest=(Path(v).resolve() for v in sys.argv[1:])
full=(Path(__file__).resolve().parent/"assembler.py").read_text()
shared,_=full.split('payload.write_bytes(bytes([17]))\nstep("old-original"',1)
needle='state if store is None else store,[])'
assert shared.count(needle)==1
shared=shared.replace(needle,'state if store is None else store,["-Zrelink-only=yes"])')
sys.argv=[__file__,str(sdk),str(sdk),str(dest)]
ctx={"__name__":"__main__","__file__":__file__}
exec(compile(shared,__file__,"exec"),ctx)
payload=ctx["payload"]; root=ctx["root"]; step=ctx["step"]; api=ctx["context"]
payload.write_bytes(bytes([17]))
step("initial","5:17")
api["put"](root/"revision/src/lib.rs",api["revision"](9))
payload.write_bytes(bytes([29]))
got=step("updated","9:17",strict=False)
clean=step("independent","9:29",dest/"empty")
r=ctx["rows"]
assert clean=="9:29" and got=="9:17"
assert ["app",True] in r["updated"]["physical_rustcs"] and r["updated"]["physical_wild"] and not r["updated"]["physical_payload_reads"]
assert ["app",False] in r["independent"]["physical_rustcs"] and r["independent"]["physical_payload_reads"]
ctx["put"](dest/"result.json",{"cargo":api["sha"](sdk/"bin/cargo"),"rustc":api["sha"](sdk/"bin/rustc"),"flags":["-Zrelink-only=yes"],"rows":r})
