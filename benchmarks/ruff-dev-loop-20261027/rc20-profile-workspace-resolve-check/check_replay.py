"""Drive the portable controller protocol with typed stubs, without any Cargo or real mount."""
import importlib.util
import io
import json
from pathlib import Path
import re
import subprocess
import tempfile

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("portable_controller",HERE/"replay.py")
controller=importlib.util.module_from_spec(spec)
spec.loader.exec_module(controller)


def test(mechanism,broken):
    visits=[]
    class Worker:
        def __init__(self,argv,**kwargs):
            self.argv=argv
            self.arm=argv[-4]
            self.out=Path(argv[-1])
            assert self.arm in "CAB"
            # Validate the generated POSIX mount script syntactically, without executing it.
            code=argv[argv.index("-ec")+1]
            subprocess.run(["sh","-n"],input=code,text=True,check=True)
            self.reply="READY"
            self.stdin=io.StringIO()
            self.stdout=io.StringIO()
            self.closed=False
        def read(self):
            self.stdin.seek(0)
            lines=self.stdin.readlines()
            self.stdin.seek(0);self.stdin.truncate()
            if not lines:return self.reply
            assert len(lines)==1
            tag,source,kind=lines[0].split()
            visits.append((self.arm,tag,source,kind))
            if kind=="finish":
                self.closed=True
                return '{"closed":true}'
            if kind in ("hydrate","trace"):
                value="unexpected" if broken and self.arm=="B" and tag=="03-settled" else "same"
                edited=tag in ("01-edited","02-restored","04-reverse","06-restore")
                full=int(self.arm=="A" and edited)
                (self.out/(tag+".json")).write_text(json.dumps({"files":[value],"roster":[],"oracle":[],"full":full,"hits":1-full}))
                return json.dumps({"row":tag,"ns":None})
            assert kind=="wall"
            return json.dumps({"row":tag,"ns":len(visits)})
        def wait(self,timeout):
            return 0
        def poll(self):
            return 0
    old_popen=controller.sp.Popen
    old_reader=controller.read_worker
    def fake_popen(cmd,**kwargs):
        if cmd[0]=="sh":
            return old_popen(cmd,**kwargs)
        return Worker(cmd,**kwargs)
    controller.sp.Popen=fake_popen
    controller.read_worker=lambda worker:worker.read()
    try:
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            (root/"results").mkdir()
            try:
                controller.campaign("check",{"scratch":temporary,"cpus":[0,1,2,3],"mechanism_only":mechanism},root/"config",
                                    {arm:("cargo-"+arm,arm) for arm in "AB"})
            except RuntimeError as err:
                assert broken and str(err)=="unequal preclock products",err
                assert not any(v[-1]=="wall" for v in visits)
                return
            assert not broken
            term=json.loads((root/"results"/"toml-check-v1"/"terminal.json").read_bytes())
            if mechanism:
                assert not any(v[-1]=="wall" for v in visits) and len(term["controls"])==14
                assert len([v for v in visits if v[-1] in ("hydrate","trace")])==20
            else:
                expected=[(a,f"{i:02}-{phase}",source,"wall") for i,_,source,a,phase in controller.schedule()]
                assert [v for v in visits if v[-1]=="wall"]==expected and len(term["events"])==128
    finally:
        controller.sp.Popen=old_popen
        controller.read_worker=old_reader


if __name__=="__main__":
    for mode in (False,True):
        for broken in (False,True): test(mode,broken)
    print("Passed the 128-slot and no-clock controllers with matching and mismatching mock inputs.")
