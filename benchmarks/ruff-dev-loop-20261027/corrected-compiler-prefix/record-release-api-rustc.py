from pathlib import Path
import hashlib,json,os,subprocess,sys
root=Path('__PRIVATE_RECORDS__');num=len(list(root.glob('*.json')));args=['__REAL_FRONT__','--sysroot','__SYSROOT__',*sys.argv[1:]];p=subprocess.run(args,capture_output=True);messages=[];stderr=p.stderr.decode(errors='replace');sources={}
for name in ('lib.rs','private.rs'):
 if Path(name).is_file(): sources[name]=Path(name).read_text()
for l in stderr.splitlines():
 if l.startswith('{'):
  try:messages.append(json.loads(l))
  except ValueError:pass
links={}
for n in ('liblib.rmeta','original-metadata.rmeta'):
 if Path(n).exists():
  st=Path(n).stat();links[n]=[st.st_dev,st.st_ino,st.st_size]
(root/(str(num).zfill(3)+'.json')).write_text(json.dumps({'argv':[str(a) for a in args],'status':p.returncode,'sources':sources,'metadata_hash':[j['public_api_hash']['value'] for j in messages if 'public_api_hash' in j],'reused_prefix':'reused metadata item prefix' in stderr,'prefix_messages':[l for l in stderr.splitlines() if 'reused metadata item prefix' in l],'diagnostics':[j['code']['code'] for j in messages if j.get('code')],'links':links,'stdout':p.stdout.decode(errors='replace'),'stderr':stderr})+'\n')
sys.stdout.buffer.write(p.stdout);sys.stderr.buffer.write(p.stderr);sys.exit(p.returncode)
