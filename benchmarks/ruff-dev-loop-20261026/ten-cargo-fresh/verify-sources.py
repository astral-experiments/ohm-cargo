"""Reconstruct ten draft heads in temporary Git objects and compare the benchmark source."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('repo', type=Path, help='ohm-cargo checkout containing the ten PR objects')
parser.add_argument('--export-patch', type=Path, help='write the full ten-PR diff, including test sources')
args = parser.parse_args()
base = '461a3d1007ecc997a6d86c7d75e8b518575c8d90'
heads = {
    242: 'f98a9e825516553171c88a85d55bfff7b0f9b748', 243: '184e50b93316db9478f82eae2e35b789ba6ab1e9',
    244: 'e0c8d5d08ce852965ecb7f06e3cff97651892acb', 245: '28c2b64e0936098e900c01d864fb0a026233e917',
    246: 'fc82ecb6f31cea7da5dba628e697fe80ed05acd9', 247: 'f9b4bba66b74fa2be213901ff6ec12c468530b1b',
    248: '37e0a7083fbf535fb8f5a41d4f1bb12303676dd8', 249: 'b5330b2788eb7ded3d0f7de4469110fb8529f014',
    250: '779889050ecdf73104225cd5e6fbd716f7e9b751', 251: '4726184e16306794a8c4d6f25c30a88066f42d25',
}
cmd = ['git', '-C', args.repo]
common = Path(subprocess.check_output(cmd + ['rev-parse', '--path-format=absolute', '--git-common-dir'], text=True).strip())
evidence = Path(__file__).resolve().parent.parent
source = (evidence/'cargo-stack-holdout/nine.patch').read_bytes() + (evidence/'frontend-scheduling/candidate.patch').read_bytes()
with tempfile.TemporaryDirectory() as tmp:
    objects = Path(tmp) / 'objects'
    objects.mkdir()
    env = dict(os.environ, GIT_OBJECT_DIRECTORY=str(objects), GIT_ALTERNATE_OBJECT_DIRECTORIES=str(common/'objects'),
               GIT_INDEX_FILE=str(Path(tmp)/'index'))

    def git(*args, data=None):
        return subprocess.check_output(cmd + list(args), env=env, input=data)

    merged = base
    for head in heads.values():
        merged = git('merge-tree', '--write-tree', '--no-messages', '--merge-base=' + base, merged, head).decode().strip()
    git('read-tree', base)
    git('apply', '--cached', '--whitespace=nowarn', '-', data=source)
    measured = git('write-tree').decode().strip()
    diff = git('diff', '--numstat', measured, merged).decode().splitlines()
    assert diff == ['104\t0\tsrc/sources/path/verified_index.rs', '30\t0\tsrc/workspace/dependency.rs', '36\t0\ttests/testsuite/rustflags.rs']
    marker = b'\n#[cfg(test)]\nmod tests {'
    for path in ('src/sources/path/verified_index.rs', 'src/workspace/dependency.rs'):
        product = git('show', merged + ':' + path)
        benchmark = git('show', measured + ':' + path)
        prefix, tests = product.split(marker)
        assert tests.rstrip().endswith(b'\n}') and all(line.startswith(b' ') for line in tests.splitlines()[1:-1] if line)
        assert benchmark.split(marker)[0].rstrip() == prefix.rstrip()
    merged_patch = git('diff', '--full-index', '--binary', base, merged)
    if args.export_patch:
        args.export_patch.write_bytes(merged_patch)
    print(json.dumps(dict(base=base, draft_heads=heads, full_draft_tree=merged, measured_source_tree=measured,
                          full_patch_sha256=hashlib.sha256(merged_patch).hexdigest(),
                          measured_patch_sha256=hashlib.sha256(source).hexdigest(), omitted_test_lines=diff), indent=2))
