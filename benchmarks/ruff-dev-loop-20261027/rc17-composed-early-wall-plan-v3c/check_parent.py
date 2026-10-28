"""Compare every parent source file, including unmodified mechanics, with the registered base."""
import ast,hashlib,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def check(parent):
    manifest=parent/'SHA256SUMS'
    assert sha(manifest)=='9099beedd4c6a180c1c5747c077d1a45e1868e922dc594031d5ac4a292bfc9c4'
    records={name:h for h,name in (row.split('  ',1) for row in manifest.read_text().splitlines())}
    assert all(sha(parent/n)==h for n,h in records.items())
    changes={n for n,h in records.items() if sha(HERE/n)!=h}
    assert changes=={'BINDING.md','README.md','catalog.py','runner.py','native_registration.py','check_native_registration.py',
                     'check_result_reader.py','reader-selftest.json'}
    catalog=(HERE/'catalog.py').read_text()
    assert catalog.replace("'wall-launch-v3b'","'wall-launch-v3'").replace("'whole-wild-width-v2'","'whole-wild-width-v1'")==(parent/'catalog.py').read_text()
    def funcs(p):
        return {node.name:ast.dump(node) for node in ast.parse(p.read_bytes()).body if isinstance(node,ast.FunctionDef)}
    b,c=funcs(parent/'runner.py'),funcs(HERE/'runner.py')
    assert set(b)==set(c)
    affected={n for n in b if b[n]!=c[n]}
    assert affected=={'qualified_native','admission','main'}
    return dict(parent_wall_ref='390db41469e8784dca0268c6317ea4b58b2e51c2',parent_manifest=sha(manifest),
                exact_parent_files=len(records)-len(changes),routing_or_provenance_files=sorted(changes),
                unmodified_worker_functions=sorted(set(b)-affected),same_catalog_implementation_except_physical_paths=True,
                original_plan_sha256=records['plan.json'],original_statistic_sha256=records['analysis.py'],
                original_offline_reader_sha256=records['verify_result.py'])
if __name__=='__main__':print(json.dumps(check(Path(sys.argv[1])),indent=2,sort_keys=True))
