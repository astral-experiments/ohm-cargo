"""Repeat the synchronized DSO and metadata cases with full identities on every compiled unit."""
from pathlib import Path
import hashlib, json, os, subprocess, sys, traceback

OPS = Path(__file__).resolve().parent
ROOT = Path('/dev/shm/ohm-ron-consumed-v1-20261028')
SDK = Path('/dev/shm/ohm-published-member-h2-20261028/installed17')
CARGO = Path('/mnt/devbox-scratch/dev-user/ohm-observer-consumption-tools-20261028/fixed-cargo')
def sha(path):
    with path.open('rb') as f: return hashlib.file_digest(f, 'sha256').hexdigest()
def save(path, value):
    path.write_text(json.dumps(value, sort_keys=True, indent=2)+'\n')
def child():
    assert sha(SDK/'bin/cargo') == '0aa04df8023984b83ef676d1494d43e482472e1b2bccdb82a4d0bd390578a322'
    assert sha(next((SDK/'lib').glob('librustc_driver-*.so'))) == '618ebac16b7d4ec01a2af89661d25b8f26ff347edbb69c6dcaa78f10115914a7'
    data={}
    for kind, script in [('dso','native-dso.py'),('rmeta','column-rmeta.py')]:
        source=(OPS/script).read_text()
        needle="env['CARGO_ENCODED_RUSTFLAGS']='--extern\\x1frace_extern='+str(live)"
        assert source.count(needle)==1
        source=source.replace(needle, needle+"+'\\x1f-Zpublic-api-hash=no'")
        ns={'__file__':str(OPS/script),'__name__':'under_test'}
        exec(compile(source, str(OPS/script), 'exec'),ns)
        sub=ROOT/('full-identity-'+kind)
        data[kind]=ns['case'](sub,SDK,kind,'preserved')
        captured={}
        for p in (sub/'initial').glob('exec.*'):
            for line in p.read_text().splitlines():
                if not line.endswith(' = 0') or '"--crate-name",' not in line: continue
                import re
                m=re.search(r'"--crate-name", "([^"]+)"',line)
                if m and m[1] != '___':
                    matches=re.findall(r'"(-Zpublic-api-hash(?:=no|=yes)?)"',line)
                    assert matches and matches[-1]=='-Zpublic-api-hash=no',(m[1],matches)
                    captured[m[1]]=matches
        assert 'hold_direct' in captured
        fpfiles=list((sub/'warm').rglob('dep-bin-hold_direct'))
        rustfiles=list((sub/'warm').rglob('hold_direct*.d'))
        save(sub/'identities.json',{'argv':captured,'record_has_OBS1':[b'OBS1' in p.read_bytes() for p in fpfiles],
            'marked_depfiles':[str(p.name) for p in rustfiles if b'ohm-foreign-span-bytes' in p.read_bytes()]})
        print(kind, data[kind], flush=True)
        save(ROOT/'full-identity.json',data)
if __name__=='__main__':
    ROOT.mkdir(exist_ok=True)
    if '--child' in sys.argv: child()
    else:
        cmd=['bwrap','--die-with-parent','--ro-bind','/','/','--dev','/dev','--proc','/proc','--ro-bind','/dev/shm','/dev/shm',
             '--tmpfs','/tmp','--bind',str(ROOT),str(ROOT),'--ro-bind',str(CARGO),str(SDK/'bin/cargo'),
             '--','taskset','-c','8-11',sys.executable,'-B',__file__,'--child']
        result=subprocess.run(cmd);sys.exit(result.returncode)

