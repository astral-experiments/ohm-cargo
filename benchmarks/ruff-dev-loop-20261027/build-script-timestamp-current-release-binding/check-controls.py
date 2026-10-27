"""Changed build-script environment and out-of-tree input must produce the same real check error warm and empty."""
from pathlib import Path
import hashlib, json, os, subprocess, sys
R=Path(sys.argv[1]);arm=sys.argv[2]
X=Path.home()/'.cache/ohm-233-position-qualified-20261027';P=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027')
SDK=P/'frozen-toolchain';RUP=P/'rustup'
product=X/'build-script-current-cargo-release-v1/packaged-v5'
cargo=product/('cargo-'+arm);official=json.loads((X/'build-script-current-stock-sdk-v1/official.json').read_bytes());actual=Path(official['sdk_root']);driver=actual/'lib'/official['driver_name']
def h(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert h(cargo)==json.loads((product/'pair.json').read_bytes())[arm]
R.mkdir()
for case in ('environment','outside-include'):
    case_dir=R/case;ws=case_dir/'source';(ws/'src').mkdir(parents=True)
    (ws/'outside.txt').write_text('41')
    (ws/'Cargo.toml').write_text('[package]\nname="check_generation"\nversion="0.0.1"\nedition="2024"\n')
    (ws/'build.rs').write_text('fn main(){ println!("cargo::rerun-if-changed=trigger.txt"); let value=std::fs::read_to_string("trigger.txt").unwrap(); '+('println!("cargo::rustc-env=ANSWER={value}");' if case=='environment' else 'std::fs::write("outside.txt",value).unwrap();')+'}\n')
    (ws/'src/lib.rs').write_text(('const ANSWER: &[u8] = env!("ANSWER").as_bytes();' if case=='environment' else 'const ANSWER: &[u8] = include_bytes!("../outside.txt");')+'\nconst _: () = assert!(ANSWER[0] == b\'4\');\n')
    results={};old=None
    for phase,value,store,code in [('prime','41','warm',0),('unchanged-original','41','warm',0),('edit','83','warm',101),('first-unchanged','83','warm',101),('empty-edited','83','independent',101),('restore','41','warm',0),('fresh-restore','41','warm',0)]:
        if value!=old:(ws/'trigger.txt').write_text(value);old=value
        case_out=case_dir/phase;case_out.mkdir();e=dict(os.environ,RUSTUP_HOME=str(RUP),RUSTUP_AUTO_INSTALL='0',RUSTUP_TOOLCHAIN='ohm',CARGO_HOME=str(case_dir/('registry-'+store)),CARGO_TARGET_DIR=str(case_dir/('target-'+store)),CARGO_BUILD_BUILD_DIR=str(case_dir/('shared-'+store)),RUSTC=str(SDK/'bin/rustc'),CARGO_NET_OFFLINE='true')
        for k in ('RUSTC_LOG','RUSTFLAGS','CARGO_ENCODED_RUSTFLAGS','RUSTC_WRAPPER','RUSTC_WORKSPACE_WRAPPER'):e.pop(k,None)
        args=['taskset','-c','26-27','bwrap','--ro-bind','/','/','--proc','/proc','--dev','/dev','--tmpfs','/tmp','--bind',str(case_dir),str(case_dir),'--ro-bind',str(actual),str(SDK),'--ro-bind',str(cargo),str(SDK/'bin/cargo'),'--chdir',str(ws),'--','strace','-qq','-f','-s','8192','-e','trace=execve','-o',str(case_out/'exec.log'),str(Path.home()/'.cargo/bin/cargo'),'+ohm','check','--offline','--message-format=json','-j2']
        p=subprocess.run(args,capture_output=True,env=e,timeout=80)
        (case_out/'cargo.stdout').write_bytes(p.stdout);(case_out/'cargo.stderr').write_bytes(p.stderr)
        assert p.returncode==code,(case,phase,p.returncode,p.stderr[-700:])
        rows=[json.loads(l) for l in p.stdout.splitlines()];ds=[a['message'] for a in rows if a['reason']=='compiler-message' and a['message'].get('code') and a['message']['code']['code']=='E0080']
        assert (len(ds)==1 if code else not ds),(case,phase,ds)
        physical=[l for l in (case_out/'exec.log').read_text().splitlines() if l.endswith('= 0') and '"--crate-name", "check_generation"' in l and 'execve("'+str(SDK/'bin/rustc')+'"' in l]
        if phase=='fresh-restore' and arm=='parent':
            assert len(physical) in (0,1),(case,phase,physical)
        else:assert len(physical)==(0 if phase in ('unchanged-original','fresh-restore') else 1),(case,phase,physical)
        results[phase]={'exit':code,'src_sha256':h(ws/'src/lib.rs'),'build_sha256':h(ws/'build.rs'),'physical_rustc':physical,'diagnostics':ds,'stderr_sha256':h(case_out/'cargo.stderr'),'fresh':[a['fresh'] for a in rows if a['reason']=='compiler-artifact']}
    assert results['edit']['diagnostics']==results['empty-edited']['diagnostics']==results['first-unchanged']['diagnostics']
    (case_dir/'result.json').write_text(json.dumps(results,sort_keys=True,indent=1)+'\n');print('CHECK CONTROL',arm,case,'E0080 edit, repeat, clean; restored',flush=True)
