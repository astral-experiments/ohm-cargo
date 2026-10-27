"""Cap one prospective instruction comparison; stop and preserve partial results on any gate mismatch."""
from pathlib import Path
from collections import Counter
import argparse, hashlib, json, re, shutil, sys

home=Path(__file__).resolve().parent
cli=argparse.ArgumentParser();cli.add_argument("phase",choices=["calibrate","score"]);cli.add_argument("--admission");par=cli.parse_args()
source=home/"parser-instruction-calibration.py";text=source.read_text()
sc={"__file__":str(home.parent/"parser-instruction-calibration.py"),"__name__":"__main__"}
exec(compile(text.split('\nwith (P/"native-measure.lock")')[0],str(source),"exec"),sc)
globals().update({k:v for k,v in sc.items() if not k.startswith("__")})
import tempfile
official=initial if "initial" in globals() else base
O=J/"scoped-parser-ir-holdout-v3";newplan=load(home/"plan.json")
assert sha(home/"parser-ir-holdout.py")==newplan["runner"] and sha(home/"parser-ir-inner.py")==newplan["inner"]
assert sha(home/"parser-instruction-calibration.py")==newplan["calibration_source"]
assert sha(program)==newplan["native_runner"] and sha(planpath)==newplan["native_protocol"]
sealed=load(official/"qualification/complete.json")
assert sha(official/"qualification/complete.json")==newplan["native_certificate"]
sdkhash=load(Path(newplan["collector"]["manifest_path"]));assert sdkhash==newplan["collector"]["actual_files"]
for k,v in sdkhash.items():assert sha(dr/k)==v,k
def names_and_link(f):
    b=f.read_bytes();i=8;names=b"";members=[];link=None
    while i<len(b):
        a=b[i:i+60];n=a[:16].decode().strip();l=int(a[48:58].strip());x=b[i+60:i+60+l];i+=60+l+(l%2)
        if n=="//":names=x;continue
        if n in {"/","/SYM64/"}:continue
        if n.startswith("/") and n[1:].isdigit():n=names[int(n[1:]):].split(b"/\n")[0].decode()
        n=n.removesuffix("/")
        if n=="lib.rmeta-link":assert link is None;link=x
        if n.endswith(".o"):members.append(n)
    assert isinstance(link,bytes) and len(set(members))==len(members)
    normalized=[]
    for name in members:
        canonical=re.sub(r"\.[0-9a-z]{7}\.rcgu\.o$",".0000000.rcgu.o",name)
        assert len(canonical)==len(name)
        src=name.encode();assert link.count(src)==1,(name,"rmeta-link member references")
        link=link.replace(src,canonical.encode());normalized.append(canonical)
    assert len(set(normalized))==len(normalized)
    return {"stable_member_names":normalized,"normalized_rmeta_link_sha256":hashlib.sha256(link).hexdigest()}
def compare_elf(w,arm,h,receipt=None):
    nm=md.with_suffix('.rlib').name;native=official/'qualification'/arm/h/'out'/nm
    got=w/'out'/nm
    a,b=ar_contents(native),ar_contents(got)
    c,e=names_and_link(native),names_and_link(got)
    out={"native":a,"instruction_counted":b,"native_names":c,"instruction_counted_names":e,"exact_object_payloads":a==b and c==e}
    dump(receipt if receipt is not None else w/'native-archive.json',out);assert a==b and c==e,(arm,h,'native CGU and link directory gate')
    return len(a["rows"]),a["symbol_count"]
def recorded(w):
    events=[(s,int(p),int(t),int(v)) for s,p,t,v in (line.split() for line in (w/'counter.txt').read_text().splitlines())]
    types=Counter(s for s,p,t,v in events);pids={p for s,p,t,v in events}
    starts=Counter(t for s,p,t,v in events if s=="T");ends=Counter(t for s,p,t,v in events if s=="F")
    assert types["B"]==types["P"]==1 and events[0][0]=="B" and events[-1][0]=="P" and len(pids)==1
    assert not types["E"],"unexpected secondary exec"
    assert starts==ends and len(starts)>1 and all(k==1 for k in starts.values())
    signals=[v for s,p,t,v in events if s=="S"]
    assert all(v==10 for v in signals),("unexpected application signal",signals)
    total=sum(v for s,p,t,v in events if s=="F");assert total>100000000
    maps=load(w/'mappings.json');assert maps["complete"] and not maps["timed_out"] and {v["pid"] for v in maps["captured"].values()}==pids
    return {"instructions":total,"thread_count":len(ends),"events":dict(types),"signal_values":signals,"raw_counter":sha(w/"counter.txt"),"mapping_receipt":sha(w/"mappings.json")}
def trial(dest,arm,h):
    dest.mkdir()
    # Writable products stay in this owned trial until its native proof and ledger have been sealed.
    w=dest/'physical';res=run(w,arm,h);assert roots(res)==roots(sealed['oracles'][arm][h]),(arm,h,"native rustc metadata")
    cnt=recorded(w);members,symbols=compare_elf(w,arm,h)
    native=official/'qualification'/arm/h
    control=(J/'scoped-parser-instructions-aa1/00-empty/stderr').read_bytes()
    expected=(native/'stderr').read_bytes()
    prefix=control[:control.index(b'{"$message_type"')]
    assert sha(w/'stdout')==sha(native/'stdout') and (w/'stderr').read_bytes()==prefix+expected
    assert (w/'launcher.stderr').read_bytes()==(native/'launcher.stderr').read_bytes()
    res.update(cnt,archive_member_count=members,gnu_symbols=symbols,ordered_archive=sha(w/'native-archive.json'),compiler_stdout=sha(native/'stdout'),compiler_stderr=sha(native/'stderr'),collector_stderr_prefix=hashlib.sha256(prefix).hexdigest())
    dump(dest/'outcome.json',res);return res
with (P/"native-measure.lock").open("a") as lock:
    fcntl.flock(lock,fcntl.LOCK_EX);gate_free(J,8*2**30)
    sc['O']=O;sc_new=run.__globals__;sc_new['O']=O
    if par.phase=="calibrate":
        assert not O.exists();O.mkdir(mode=0o700);skeleton_base=skeleton(O);dump(O/"namespace.json",skeleton_base)
        shutil.copyfile(home/"parser-ir-inner.py",O/"inner.py")
        init={"sdk":str(dr),"frontend":str(P/"rustup/toolchains/ohm/bin/rustc"),"mapped":{"frontend":str(FROZEN/"bin/rustc"),"driver":str(FROZEN/"lib"/driver_name),"derive":rs['warm']['get_size_derive']}}
        init["mapped"]["runtime"]=str(dr/"sdk/lib64/release/libdynamorio.so")
        init["mapped"]["client"]=str(dr/"client/libpidcounter.so")
        dump(O/"inner-binding.json",init);q=O/"qualification"
        for arm in ('parent','candidate'):
            f=q/arm;f.mkdir(parents=True);(f/'training').symlink_to(official/'qualification'/arm/'training',target_is_directory=True)
        sc_new['skeleton_base']=skeleton_base
        # Authenticate all six existing A/A artifact contracts without a single counted candidate.
        cal=J/"scoped-parser-instructions-aa1";rc=load(cal/'observations.json');assert len(rc)==6 and all(r["arm"]=="parent" for r in rc)
        old=[];(O/'six-native-oracles').mkdir()
        for i,row in enumerate(rc):
            h=row["history"];old.append({"row":i,"history":h,"native_archive":compare_elf(cal/f"{i:02d}-{h}","parent",h,O/'six-native-oracles'/f"{i:02d}-{h}.json")})
        # One blind parent only to validate current per-PID executable and plugin mmap receipt.
        q0=trial(O/"map-calibration-parent","parent","retained");dump(O/"inputs.json",verify_inputs())
        dump(O/"admission.json",{"protocol":sha(home/"plan.json"),"public_plan_worker":sha(home/"parser-ir-holdout.py"),"parent_only":True,"new_candidate_counts":0,"calibration":{"six":sha(cal/'observations.json'),"stronger_archive":old,"map_control":q0},"input_sha":sha(O/"inputs.json")})
    else:
        assert par.admission==sha(O/"admission.json") and load(O/"admission.json")["new_candidate_counts"]==0
        q=load(O/"admission.json");assert q["protocol"]==sha(home/"plan.json") and q["public_plan_worker"]==sha(home/"parser-ir-holdout.py") and q["input_sha"]==sha(O/"inputs.json") and verify_inputs()==load(O/"inputs.json")
        assert sha(O/"inner.py")==newplan["inner"]
        skeleton_base=load(O/"namespace.json");sc_new['skeleton_base']=skeleton_base;d=O/"score";d.mkdir();obs=[]
        for i,block in enumerate(newplan["blocks"]):
            for ep in block["endpoints"]:
                for arm in block[ep]:
                    v=trial(d/f"{i:02d}-{ep}-{arm}",arm,ep);obs.append({"pair":i,"endpoint":ep,**v});dump(d/"observations.json",obs)
        assert len(obs)==48 and verify_inputs()==load(O/"inputs.json")
        dump(d/"complete.json",{"complete_pairs_per_history":12,"observations":sha(d/"observations.json"),"registration":sha(home/"plan.json"),"admission":par.admission})
