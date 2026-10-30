from pathlib import Path
import json,os,sys,time
r=Path(sys.argv[1]);dest=Path(sys.argv[2]);p=Path('/proc'); seen={}; skipped=[]
def snapshot(t):
 stat=(p/str(t)/'status').read_text().splitlines();o={l.split(':',1)[0]:l.split(':',1)[1].strip() for l in stat if l.startswith(('Name:','Tgid:','Pid:','TracerPid:'))}
 if o['TracerPid']=='0':return None
 exe=(p/str(t)/'exe');ss=exe.stat();return [int(o['Tgid']),int(o['Pid']),int(o['TracerPid']),os.path.basename(os.readlink(exe)),ss.st_dev,ss.st_ino]
for slot in ['pair-1-R','pair-1-K','pair-2-K','pair-2-R']:
 for ph in ['native-edit-B','native-restore-B','native-edit-B-2','native-restore-B-2']:
  d=r/'runs'/slot/ph
  # Outside unscored flanks only one pathname existence lookup per half second. No native work or files sampled.
  while not d.is_dir():
   if (r/'boot.exit').exists():raise SystemExit('closed early')
   time.sleep(.45)
  rows={}
  if (d/'result.json').exists():skipped.append([slot,ph])
  while not(d/'result.json').exists():
   if (r/'boot.exit').exists():break
   for f in d.glob('sys.*'):
    tail=f.name[4:]
    if not tail.isdecimal() or tail in rows:continue
    try:z=snapshot(int(tail))
    except (FileNotFoundError,PermissionError,ProcessLookupError):continue
    if z:rows[tail]=z
   time.sleep(.045)
  seen[slot+'/'+ph]=rows
  out=dest/'tgids-live.tmp';out.write_text(json.dumps({'rows':seen,'skipped':skipped},separators=(',',':'))+'\n');out.replace(dest/'tgids-partial.json')
(dest/'tgids-terminal.json').write_text(json.dumps({'rows':seen,'skipped':skipped},separators=(',',':'))+'\n')
