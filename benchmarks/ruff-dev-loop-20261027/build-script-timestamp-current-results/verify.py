"""Recompute every paired effect and exact test from the registered raw clock readings."""
from pathlib import Path
import hashlib, importlib.util, json, tarfile, tempfile
here=Path(__file__).resolve().parent
read=lambda p:json.loads(p.read_bytes())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(here/'raw.tar.gz')=='11cc0a3c3f0a09a5b02098699344761694772f0c0d2edad49600feea7ca7d84a'
assert sha(here/'analyze.py')==read(here/'release-score.json')['analysis']
with tempfile.TemporaryDirectory() as wd:
    d=Path(wd)
    with tarfile.open(here/'raw.tar.gz') as t:t.extractall(d,filter='data')
    o=read(here/'order.json');audit=read(here/'audit.json')
    spec=importlib.util.spec_from_file_location('frozen_analyzer',here/'analyze.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    assert m.analyze(o,d/'score')==read(here/'analysis.json')
    n=0
    for r in o:
        for arm in r['arm_order']:
            base=d/'score'/f"{r['order']:02d}"/arm
            assert read(base/'preflight/receipt.json')['fresh']==520
            times=[]
            for name in ('change','change-next','change-next-2'):
                e=read(base/name/'elapsed.json')
                assert e['ns']==e['finish_monotonic_ns']-e['start_monotonic_ns']>0
                times.append(e['ns']);n+=1
            assert times==read(base/'change-family.json')['ns']
    assert n==audit['elapsed_rows_without_trace']==144
    print('Verified 144 clocks, 48 initial 520-fresh checks, and 3 primary endpoints.')
