"""Check downstream effects of private impl edits with ordinary Ohm Cargo."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('state',type=Path,help='new directory for the small generated checkouts and targets')
parser.add_argument('results',type=Path)
a=parser.parse_args()
state=a.state.resolve();state.mkdir(mode=0o700)
recipe=json.loads((Path(__file__).parent/'cases.json').read_text())
env=dict(os.environ,CARGO_TERM_COLOR='never',CARGO_BUILD_JOBS='2')
for key in ['RUSTFLAGS','CARGO_ENCODED_RUSTFLAGS','RUSTC_WRAPPER']:env.pop(key,None)
out={}
for name,case in recipe['cases'].items():
    repo=state/name/'source'; repo.mkdir(parents=True)
    (repo/'Cargo.toml').write_text('[workspace]\nmembers=["contract","api","consumer"]\nresolver="3"\n')
    for pkg,deps in [('contract',[]),('api',['contract']),('consumer',['api','contract'])]:
        crate=repo/pkg
        (crate/'src').mkdir(parents=True)
        (crate/'Cargo.toml').write_text(f'[package]\nname="{pkg}"\nversion="0.0.1"\nedition="2024"\n[dependencies]\n'+
            ''.join(f'{d}={{path="../{d}"}}\n' for d in deps))
    (repo/'contract/src/lib.rs').write_text(recipe['contract'])
    (repo/'consumer/src/lib.rs').write_text(case['consumer'])
    phases={}
    for phase in ['before','after','clean_after']:
        build=state/name/('cold' if phase=='clean_after' else 'warm')
        run_env=dict(env,CARGO_TARGET_DIR=str(build/'target'),CARGO_BUILD_BUILD_DIR=str(build/'shared'))
        (repo/'api/src/lib.rs').write_text(case['producer_before' if phase=='before' else 'producer_after'])
        proc=subprocess.run(['cargo','+ohm','check','--offline','-p','consumer','--message-format=json'],
                            cwd=repo,env=run_env,capture_output=True,text=True)
        assert proc.returncode in (0,101),(name,phase,proc.stderr)
        records=list(map(json.loads,proc.stdout.splitlines()))
        api,=[Path(f) for j in records if j['reason']=='compiler-artifact' and j['target']['name']=='api'
              for f in j['filenames'] if f.endswith('.rmeta')]
        digest=subprocess.check_output(['rustc','+ohm','-Zls=public_hash',str(api)],env=run_env,text=True).strip()
        assert digest.startswith('Public hash: ')
        errors=[j['message'] for j in records if j['reason']=='compiler-message' and j['message']['level']=='error']
        serialized=json.dumps(errors,sort_keys=True,ensure_ascii=False).encode()
        phases[phase]=dict(passes=proc.returncode==0,public_hash=digest,errors=[m['code']['code'] if m['code'] else None for m in errors],
                           diagnostic_bytes=len(serialized),diagnostic_sha256=hashlib.sha256(serialized).hexdigest())
        assert phases[phase]['passes']==case['passes_before' if phase=='before' else 'passes_after'],(name,phase,proc.stderr)
    assert (phases['before']['public_hash']!=phases['after']['public_hash'])==case['changes_public_hash'],name
    assert phases['after']==phases['clean_after'],name
    out[name]=phases
    a.results.write_text(json.dumps(out,indent=2)+'\n')
    print(name,phases['before']['passes'],phases['after']['passes'],phases['after']['errors'],flush=True)
