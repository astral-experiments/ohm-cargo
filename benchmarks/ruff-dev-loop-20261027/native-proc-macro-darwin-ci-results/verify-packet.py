import hashlib, json, os, tempfile, zipfile, sys
from pathlib import Path
sys.dont_write_bytecode = True
import runpy
root = Path(__file__).resolve().parent
verify = runpy.run_path(str(root / "verify.py"))["verify"]
j=lambda name: json.loads((root/name).read_bytes())
h=lambda b: hashlib.sha256(b).hexdigest()
a = j('artifact.json')
assert a['id']==12836215731 and a['name']=='native-proc-macro-darwin'
assert a['digest']=="sha256:0c40fb701af66465108e12da0db851c7c0593d68536c184529b7af2e147a14e0"
assert a['size_in_bytes']==(root/'native-macro-darwin.zip').stat().st_size==17623
assert a['digest']=='sha256:'+h((root/'native-macro-darwin.zip').read_bytes())
with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(root/'native-macro-darwin.zip') as z:
    assert not z.testzip()
    names=z.namelist()
    assert len(set(names))==len(names)
    assert all(not Path(n).is_absolute() and '..' not in Path(n).parts for n in names)
    z.extractall(tmp)
    result=verify(tmp)
    prim=(Path(tmp)/'checked-in-run-make.txt').read_text().strip()
    assert result==j('verification.json')
    reported={k:result[k]['values'] for k in ('stock','fixed')}
    for n in ('native.rs','reader.rs'):
        assert all(result[r]['inputs'][n]==h((root/'source'/n).read_bytes()) for r in result)
    actual={k:reported['stock'][k] for k in ('edited','repeat','edited-empty')}
    assert actual=={'edited':'17,17','repeat':'17,17','edited-empty':'29,29'}
source=j('source.json')
assert source['compiler_tree']=='47e23eb4bab742e271ca9a3cf1bbd583d5b4a640'
assert source['qualified']==a['workflow_run']['head_sha']=='a34f48d944280a5de0bcf8a49c3d0cdb24082fd8'
assert source['qa_parent']==source['release_candidate']=='9828b82f475f18bf9077ee25f36de43d4fec8277'
assert sorted(source['changed_paths'])==['.github/workflows/ci.yml','tests/run-make/incremental-proc-macro-native-inputs/qualify-darwin.py']
for name,meta in source['files'].items():
    data=(root/'source'/Path(name).name).read_bytes()
    assert h(data)==meta['sha256'] and hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==meta['git_blob']
wf=(root/'source/ci.yml').read_text()
arg='python3 x.py --ci false --set build.submodules=false --set rust.debug-assertions=true --set rust.lto=off test --stage 1 "$CASE"'
case='CASE: tests/run-make/incremental-proc-macro-native-inputs'
assert 'contents: read' in wf and case in wf and arg in wf
jlog=j('job-witness.json')
lines=[row['text'] for row in jlog['selected']]
cmd=[i for i,s in enumerate(lines) if arg in s]
assert len(cmd)==1
env=next(i for i,s in enumerate(lines) if i>cmd[0] and case in s)
setup=next(i for i,s in enumerate(lines) if i>env and 'Testing stage1 with compiletest suite=run-make mode=run-make (aarch64-apple-darwin)' in s)
assert any(prim in s for s in lines[setup+1:])
native=[json.loads(t.split('DARWIN_NATIVE_VALUES ',1)[1]) for t in lines if 'DARWIN_NATIVE_VALUES ' in t]
assert native==[reported['stock'],reported['fixed']]
run=j('run.json')
assert run['headSha']==source['qualified'] and run['conclusion']=='success'
job,=run['jobs']
assert job['databaseId']==jlog['job']==122966381461 and job['conclusion']=='success'
assert all(s['conclusion']=='success' for s in job['steps'])
release=j('release.json')
assert any(a['name'].endswith('darwin.tar.gz') and a['digest']=='sha256:e58f5ce47b9dd2dbee8c47a7850fb3aec53066c1c781daa3f955ae201f3cb92b' for a in release['assets'])
assert h((root/'mac-release-provenance.json').read_bytes())=='e61f200d09fcd9b84f215032916b55673fa7de33c3ea4f8dbee1070819505fbf'
print(f"PASS: verified {len(names)} original archive entries, 40 process records, 12 actual reader outputs, checked-in run-make (1 passed, 0 ignored), and source bindings.")
