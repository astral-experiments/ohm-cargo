"""Exercise the production coordinator through both full phases without running Cargo or rustc."""
import argparse
import ast
from collections import Counter
import csv
import hashlib
import inspect
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace

H = Path(__file__).resolve().parent
PLAN = json.loads((H/'plan.json').read_text())
WASM = ('ruff_wasm','ty_wasm')

def need(cond, msg):
    if not cond: raise ValueError(msg)

def dump(p,v):p.write_text(json.dumps(v)+'\n')
def load(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def check_static_calls(root):
    parsed={p.stem:ast.parse(p.read_bytes()) for p in root.glob('*.py') if not p.name.startswith('test_')}
    sigs={}
    for name,module in parsed.items():
        for fn in module.body:
            if not isinstance(fn,ast.FunctionDef):continue
            a=fn.args
            if a.vararg or a.kwarg or a.posonlyargs or a.kwonlyargs:continue
            params=[inspect.Parameter(v.arg,inspect.Parameter.POSITIONAL_OR_KEYWORD,default=inspect.Parameter.empty if i<len(a.args)-len(a.defaults) else None) for i,v in enumerate(a.args)]
            sigs[(name,fn.name)]=inspect.Signature(params)
    checked=0
    for name,module in parsed.items():
        imports={a.asname or a.name:(n.module,a.name) for n in ast.walk(module) if isinstance(n,ast.ImportFrom) for a in n.names}
        for call in ast.walk(module):
            if not isinstance(call,ast.Call) or not isinstance(call.func,ast.Name) or any(isinstance(v,ast.Starred) for v in call.args) or any(v.arg is None for v in call.keywords):continue
            sig=sigs.get((name,call.func.id),sigs.get(imports.get(call.func.id)))
            if sig is None:continue
            try:sig.bind(*[None]*len(call.args),**{v.arg:None for v in call.keywords})
            except TypeError as exc:raise AssertionError(f'{name}:{call.lineno} {call.func.id}{sig} {exc}') from exc
            checked+=1
    return checked

def rehearse(runner):
    functions=[f for f in ast.parse(runner.read_bytes(),filename=str(runner)).body if isinstance(f,ast.FunctionDef)]
    # Execute the coordinator's real call, training, cloning, bridges, comparisons and CSV loop.
    # Substitute only its process-launch, private offline-source seed and host-specific checks.
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);target=root/'canonical-target';shared=root/'canonical-shared';out=root/'private-run';out.mkdir(); fixture=out/'fixture';fixture.mkdir();(out/'bridge-canonical').mkdir();record=[];bridge_calls=[];seeded=[]
        env=dict(globals(), H=H, PLAN=PLAN, TARGET=target, SHARED=shared, CARGO_HOME=root/'cargo-home', out=out, fixture=fixture, binding=root/'binding.json')
        exec(compile(ast.fix_missing_locations(ast.Module(body=functions,type_ignores=[])),str(runner),'exec'),env)
        def seed(st,fixture,source_home):
            assert not st.exists();st.mkdir(parents=True);seeded.append((st.parent.name,st.name))
            for n in ('target','shared','inputs','rustup','registry-home'):(st/n).mkdir()
            return st
        def command(st,arm,extra=()):return ['mock-host',str(st),arm,*map(str,extra),'--']
        def launch(cmd):
            st=Path(cmd[1]);arm=cmd[2];arg=lambda n:cmd[cmd.index('--'+n)+1];after=cmd[cmd.index('--')+1:];script=Path(after[2]).name; d=Path(arg('out'));d.mkdir(); assert arm==arg('arm');
            if script=='bridge_worker.py':
                action=arg('action');bridge_calls.append((st.parent.name,action,arm));
                if action=='bridge':(d.parent/'libordinary_bridge.rlib').write_bytes(b'bridge')
                else:dump(d/'bridge.json',{'runtime':'ok'})
                return
            assert script=='worker.py';mode=arg('mode');phase=arg('phase');edited=arg('state')=='edited';units=PLAN['endpoints'][mode]['expected_units'];rows=units if phase!='cold' else 0;record.append((mode,st.name,arm,phase,d.name,edited))
            traces={'jobs':[]};prod={'dirty':['producer'] if phase in ('cold','conditioning','edit','forced','ordinary','settle') else [],'structural_roster':mode,'messages':mode,'diagnostics':str(edited),'mixed':{cr:{'metadata':cr} for cr in WASM},'marker':(mode,edited)}
            receipt={'arm':arm,'mode':mode,'state':str(edited),'elapsed_ns':100,'processes':traces,'product':prod,'recipe_after':{cr:[cr,100,1] for cr in WASM},'fresh_units':rows,'unit_count':units};dump(d/'receipt.json',receipt)
            # The actual clone path will copy and independently hash every advertised inode.
            if st.name=='C' and d.name=='condition-restore-fresh':
                with (d/'stdout').open('w') as f:
                    for i in range(units):
                        rel=f'f{i}';(st/'target'/rel).write_text(rel);print(json.dumps({'reason':'compiler-artifact','filenames':[str(target/rel)]}),file=f)
        def compare(got,ref):assert list(got['marker'])==list(ref['marker']);return {'checked':True}
        env.update(seed=seed,command=command,checked_launch=launch,set_source=lambda *args:None,gate_free=lambda *args:1000*2**30,compare_context=compare)
        for mode in ('build','test'):
            env['qualify'](mode)
            assert not load(out/f'qualification-{mode}.json')['mismatches']
            assert len(load(out/f'cloned-artifacts-{mode}.json'))==PLAN['endpoints'][mode]['expected_units']
            mode_arms=[arm for m,arm in seeded if m==mode];assert mode_arms==['A','B','C','gold-A','gold-B'] and not (out/'state'/mode/'forced-C'/'target').exists()
            assert Counter(a for m,a,_ in bridge_calls if m==mode)=={'bridge':8,'caller':16}
            assert not (out/f'{mode}.csv').exists()
        for mode in ('build','test'):
            env['score'](mode)
            rows=list(csv.DictReader((out/f'{mode}.csv').open()));assert len(rows)==54
            for seq,pos in zip(rows,[(b,s,a) for b,order in enumerate(PLAN['endpoints'][mode]['orders'],1) for s,a in enumerate(order,1)],strict=True):assert (int(seq['block']),int(seq['slot']),seq['arm'])==pos
        assert sum(ev[3]=='ordinary' for ev in record)==108 and sum(ev[3]=='settle' for ev in record)==108
        print('Mock full coordinator: 6 independently seeded primary targets, both independent cold contexts per mode, both actual inode-independent forced copies, 32 bridge callers and 108 correctly ordered ordinary edits.')

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--runner',type=Path,default=H/'run.py');args=ap.parse_args();rehearse(args.runner);print('Static calls cross-checked:',check_static_calls(args.runner.parent))
