"""Exercise the predeclared process classifier and phase-specific fallback and eligibility gates."""
import json, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import processes
from unittest.mock import patch

class MixedTraceTests(unittest.TestCase):
    def run_trace(self, mode, scenario):
        # One rustc checked process can fall back without spawning a distinct full rustc.
        # Its retained recipe's unchanged physical timestamp and digest distinguish that case.
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); tool=root/'tool/bin';tool.mkdir(parents=True);(tool/'cargo').touch()
            rows=[(tool/'cargo',['cargo',mode])];before={};after={}
            for name in ['ruff_python_parser']+(['ruff_python_parser','api','api'] if mode=='test' else []):
                rows.append((tool/'rustc',['rustc','--crate-name',name]))
            for j,crate in enumerate(('ruff_wasm','ty_wasm')):
                recipe=str(root/(crate+'.rlink'))
                before[recipe]=['a',100,10];after[recipe]=['a' if scenario!='rewrite-data' else 'b',100 if scenario!='rewrite-mtime' else 200,10]
                args=['rustc','--crate-name',crate,'-L','dependency='+str(root)]
                if scenario!='no-capability':args+=['-Z','ohm-checked-mixed-rlink='+recipe]
                rows.append((tool/'rustc',args))
            for i in range(6 if mode=='build' else 62):rows.append((tool/'rustc',['rustc','--crate-name','ordinary','-Z','link-only']))
            for i in range(8 if mode=='build' else 67):
                for n in ('cc','collect2','wild-ld/ld.bfd'):rows.append((tool/n,[n,'-o','ordinary-elf']))
            for i,(exe,args) in enumerate(rows):
                entry='execve('+json.dumps(str(exe))+', '+json.dumps(args)+', 0x7fff /* 5 vars */) = 0'
                if i==1:entry=entry.replace(', 0x7fff',',  <unfinished ...>\n<... execve resumed>0x7fff')
                (root/f'exec.{1000+i}').write_text(entry+'\n')
            with patch.object(processes,'FROZEN',root/'tool'):
                return processes.parse(root,mode,before,after)

    def test_scored_hits(self):
        for mode in ('build','test'):
            traces=self.run_trace(mode,'hit')
            processes.qualify(traces,mode,'C','edit')
            with self.assertRaises(ValueError):processes.qualify(traces,mode,'C','forced')

    def test_cold_fallback_and_rewritten_same_bytes(self):
        for mode in ('build','test'):
            for scenario in ('rewrite-data','rewrite-mtime'):
                rows=self.run_trace(mode,scenario)
                for phase in ('conditioning','forced'):processes.qualify(rows,mode,'C',phase)
                with self.assertRaises(ValueError):processes.qualify(rows,mode,'C','edit')

    def test_arms_without_the_protocol(self):
        for mode in ('build','test'):
            rows=self.run_trace(mode,'no-capability')
            for arm in 'AB':
                for phase in ('conditioning','edit'):processes.qualify(rows,mode,arm,phase)
            with self.assertRaises(ValueError):processes.qualify(rows,mode,'C','edit')

if __name__=='__main__':unittest.main()
