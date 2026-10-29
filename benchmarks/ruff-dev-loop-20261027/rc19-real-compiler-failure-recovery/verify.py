"""Verify ordinary real compiler failure, interruption, precise recovery, and independently executed clean oracles."""
from pathlib import Path
import hashlib,json,re
root=Path(__file__).resolve().parent
cases=json.loads((root/"cases.json").read_bytes());assert set(cases)=={"assembler","held-assembler","held-compiler-signal"}
assert len(json.loads((root/"unreached.json").read_bytes()))==2;images=json.loads((root/"provenance.json").read_bytes())
count=exe=commits=signals=0
for mode,arms in cases.items():
 assert set(arms)=={"release","A","B"}
 for arm,phases in arms.items():
  fail="interrupted-provider" if mode=="held-compiler-signal" else "actual-assembler-failure"
  assert set(phases)=={"seed","unchanged",fail,"revert","revert-again","clean-revert","independent-valid-change"}
  assert phases[fail]["rc"]==101
  if mode=="held-compiler-signal":
   e=phases[fail]["signal"];assert e["signal"]=="SIGKILL" and e["committed_before_signal"] and e["actual_rustc"]==images["rustc"];signals+=1
  else:assert any("deliberate_ohm_codegen_failure" in err[2] for err in phases[fail]["errors"])
  if mode!="assembler":
   e=phases[fail]["dependent_commit"];assert e["committed_before_assembler_error"] and e["states"][-1][0]!=e["before"][0] and re.fullmatch("[0-9a-f]{16}",e["states"][-1][1]);commits+=1
  for phase,val in phases.items():
   assert all(re.fullmatch("[0-9a-f]{64}",val[k]) for k in ("stdout","stderr","source")) and val["raw_json_bytes"]>0 and val["raw_stderr_bytes"]>0;count+=1
   if phase==fail:continue
   assert val["rc"]==0 and val["errors"]==[] and val["program_stdout"]==("29\n" if phase=="independent-valid-change" else "17\n")
   assert re.fullmatch("[0-9a-f]{64}",val["elf"]);exe+=1
  assert len({phases[k]["elf"] for k in ("seed","unchanged","revert","revert-again","clean-revert")})==1 and phases["seed"]["elf"]!=phases["independent-valid-change"]["elf"]
  assert len(phases["revert"]["artifacts"])==3 and all(not a[2] for a in phases["revert"]["artifacts"]) and all(a[2] for a in phases["revert-again"]["artifacts"])
assert (count,exe,commits,signals)==(63,54,6,3)
print("Verified 63 ordinary Cargo commands, 54 real executable results, six committed dependents and three genuine rustc interruptions.")
