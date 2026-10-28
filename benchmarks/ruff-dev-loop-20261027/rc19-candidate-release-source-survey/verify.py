"""Validate the one-to-one coverage and compare all released scheduler and stream implementations."""
import json
from pathlib import Path
here=Path(__file__).resolve().parent
p=json.loads((here/'ohm-release-source-coverage.json').read_bytes());t=json.loads((here/'ohm-release-tag-coverage.json').read_bytes())
assert len(t)==len(p['pins'])==55 and len(set(p['pins'].values()))==len(p['layout'])==44
assert all(not v['draft'] and v['published_at'] and v['url'].startswith('https://github.com/astral-sh/ohm/releases/tag/') for v in t.values())
assert {v['manifest'] for v in t.values()}==set(p['pins']) and len(set(p['pins_outside_live_branches_and_prs']))==28
assert set(p['pins_outside_live_branches_and_prs'])<=set(p['layout'])
seen=set();generated=0
for ref,commit in p['pins'].items():
    files=p['layout'][commit];jobs=[blob for path,blob in files.items() if 'job_queue' in path];dep=[blob for path,blob in files.items() if 'dependency_queue' in path];inputs=[blob for path,blob in files.items() if path.endswith('fingerprint/worktree.rs')]
    assert len(jobs)==len(dep)==1 and len(inputs)<=1
    v=p['blobs'][jobs[0]];assert v=={'purpose':'scheduler','previous_size':False,'weight':'self.queue.queue(unit.clone(),job,queue_deps,100);'}
    assert p['blobs'][dep[0]]=={'purpose':'dependency_queue','reads_files':False}
    for i in inputs:assert p['blobs'][i]=={'purpose':'generated_file','body_sha256':'3010dd32b254f6146bff06d4a8c8795594086194b53fc73825aa4972e8fa4f26','align_hasher':False}
    generated+=len(inputs);seen.update(files.values())
assert generated==29 and seen==set(p['blobs']) and len(seen)==15
print('Verified all 55 Ohm releases and 44 Cargo pins. Both proposed optimizations are absent in the audited implementations.')
