"""Run unmodified packaged Ohm against Ruff's actual ron graph and a real upstream edit."""
import argparse
import ast
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tomllib


def sha(path):
    return sha256(path.read_bytes()).hexdigest()


def save(path, data):
    path.write_text(json.dumps(data, sort_keys=True, indent=2) + '\n')


def prepare(root, sdk, source, archives):
    root.mkdir()
    vendor = root/'vendor'; vendor.mkdir()
    alias = root/'rustup'/'toolchains'; alias.mkdir(parents=True); (alias/'ohm').symlink_to(sdk.resolve())
    lock = source/'Cargo.lock'
    revision = subprocess.check_output(['git','--no-optional-locks','-C',source,'rev-parse','HEAD'], text=True).strip()
    assert revision == '93526150df078af7dd8fc4226cdcc469539d2001'
    assert (subprocess.check_output(['git','--no-optional-locks','-C',source,'show',revision+':Cargo.lock'])
            == lock.read_bytes())
    pkgs = {(e['name'],e['version']):e for e in tomllib.loads(lock.read_text())['package']}
    pending=[('ron','0.12.0')]; done=set(); receipts={}
    while pending:
        k = pending.pop()
        if k in done: continue
        done.add(k); entry=pkgs[k]
        name,version=k; label=name+'-'+version
        src, = archives.glob('*/'+label+'.crate'); want=entry['checksum']; assert sha(src)==want
        with tarfile.open(src) as t: t.extractall(vendor,filter='data')
        crate=vendor/label
        files={str(p.relative_to(crate)):sha(p) for p in sorted(crate.rglob('*')) if p.is_file()}
        save(crate/'.cargo-checksum.json',{'files':files,'package':want}); receipts[label]=want
        for dep in entry.get('dependencies',[]):
            v=dep.split(); match,=[e for e in pkgs if e[0]==v[0] and (len(v)==1 or v[1]==e[1])]; pending.append(match)
    assert len(done)==11 and receipts['ron-0.12.0']=='fd490c5b18261893f14449cbd28cb9c0b637aebf161cd77900bfdedaff21ec32'
    assert receipts['bitflags-2.13.2']
    for case in ('registry','editable'):
        ws=root/case/'source'; (ws/'src').mkdir(parents=True); (ws/'.cargo').mkdir()
        (ws/'.cargo/config.toml').write_text('[source.crates-io]\nreplace-with="local-registry"\n[source.local-registry]\ndirectory='+json.dumps(str(vendor))+'\n')
        body='[package]\nname="ron_native_probe"\nversion="0.0.0"\nedition="2021"\n[dependencies]\nron="=0.12.0"\n[profile.dev]\nopt-level=1\ndebug="line-tables-only"\n'
        if case=='editable':
            bit=ws/'upstream'; shutil.copytree(vendor/'bitflags-2.13.2',bit)
            body+='[patch.crates-io]\nbitflags={path="upstream"}\n'
        (ws/'Cargo.toml').write_text(body)
        (ws/'src/main.rs').write_text('fn main() { let n = ron::extensions::Extensions::IMPLICIT_SOME.bits(); println!("{}", ron::to_string(&n).unwrap()); }\n')
        shutil.copyfile(lock,ws/'Cargo.lock')
    actual={k:sha(sdk/'bin'/k) for k in ('cargo','rustc')}
    driver,=(sdk/'lib').glob('librustc_driver-*.so');actual['driver']=sha(driver)
    save(root/'data.json',{'registry':receipts,'revision':revision,'images':actual,'sdk':str(sdk)})


def build(root, case, state, phase, expected, locked=True):
    ws=root/case/'source'; state=root/case/state; state.mkdir(exist_ok=True)
    out=root/case/phase; out.mkdir(); env={k:v for k,v in os.environ.items() if not k.startswith(('CARGO','RUST','OHM_'))}
    env.update(CARGO_HOME=str(state/'cargo'),CARGO_TARGET_DIR=str(state/'target'),CARGO_BUILD_BUILD_DIR=str(state/'shared'),
        RUSTUP_HOME=str(root/'rustup'),RUSTUP_AUTO_INSTALL='0',CARGO_NET_OFFLINE='true',CARGO_TERM_COLOR='never',
        PATH=str(Path.home()/'.cargo/bin')+':/usr/local/bin:/usr/bin:/bin')
    args=['cargo','+ohm','build','--offline','-j8','--message-format=json']
    if locked:args.append('--locked')
    with (out/'stdout').open('xb') as so,(out/'stderr').open('xb') as se:
        run=subprocess.run(['strace','-ff','-qq','-e','trace=execve','-s','65535','-o',str(out/'exec')]+args,
            env=env,cwd=ws,stdout=so,stderr=se,timeout=220)
    if run.returncode:raise RuntimeError((case,phase,run.returncode,(out/'stderr').read_text()[-1200:],(out/'stdout').read_text()[-1500:]))
    messages=[json.loads(s) for s in (out/'stdout').read_bytes().splitlines()];assert messages[-1]=={'reason':'build-finished','success':True}
    libs={r['target']['name']:r for r in messages if r.get('reason')=='compiler-artifact' and r['target']['kind'] in (['lib'],['proc-macro'],['bin'])}
    ron=libs['ron']; bit=libs['bitflags']; assert ron['package_id'].startswith('registry+') and ron['features']==['default','std']
    assert (bit['package_id'].startswith('path+'))==(case=='editable')
    elf=Path(libs['ron_native_probe']['executable']); result=subprocess.run([elf],capture_output=True,timeout=10,check=True)
    assert result.stdout==f'{expected}\n'.encode() and not result.stderr
    p,=[p for s in (state/'target',state/'shared') for p in s.rglob('ron-*.d') if p.parent.name=='out']
    fp=p.parent.parent/'fingerprint'/'dep-lib-ron'; enc=fp.read_bytes(); raw=p.read_bytes()
    assert b'ohm-foreign-span-bytes' in raw and enc[-41:-37]==b'OBS1' and enc[-33]==0
    counts={'full':[],'link_only':[],'wild':[]}; trace={}; matched=[]
    for path in sorted(out.glob('exec.*')):
        trace[path.name]=sha(path)
        for line in path.read_bytes().splitlines():
            m=re.fullmatch(rb'execve\(("(?:\\.|[^"\\])*"),\s*(\[.*\]), (?:0x[\da-f]+|NULL).*?\)\s+= 0',line)
            if not m:continue
            exe=Path(ast.literal_eval(m[1].decode())); argv=ast.literal_eval(m[2].decode()); h=sha256(m[2]).hexdigest()
            if exe.name=='rustc' and '--crate-name' in argv:
                name=argv[argv.index('--crate-name')+1]
                if name=='___':continue
                role='link_only' if '-Zlink-only' in argv else 'full';counts[role].append(name)
                if name=='ron':matched.append(h)
            if exe.name=='ld.bfd' and exe.parent.name=='wild-ld':counts['wild'].append(h)
    row={'argv':args,'full':sorted(counts['full']),'link_only':sorted(counts['link_only']),'wild_count':len(counts['wild']),
         'ron_argv':matched,'complete_trace_digests':trace,'ron_fresh':ron['fresh'],'bitflags_fresh':bit['fresh'],
         'ron_registry_features':ron['features'],'ron_rust_depinfo_sha256':sha(p),'encoded_sha256':sha(fp),'incomplete_obs1':True,
         'program_sha256':sha(elf),'program_decodes':expected,'rust_diagnostics':[s['message']['level'] for s in messages if s.get('reason')=='compiler-message'],
         'ron_artifacts':{Path(a).suffix:sha(Path(a)) for a in ron['filenames']},'lock_sha256':sha(ws/'Cargo.lock')}
    assert not ron['fresh'] and matched
    save(out/'row.json',row);print(case,phase,expected,row['full'],row['link_only'],row['wild_count'],flush=True);return row


if __name__=='__main__':
    cli=argparse.ArgumentParser();cli.add_argument('--root',required=True,type=Path);cli.add_argument('--sdk',required=True,type=Path);cli.add_argument('--ruff',required=True,type=Path);cli.add_argument('--archives',required=True,type=Path);a=cli.parse_args()
    prepare(a.root,a.sdk,a.ruff,a.archives);rows={}
    for case in ('registry','editable'):
        rows[case]={}
        for phase in ('cold','unchanged-1','unchanged-2'):
            rows[case][phase]=build(a.root,case,'warm',phase,2,locked=phase!='cold')
        if case=='editable':
            path=a.root/case/'source/upstream/src/public.rs';before=path.read_bytes();from_=b'fn bits(&self) {\n                    self.0.bits()\n';to=from_.replace(b'self.0.bits()',b'self.0.bits() ^ 1')
            assert before.count(from_)==1; path.write_bytes(before.replace(from_,to))
            rows[case]['edited']=build(a.root,case,'warm','edited',3)
            rows[case]['edited-repeat']=build(a.root,case,'warm','edited-repeat',3)
            rows[case]['cold-edited']=build(a.root,case,'independent','cold-edited',3)
            assert 'bitflags' in rows[case]['edited']['full'];assert 'bitflags' not in rows[case]['edited-repeat']['full']
            path.write_bytes(before);rows[case]['restored']=build(a.root,case,'warm','restored',2)
            assert 'bitflags' in rows[case]['restored']['full'];assert before==path.read_bytes()
    save(a.root/'complete.json',rows)
