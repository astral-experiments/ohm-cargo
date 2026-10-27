"""Hold the full Ruff run until both independent miniature histories and focused regressions pass."""
from pathlib import Path
import hashlib,json,os,subprocess,sys
P=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027');J=P/'mixed-registry-only-pilot';F=P/'frozen-toolchain'
X=Path.home()/'.cache/ohm-233-position-qualified-20261027';S=X/'mixed-registry-seed-programs-20261027'
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def dump(p,x):p.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n')
def load(p):return json.loads(p.read_bytes())
image=Path(sys.argv[1]);label=sys.argv[2];expected=sys.argv[3];assert sha(image)==expected
out=J/('parsed-source-functional-'+label);out.mkdir(mode=0o700)
def go(name,argv):
    d=out/name;d.mkdir();dump(d/'argv.json',list(map(str,argv)))
    with (d/'stdout').open('wb') as f,(d/'stderr').open('wb') as g:
        q=subprocess.run(['taskset','-c','0-3','python3','-B',*map(str,argv)],stdout=f,stderr=g)
    dump(d/'status.json',dict(returncode=q.returncode))
    assert not q.returncode,(name,(d/'stderr').read_text()[-1200:])
    print(name,'finished',flush=True)
cargo=Path(load(X/'mixed-native-abc-protocol-h3-v2/runner-binding.json')['arms']['A']['cargo'])
assert sha(cargo)=='0f237cc3b506aa90c1224e6ed80f646566b424b78c8d74f288f6523d17fc8aa1'
checks={}
for n,expected_true in [('minimal-proc-source-hash-v2','8'),('minimal-transient-positions-v2','8:#0 bytes(373864..373874)')]:
    q=J/f'fixed-{label}-{n}'
    go(n,[S/(n+'.py'),'--out',q,'--rustup',P/'rustup','--sysroot',F,'--cargo',cargo,'--driver',image])
    rows=load(q/'evidence/results.json')
    for variant,v in rows.items():
        a,b=v['builds']['warm'],v['builds']['empty']
        assert a['header']==b['header'] and a['rmeta_sha256']==b['rmeta_sha256'] and a['proc_macro_sha256']==b['proc_macro_sha256']
        vals={r['runtime'] for r in v['readers'].values()};assert len(v['readers'])==4 and len(vals)==1 and all(r['compiler_status']==0 for r in v['readers'].values())
        if variant=='parse':assert vals=={expected_true},(n,variant,vals)
    checks[n]=sha(q/'evidence/results.json')
tests=['incremental-proc-macro-source-tracked-final','incremental-proc-macro-source-span-final','incremental-attribute-proc-macro-cache','rdr-public-hash-proc-macro-foreign-bytes']
go('run-make',[S/'run-source-replay-rmake.py',label,image,expected,*tests])
test=J/('parse-source-runmake-'+label)/'results.json';results=load(test)
assert sorted(results)==sorted(tests) and all(r['returncode']==0 and r['driver_sha256']==expected for r in results.values()),results
checks['run-make']=sha(test)
for script,folder in [('verify-macro-real-paths','macro-real-path-control-'),('check-parse-cache-upgrade','parse-cache-upgrade-')]:
    go(script,[S/(script+'.py'),image,label]);assert (J/(folder+label)/'complete.json').is_file()
    checks[script]=sha(J/(folder+label)/'results.json')
dump(out/'complete.json',dict(driver_sha256=expected,cargo_sha256=sha(cargo),frontend_sha256=sha(F/'bin/rustc'),checks=checks,timings=0))
