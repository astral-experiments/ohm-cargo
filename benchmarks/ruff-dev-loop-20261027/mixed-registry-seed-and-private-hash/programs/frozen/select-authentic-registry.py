"""Select the first genuine older-compiler producer that exactly matches the preregistered shared object."""
from pathlib import Path
import collections, fcntl, hashlib, json, os, re, shutil, signal, subprocess, sys

x = Path.home()/".cache/ohm-233-position-qualified-20261027"
w=x/"mixed-native-abc-protocol-h3-v2";sys.path.insert(0,str(w))
from common import P, CARGO_HOME, TARGET, SHARED, FROZEN, RUFF, dump, load, need, sha, env
from state import gate_free, source_clean, source_binds
from namespace import spawn_args
from processes import records

root=P/"mixed-registry-only-pilot/older-authenticated-base"
program=x/"mixed-registry-seed-programs-20261027/match-frozen-prereg"
binding=load(w/"runner-binding.json")
registered=program/"registry-match-registration.json"
assert sha(registered)=="fa0208b35ea3a805475ae31ce9cd617a6ccf4d62c3b73f8f0dd44eb20f136bab"
ref=load(registered)["fixed_reference"];expected=ref["entire_shared_object_sha256"];arm=binding["arms"]["A"]
st=root/"physical";manifest=load(root/"projected.json");logical=Path(manifest["expected_proc_macro"])
unit=logical.parents[1];assert unit.name=="16667a986d3ac90d" and unit.parent.name=="get-size-derive2"
assert sha(st/"target"/logical)==manifest["expected_sha"]!=expected and load(root/"matched-environment.json")["actual_donor_inherited_PATH"]
assert (program/"cross-natural.rc").read_text().strip()=="1" and "different Cargo authenticated namespace" in (program/"cross-natural.reason").read_text()
assert manifest["arm"]==manifest["donor_arm"]=="A" and manifest["previous_workspace_artifacts"]==0
out=root/"selection";need(not out.exists(),out);out.mkdir(mode=0o700);dest_unit=st/"target"/unit
cfg=env();cfg["PATH"]=load(root/"matched-environment.json")["actual_donor_inherited_PATH"]
mount=load(root/"mount.json")
opts=spawn_args(mount,root,st,st/"registry-home",[],Path(arm["cargo"]),Path(arm["driver"]));ix=opts.index("--");opts[ix:ix]=source_binds(st)
assert all(sha(Path(arm[k]))==arm[k+"_sha256"] for k in ("cargo","driver"))
command=["cargo","+ohm","build","--locked","--offline","--message-format=json"]
summary=[];winner=None
def stop(p):
    if p.poll() is None:
        os.killpg(p.pid,signal.SIGTERM)
        try:p.wait(timeout=15)
        except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
with (P/"native-measure.lock").open("a") as lock:
    fcntl.flock(lock,fcntl.LOCK_EX)
    for i in range(1,25):
        gate_free(root,10*2**30);need(shutil.disk_usage(x).free>107*2**30 and source_clean()==manifest["source_index"],"storage/source gate")
        d=out/f"attempt-{i:02d}";d.mkdir()
        # Only move the owned original/previous unit. The immutable donor and every primary state remain untouched.
        need(dest_unit.is_dir() and not dest_unit.is_symlink() and not (d/"previous-target-unit").exists(),"attempt boundary")
        dest_unit.rename(d/"previous-target-unit")
        dumped=[];reading=None;rejected=False
        with(d/"stdout").open("xb") as so,(d/"stderr").open("xb") as se:
            p=subprocess.Popen([*opts,"strace","-ff","-qq","-s","1048576","-e","trace=execve,execveat,prctl","-o",str(d/"exec"),*command],
                               cwd=RUFF,env=cfg,stdout=subprocess.PIPE,stderr=se,start_new_session=True)
            try:
                for line in p.stdout:
                    so.write(line);so.flush();row=json.loads(line)
                    if row["reason"]!="compiler-artifact":continue
                    dumped.append(row)
                    if row["target"]["name"]=="get_size_derive2":
                        expected_path=TARGET/logical
                        need(reading is None and row["fresh"] is False and row["filenames"]==[str(expected_path)],("producer was not cold in actual old-compiler context",row))
                        actual=sha(st/"target"/logical)
                        reading={"attempt":i,"cargo":arm["cargo_sha256"],"driver":arm["driver_sha256"],"command":command,
                                 "target_artifact":row,"entire_so_sha256":actual,"matches":actual==expected}
                        dump(d/"producer.json",reading)
                        print("OBSERVED",i,actual,"match",reading["matches"],flush=True)
                        if actual!=expected:rejected=True;stop(p);break
                code=p.wait()
            except BaseException:stop(p);raise
        class ProducerTraces:
            def glob(self,pat):
                return [trace for trace in d.glob(pat) if b'"--crate-name", "get_size_derive2"' in trace.read_bytes()]
        actual_commands=[a for _,f,a in records(ProducerTraces()) if Path(f).name=="rustc" and "--crate-name" in a and a[a.index("--crate-name")+1]=="get_size_derive2"]
        need(len(actual_commands)==1 and reading is not None,("no unique real compile",i))
        reading.update(command_exit=code,interrupted_after_rejected_producer=rejected,full_json_artifacts=len(dumped),rustc_argv=actual_commands[0])
        dump(d/"producer.json",reading);summary.append(reading);dump(out/"all-attempts.json",summary)
        if reading["matches"]:
            need(not rejected and code==0 and len(dumped)==501 and sha(st/"target"/logical)==expected,"winning native command did not finish")
            winner=i
            break
    dump(out/"complete.json",{"winner":winner,"attempt_count":len(summary),"digest":expected,"reference_registration":sha(registered),
         "source_index":source_clean(),"timed_samples":0})
    print("FINISHED",winner,len(summary),flush=True)
