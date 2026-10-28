"""Verify the v3b parent and compare the literal scorer, allocator, stock checks and test readers."""
import ast,hashlib,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def check(old):
    manifest=h(old/'SHA256SUMS');assert manifest=='2db9f4a735f6ebaab6f86c77e5643d6a99dd00c7691d62de2bb1e168720ce3c8'
    entries={n:v for v,n in (s.split('  ',1) for s in (old/'SHA256SUMS').read_text().splitlines())};assert all(h(old/n)==v for n,v in entries.items())
    changed=sorted(n for n,v in entries.items() if h(HERE/n)!=v)
    possible={'BINDING.md','README.md','catalog.py','continuation.py','runner.py','native_registration.py','check_native_registration.py','check_continuation.py','check_result_reader.py','continuation-selftest.json','reader-selftest.json'}
    assert set(changed)<=possible
    assert (HERE/'runner.py').read_text().replace('v3c','v3b')==(old/'runner.py').read_text()
    assert (HERE/'catalog.py').read_text().replace('wall-launch-v3c','wall-launch-v3b')==(old/'catalog.py').read_text()
    def defs(file):return {f.name:ast.dump(f) for f in ast.parse(file.read_bytes()).body if isinstance(f,ast.FunctionDef)}
    a,z=defs(old/'continuation.py'),defs(HERE/'continuation.py');assert set(a)==set(z) and {k for k in a if a[k]!=z[k]}=={'registrations','preservation','admissions'}
    preserved=['plan.json','analysis.py','clock.py','elf.py','guards.py','verify_result.py','historical-links.json.gz','ci-exact-heads.json','retained-native-bindings.json']
    assert all(h(HERE/n)==entries[n] for n in preserved)
    return dict(parent_wall='18d39259d88610e634243199b707c5435a506d77',parent_manifest=manifest,byte_identical={n:entries[n] for n in preserved},
                all_cargo_and_score_runner_code_identical_after_routing_only=True,all_native_catalog_code_identical_after_routing_only=True,changed_previous_files=changed)
if __name__=='__main__':print(json.dumps(check(Path(sys.argv[1])),sort_keys=True,indent=2))
