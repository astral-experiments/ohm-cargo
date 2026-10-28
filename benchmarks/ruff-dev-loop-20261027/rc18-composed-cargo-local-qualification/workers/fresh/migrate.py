"""Migrate six independently retained, falsely fresh released -17 Cargo targets."""
from pathlib import Path
import hashlib, json, os, re, shutil, subprocess, sys
H=Path('/home/dev-user/.cache/ohm-rc18-retained-includes-current-epoch-20261028')
DATA=Path('/home/dev-user/.cache/ohm-rc18-current-epoch-20261028')
SDK=Path('/dev/shm/ohm-published-member-h2-20261028/installed17')
X=Path('/dev/shm/ohm-ron-consumed-v1-20261028')
IMAGE=X/'target-rc18-composed/debug/cargo';NEW='1c328d9c2e078019989b2c677acd666820caa093f4993ca8c606d141cf8574e4';OLD='4e4065390403afbf4fb77b2f41fbc21c59afe3dda2337a5bbe29fda29a47dbb3'
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
read=lambda p:json.loads(p.read_bytes())
def save(p,x):p.write_text(json.dumps(x,sort_keys=True,indent=2)+'\n')
def program(p):
    raw=subprocess.check_output([p],timeout=15);assert b'revision=2' in raw.splitlines()
    return int(re.search(rb'(?m)^sample=(\d+)$',raw)[1]),raw
def inner(case,phase,rec):
    expected=OLD if phase=='before' else NEW;assert sha(SDK/'bin/cargo')==expected
    rows=read(case/'report.json') if (case/'report.json').exists() else read(rec.parent/'original.json')
    previous=rows['rows']['again']
    e=dict(HOME=str(case),PATH=os.environ['PATH'],RUSTUP_HOME=str(case/'rustup'),RUSTUP_AUTO_INSTALL='0',CARGO_HOME=str(case/'cargo'),CARGO_NET_OFFLINE='true',CARGO_BUILD_JOBS='4',OHM_SYNC_DIR=str(case),OHM_SYNC_CONSTANT='fixed',LC_ALL='C.UTF-8',LANG='C.UTF-8',CARGO_TARGET_DIR=str(case/'warm/target'),CARGO_BUILD_BUILD_DIR=str(case/'warm/shared'))
    with (rec/'cargo.jsonl').open('xb') as so,(rec/'stderr').open('xb') as er:
        q=subprocess.run(['strace','-f','-qq','-s','65535','-e','trace=execve','-o',str(rec/'exec'),'cargo','+ohm','build','--offline','-p','hold_direct','--message-format=json'],cwd=case/'src',env=e,stdout=so,stderr=er,timeout=100)
    assert q.returncode==0,(rec,(rec/'stderr').read_text()[-1000:])
    events=[json.loads(l) for l in (rec/'cargo.jsonl').read_bytes().splitlines()];assert events[-1]=={'reason':'build-finished','success':True}
    arts={a['target']['name']:a for a in events if a['reason']=='compiler-artifact'};caller=arts['hold_direct'];elf=Path(caller['executable']);value,raw=program(elf);(rec/'program').write_bytes(raw)
    comp=[]
    for l in (rec/'exec').read_text().splitlines():
        if 'execve(' not in l or not l.rstrip().endswith('= 0') or '"--crate-name",' not in l:continue
        m=re.search(r'execve\("([^"]+)"',l);n=re.search(r'"--crate-name", "([^"]+)"',l);d=re.search(r'"--out-dir", "([^"]+)"',l)
        if m and n and d and n[1]!='___' and Path(m[1]).is_file() and Path(m[1]).samefile(SDK/'bin/rustc'):
            comp.append({'unit':n[1],'out':d[1],'argv_sha256':hashlib.sha256(l.encode()).hexdigest()})
    if phase=='before':
        assert caller['fresh'] and not comp and value==17 and sha(elf)==previous['exe']
        fp,=[p for p in (case/'warm').rglob('dep-bin-hold_direct') if sha(p)==previous['fingerprint']]
    else:
        c,=[v for v in comp if v['unit']=='hold_direct'];assert not caller['fresh'] and value==29
        out=Path(c['out']);fp=out.parent/'fingerprint/dep-bin-hold_direct';di=out/'hold_direct.d';assert b'ohm-foreign-span-bytes' in di.read_bytes();(rec/'rustc.d').write_bytes(di.read_bytes())
    b=fp.read_bytes();assert b[-41:-37]==b'OBS1' and bool(b[-33])==(phase=='before');(rec/'encoded.bin').write_bytes(b)
    item={'cargo':expected,'value':value,'fresh':{n:a['fresh'] for n,a in arts.items()},'full_compilers':comp,'active_fp_sha256':sha(fp),'active_fp':str(fp),'complete':bool(b[-33]),'elf_sha256':sha(elf),'cargo_rc':q.returncode};save(rec/'row.json',item)
if len(sys.argv)>1 and sys.argv[1]=='inner':
    args=sys.argv[2:];inner(Path(args[0]),args[1],Path(args[2]));sys.exit()
assert sha(IMAGE)==NEW and sha(SDK/'bin/cargo')==OLD and shutil.disk_usage(H.parent).free>15*2**30;H.mkdir(mode=0o700)
allrows={}
for case in sorted(DATA.glob('trained-*')):
    baseline=read(case/'report.json');assert baseline['rows']['again']['value']==17 and baseline['rows']['again']['initially_complete'] and baseline['rows']['clean']['value']==29
    rec=H/case.name;rec.mkdir();save(rec/'original.json',baseline);log=read(case/'report.json');art,=[v for l in (case/'again/cargo.jsonl').read_bytes().splitlines() if (v:=json.loads(l)).get('target',{}).get('name')=='hold_direct'];original=Path(art['executable']);old_sha=sha(original);assert program(original)[0]==17 and old_sha==baseline['rows']['again']['exe']
    clone=rec/'state';clone.mkdir()
    for n in ('src','rustup','cargo','warm','private-input.txt','observed','release'):subprocess.run(['cp','-a','--reflink=auto',str(case/n),str(clone/n)],check=True)
    assert (clone/'warm').stat().st_ino!=(case/'warm').stat().st_ino and sha(case/'private-input.txt')==sha(clone/'private-input.txt')
    rows={}
    for phase in ('before','first','second','empty'):
        out=rec/phase;out.mkdir()
        cmd=['bwrap','--die-with-parent','--ro-bind','/','/','--dev','/dev','--proc','/proc','--ro-bind','/dev/shm','/dev/shm','--tmpfs','/tmp','--bind',str(rec),str(rec),'--bind',str(clone),str(case)]
        if phase=='empty':
            fresh=rec/'independent';fresh.mkdir();cmd+=['--bind',str(fresh),str(case/'warm')]
        if phase!='before':cmd+=['--ro-bind',str(IMAGE),str(SDK/'bin/cargo')]
        cmd+=['--','taskset','-c','8-11',sys.executable,'-B',__file__,'inner',str(case),phase,str(out)]
        p=subprocess.run(cmd,capture_output=True,timeout=150);(out/'worker.stderr').write_bytes(p.stderr);assert p.returncode==0,(case,phase,p.stderr[-1000:]);rows[phase]=read(out/'row.json')
        print(case.name,phase,rows[phase]['value'],rows[phase]['fresh']['hold_direct'],len(rows[phase]['full_compilers']),flush=True)
    assert program(original)[0]==17 and sha(original)==old_sha
    allrows[case.name]=rows;save(H/'partial.json',allrows)
assert len(allrows)==6;save(H/'complete.json',allrows)
