"""Profile the actual dirty rustc for a native Ruff edit on the release candidate."""
import gzip
import json
import shutil
import re
import traceback
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import native_helpers as h


def observe():
    assert h.arm in ('P','Q') and h.mode == 'build'
    assert h.label.startswith(('pair-', 'admission-'))
    h.save('storage.json',h.storage())
    candidate = json.loads((h.D / 'source-product.json').read_bytes())
    assert candidate['driver']==h.digest(next((h.sdk/'lib').glob('librustc_driver*.so')))
    assert candidate['commit'] == {'P':'ad005f99d0b51fd62b5c237bc13b31b371a1686e','Q':'2813724f18d9228075f6086d4f050a147f6e761e'}[h.arm]
    assert h.digest(h.sdk/'bin/cargo') == h.cargo_sha
    assert h.git('rev-parse','HEAD').decode().strip() == h.ruff
    assert not h.git('diff', 'HEAD', '--', 'Cargo.toml', 'Cargo.lock', '.cargo', 'crates')
    h.save('provenance.json', dict(commit=candidate['commit'], cargo=h.cargo_sha, driver=h.digest(next((h.sdk/'lib').glob('librustc_driver*.so'))), stock_wild=h.digest(h.stock), affinity=sorted(h.os.sched_getaffinity(0))))
    version = h.source/h.version_rel
    old = h.git('show', h.edit+'^:'+h.version_rel)
    new = h.git('show', h.edit+':'+h.version_rel)
    assert new == version.read_bytes() == (h.donor/h.version_rel).read_bytes() and new != old
    assert h.label.count('-forward-')+h.label.count('-reverse-')==1
    start_state,final_state=('old','new') if '-forward-' in h.label else ('new','old')
    initial,changed=(old,new) if start_state=='old' else (new,old)
    assert all(not any(x.iterdir()) for x in (h.M/'products',h.M/'shared'))
    rows = {}
    is_admission = h.label.startswith('admission-')
    for name in (('native',) if is_admission else ('native','profile')):
        version.write_bytes(initial)
        cold=h.cargo(name+'-initial','build',start_state)
        assert h.root in cold['record']['checked']
        old_value=h.verdict(name+'-initial',cold,start_state)
        warm=h.cargo(name+'-warm','build',start_state)
        assert not warm['record']['rustc'] and not warm['record']['dirty'] and warm['record']['wild']==0
        version.write_bytes(changed)
        if name=='native':
            edited=h.cargo(name+'-edit','build',final_state)
            selected, = [row for row in edited['commands'] if row['crate'] == h.root]
            native_argv=selected['argv']
            assert sorted(h.os.sched_getaffinity(0)) == [int(c) for c in h.os.environ["OHM_REPLAY_CPUSET"].split(",")]
            assert "-Zohm-check-relink-inputs" in native_argv and not any("/v2-" in v for v in native_argv)
            assert Path(native_argv[native_argv.index("--out-dir")+1])==h.M/"shared"/"debug"/"deps"
            assert all(Path(v.split("=",1)[1]).is_file() for i,v in enumerate(native_argv)
                       if i and native_argv[i-1] in ("--extern","--extern-rmeta") and "=" in v)
            h.save("actual-dirty-argv.json",native_argv)
            if not is_admission:
                admitted=json.loads((h.O.parent/"native-admission.json").read_bytes())
                entry=admitted["directions"]["forward" if start_state=="old" else "reverse"]
                assert native_argv == entry["argv"], "different genuine dirty Rust invocation"
            assert edited['record']['rustc']==edited['record']['checked']==edited['record']['dirty']==[h.root] and edited['record']['wild']==0
        else:
            p=h.M/'profiles'
            p.mkdir(mode=0o700)
            args=['cargo','+ohm','build','--locked','--offline','-p',h.root,'-j','4','--message-format=json']
            tracer = h.D / 'trace'
            assert h.digest(tracer) == h.os.environ['OHM_REPLAY_TRACE_SHA']
            try:
                raw=h.checked([tracer,p,h.sdk/'bin/rustc',h.stock,h.root,'--',*args], 'profile-edit')
            finally:
                for aux in sorted(p.glob('*')):
                    if not aux.name.startswith('output.') and aux.is_file() and aux.stat().st_size<4*2**20:
                        h.zipfile(aux.name+'.gz',aux.read_bytes())
            stream=[json.loads(line) for line in raw.splitlines() if line.startswith(b'{')]
            extra=[line for line in raw.splitlines() if not line.startswith(b'{')]
            assert extra[:2]==[b'cargo 0',b'links 0'] and len(extra)==3
            match=re.fullmatch(rb'compiler (\d+) ruff_python_ast 1 0',extra[2]);assert match,extra
            pid=match[1].decode()
            fds={int(line.split(' ',1)[0]):line.split(' ',1)[1] for line in (p/('rustc.'+pid+'.fds')).read_text().splitlines()}
            pair=re.search(r'--jobserver-(?:auth|fds)=(\d+),(\d+)',(p/('rustc.'+pid+'.jobserver')).read_text());assert pair
            assert fds[int(pair[1])]==fds[int(pair[2])] and fds[int(pair[1])].startswith('pipe:[')
            traced=(p/('rustc.'+pid+'.argv')).read_bytes().split(b'\0');assert traced[-1]==b''
            assert [w.decode() for w in traced[:-1]]==native_argv
            assert stream[-1]=={'reason':'build-finished','success':True}
            artifacts=[row for row in stream if row['reason']=='compiler-artifact']
            assert [a['target']['name'] for a in artifacts if not a['fresh']]==[h.root]
            dirty,=[a for a in artifacts if a['target']['name']==h.root]
            edited={'pkg':dirty,'all':[Path(f) for a in artifacts for f in a['filenames']],'commands':[]}
            qualified=p/('output.'+pid+'.'+pid)
            with qualified.open('rb') as raw_profile, gzip.open(h.O/'full-rustc.callgrind.gz','xb',compresslevel=4) as retained:
                shutil.copyfileobj(raw_profile,retained)
            profiles=[]
            for profile in sorted(p.glob('output.*')):
                with profile.open('rb') as f:
                    header=f.read(14000).splitlines()
                cmd=next((line[5:] for line in header if line.startswith(b'cmd: ')),b'')
                if not cmd:continue
                has_unit=b' --crate-name ' in cmd
                if has_unit:
                    assert b' --crate-name ruff_python_ast ' in cmd and b'-Zohm-check-relink-inputs' in cmd
                    assert cmd.strip().split(b' ',1)[0].decode()==native_argv[0]
                    assert Path(native_argv[0]).samefile(h.sdk/'bin/rustc')
                    assert b'events: Ir' in header
                    assert profile.name=='output.'+pid+'.'+pid
                profiles.append(dict(id=profile.name,cmd=cmd.decode(),has_unit=has_unit,bytes=profile.stat().st_size))
            assert sum(r['has_unit'] for r in profiles)==1
            h.save('profile-roster.json',profiles)

        new_value=h.verdict(name+'-changed',edited,final_state)
        warmed=h.cargo(name+'-edited-unchanged','build',final_state)
        assert not warmed['record']['rustc'] and not warmed['record']['dirty'] and warmed['record']['wild']==0
        rows[name]=(old_value,new_value)
        if name=='native':
            for dest in (h.M/'products', h.M/'shared'):
                assert dest.parent==h.M
                dest.rename(dest.with_name('native-'+dest.name))
                dest.mkdir()
    assert rows['native'][0] != rows['native'][1]
    if not is_admission:
        assert rows['native'] == rows['profile']
    for dest in (h.M/'products',h.M/'shared'):
        dest.rename(dest.with_name('profile-'+dest.name));dest.mkdir()
    independent=h.cargo('independent-changed','build',final_state)
    assert h.root in independent['record']['checked']
    clean=h.verdict('independent-changed',independent,final_state)
    assert clean==rows['native'][1]
    h.save('terminal.json',dict(matched=True,consumer=rows,clean=clean,start_state=start_state,final_state=final_state))
try:
    observe()
except BaseException:
    h.save('failure.json',dict(error=traceback.format_exc()))
    raise
