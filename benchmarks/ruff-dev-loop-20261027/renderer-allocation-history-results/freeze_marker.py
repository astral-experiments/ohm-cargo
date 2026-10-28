"""Bind the second entire historical change before discovering either compiler outcome."""
from pathlib import Path as P
import hashlib,json,subprocess,tempfile
d=P(__file__).resolve().parent;repo='/home/dev-user/code/oss/ruff';git=lambda *a:subprocess.check_output(['git','-C',repo,*a]);H=lambda x:hashlib.sha256(x).hexdigest();pin='93526150df078af7dd8fc4226cdcc469539d2001';rev='2e64753372956af0578c56cfb0e5b655bd21e54a'
p=git('show','--binary','--full-index','--format=',rev);(d/'marker.patch').write_bytes(p);files=git('diff-tree','--no-commit-id','-r','--name-only',rev).decode().splitlines();assert len(files)==4 and sum('/src/'in f for f in files)==1
stim=git('show',pin+':crates/ruff_annotate_snippets/tests/ruff.rs').decode().split('fn patch_with_primary_cell() {\n',1)[1].split('    let expected_ascii',1)[0];r=('use annotate_snippets::{AnnotationKind, Level, Patch, Renderer, Snippet};\nfn main() {\n'+stim+'println!("{}",Renderer::plain().render(input));\n}\n').encode();(d/'marker-reader.rs').write_bytes(r)
with tempfile.TemporaryDirectory() as tmp:
 t=P(tmp)
 for f in files:
  tf=t/f;tf.parent.mkdir(parents=True,exist_ok=True);tf.write_bytes(git('show',pin+':'+f))
 before={f:H((t/f).read_bytes())for f in files};subprocess.run(['git','apply','--reverse','--check','-'],cwd=t,input=p,check=True);subprocess.run(['git','apply','--reverse','-'],cwd=t,input=p,check=True);after={f:H((t/f).read_bytes())for f in files}
 out={'pin':pin,'revision':rev,'files':files,'sha_original':before,'sha_edit':after,'patch':H(p),'caller':H(r),'reason':'The sole other recent renderer source change in the bounded 25-commit first-parent-list same-file screen that completely reverse-applies to pinned Ruff. Its two private function sites keep line count fixed, differing by four total source bytes. The change has a genuine shifted notebook patch-origin marker. Selection used source only before package outcomes.','compiled_guard':{'original':' ::: cell 1:2:8','edited':' --> cell 1:2:8'},'primary_paths':['ordinary cargo +ohm build -p ruff_annotate_snippets --lib with each of the three existing compiler arms, native external reader over current .rlib','Only if both source variants cleanly share public identity on the fixed arm and prior warm falsely diverges, trial authentic joint CLI compiles with clean/fresh references. No timing, no speed claim until replicated.']}
 (d/'marker-plan.json').write_text(json.dumps(out,sort_keys=True,indent=2)+'\n')
print(H((d/'marker-plan.json').read_bytes()),H(p),H(r))
