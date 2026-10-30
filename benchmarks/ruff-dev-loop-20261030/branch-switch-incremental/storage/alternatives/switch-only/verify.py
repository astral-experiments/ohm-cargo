"""Recompute the switch-only measurements with the same verifier as the compact comparison."""
from pathlib import Path
import gzip,hashlib,importlib.util,json


def verify(root, shared):
    spec=importlib.util.spec_from_file_location('compact_result',shared);checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)
    compiler=checker.load(root/'compiler.json');evidence=checker.load(root/'source/source.json')
    assert compiler['source']==evidence['child'] and compiler['parent']==evidence['parent']
    assert compiler['tree']==evidence['tree'] and len(compiler['native_files'])==55
    assert compiler['run_make']=={'ohm-branch-cache-opt-out':7,'ohm-packed-branch-cache':10,'ohm-relink-assembler-inputs':12}
    assert len(compiler['unit_tests'])==8 and any(t.endswith('::pack_only_on_checkout_switch') for t in compiler['unit_tests'])
    for line in (root/'source/SHA256SUMS').read_text().splitlines():
        digest,member=line.split('  ');assert '/' not in member
        assert hashlib.sha256((root/'source'/member).read_bytes()).hexdigest()==digest
    assert evidence['originals']['before.json']['status']==101 and evidence['originals']['after.json']['status']==0
    samples=sorted(root.glob('sample-*.json.gz'));assert samples
    for sample in samples:
        label=sample.name.removeprefix('sample-').removesuffix('.json.gz')
        block=gzip.decompress(sample.read_bytes());observed=json.loads(block);raw=checker.load(root/f'native-{label}.json.gz')
        assert hashlib.sha256(block).hexdigest()==raw['verified_sha256']
        assert observed['recipe']['commit']==compiler['source'] and observed['driver_sha256']==compiler['native_files'][compiler['driver']]
        assert observed['filesystem']==('tmpfs' if observed['recipe']['pairs']==12 else 'ext4')
        summary=checker.check(observed,raw);assert summary==checker.load(root/f'summary-{label}.json')
        print(label,[(p,round(summary[p]['paired_median'],3),round(summary[p]['max_storage_ratio'],4)) for p in checker.TARGETS])


if __name__=='__main__':
    root=Path(__file__).resolve().parent
    verify(root,root.parent/'native-compact/verify.py')
