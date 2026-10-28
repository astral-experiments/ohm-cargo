"""Freeze the complete real generated-source file projection and native behavior checks."""
from pathlib import Path
import hashlib,json,subprocess,tempfile
d=Path(__file__).resolve().parent;r='/home/dev-user/code/oss/ruff';git=lambda *a:subprocess.check_output(['git','-C',r,*a]);H=lambda b:hashlib.sha256(b).hexdigest()
pin='93526150df078af7dd8fc4226cdcc469539d2001';commit='bfedc614b7670b8766576b64afd426c292f8c2ce';f='crates/ruff_unicode_names2_generator/src/formatting.rs'
pat=git('diff','--full-index','--binary',commit+'^',commit,'--',f);orig=git('show',pin+':'+f)
with tempfile.TemporaryDirectory() as tmp:
 dst=Path(tmp)/f;dst.parent.mkdir(parents=True);dst.write_bytes(orig);subprocess.run(['git','apply','-R','--check','-'],cwd=tmp,input=pat,check=True);subprocess.run(['git','apply','-R','-'],cwd=tmp,input=pat,check=True);edit=dst.read_bytes()
assert edit==orig.replace(b'pub static {}: &[{}] = &[',b"pub static {}: &'static [{}] = &[").replace(b'pub static {}: &str =',b"pub static {}: &'static str =")
reader=r'''use unicode_names2::{character, name};
fn main() {
    for (ch, official) in [('A',"LATIN CAPITAL LETTER A"), ('\u{2603}',"SNOWMAN"), ('\u{1f980}',"CRAB")] {
        assert_eq!(name(ch).unwrap().to_string(), official);
        assert_eq!(character(official), Some(ch));
        println!("{ch:?} {official}");
    }
    assert_eq!(character("LINE FEED"), Some('\n'));
    assert_eq!(character("THIS IS NOT AN OFFICIAL UNICODE NAME"), None);
    println!("LF alias and absent spelling checked");
}
'''.encode()
(d/'unicode-reader.rs').write_bytes(reader);(d/'unicode.patch').write_bytes(pat)
normalized={'command':['cargo','+ohm','build','--locked','--offline','--message-format=json','-p','ruff','--bin','ruff'],'file':f,'files':[f],'pin':pin,'commit':commit,'commit_files':len(git('diff-tree','--no-commit-id','--name-only','-r',commit).splitlines()),'patch':H(pat),'caller':H(reader),'original':H(orig),'edited':H(edit),'sha_original':{f:H(orig)},'sha_edit':{f:H(edit)},'frozen_inputs':{n:H(git('show',pin+':'+n))for n in ('crates/ruff_unicode_names2/build.rs','crates/ruff_unicode_names2/src/lib.rs','crates/ruff_unicode_names2/data/UnicodeData.txt','crates/ruff_unicode_names2/data/NameAliases.txt')},'release':json.loads((d/'plan.json').read_bytes())['release'],'source_scope':'One complete file in the published historical commit. Reversing it adds two explicit static lifetimes to Rust text literal templates. Other files in the commit stay pinned. The generator declares three actual .rs outputs and the library includes all three. Measure each separately, allow individual outputs to remain unchanged.','order':['original','original-repeat','edited','edited-repeat','restored','restored-repeat'],'proof':['Hold the authentic physically SHA-verified released 1.99.0-16 Cargo, rustc driver+frontend and Wild. Work in an already settled independently copied ordinary Ruff/ty native store under native lock. No timing. For all six ordinary commands keep all 373 Cargo units, complete physical Rust and Wild argv and exec exits, native product digests, build script stdout and output paths, trace and broad source inventory. Preserve actual rmeta/rlib member SHA and present-if-any program, metadata, proc macro, genuine temporary and output gaps.','For first, edit, restoration compile a fresh ordinary native external Unicode caller against the real Unicode library and require official Unicode names, reverse lookup, alias and unknown lookup. Inspect ruff invalid-name Python diagnostics and valid official name for all six invocations. Keep byte fractions in archive, qualified sections and unchanged bodies separate.','Only consider a candidate if a concrete observed same-input full compile or real link repeats that can be skipped without changing generated source bytes, source/diagnostic metadata, library names, body or native selection. Existing implicit linker script and unconditional proc-macro negatives remain binding. If actual native inputs differ, report the boundary. A performance PR additionally needs separate prospectively qualified wall or instruction measurement.']}
(d/'unicode-plan.json').write_text(json.dumps(normalized,sort_keys=True,indent=2)+'\n');print(H((d/'unicode-plan.json').read_bytes()),H(pat),H(reader),normalized['commit_files'])
