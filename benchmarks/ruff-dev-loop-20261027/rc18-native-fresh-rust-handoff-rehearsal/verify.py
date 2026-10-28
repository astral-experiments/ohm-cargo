"""Re-read physical H2 exec traces, the two native ELFs and GCC's later, independent decisions."""
from pathlib import Path
import ast,hashlib,io,json,os,re,subprocess,tarfile,tempfile
root=Path(__file__).resolve().parent;h=lambda b:hashlib.sha256(b).hexdigest()
b=(root/'h2.tar.gz').read_bytes();assert h(b)=='0e6fd1166b8cb703efd39add4ae78acf3a04b9b3d66f85a390eb798c266fea80'
unsafe=re.compile(rb'openai[.](org|com|internal)|artifactory[.]|authorization: bearer|github_pat_|ghp_[A-Za-z0-9]{16}',re.I)
with tarfile.open(fileobj=io.BytesIO(b))as t:
 rows={m.name:t.extractfile(m).read() for m in t};assert len(rows)==len(set(t.getnames()))==66
assert not any(unsafe.search(v) for v in rows.values())
ledger=json.loads(rows['artifacts.json']);assert set(ledger)==set(rows)-{'artifacts.json'} and all(h(rows[k])==v for k,v in ledger.items())
j=lambda n:json.loads(rows[n]);term=j('host/trial1.terminal.json')
assert term['status']==0 and term['before']>=term['floor'] and term['after']>=term['floor'] and term['arch']=='x86_64' and term['uid']==1000
assert term['physical']=={'cargo':'cfc66a7ceee5cad8f8939245d359e4db0d2b6f2abb5760c7cbefa6c9a1d454f8','rustc':'4fa9a18b77430bcc416e88561b6fe5797d98b996a7698b9f3bd11d4e7817a19f','driver':'22abce6921b46f93f387c7d3d99cefa4df9c0a866619447077699ef81a73827f'}
allrows={s:j(f'commands/{s}/structured.json') for s in ('cold','train','repeat','higher','highergold','malformed','restored','restoredgold')}
for name,v in allrows.items():
 prefix='commands/'+name+'/';raw=rows[prefix+'trace.private'].splitlines();ids={h(l):l for l in raw}
 assert len(v['actual_processes'])>3
 for proc in v['actual_processes']:
  line=ids[proc['original_line_sha256']].decode()
  m=re.match(r'^(\d+)\s+execve\(("(?:[^"\\]|\\.)*"), (\[.*\]), (?:0x[^ ]+ )?/\* [0-9]+ vars \*/\)\s+= 0$',line)
  assert int(m[1])==proc['pid'] and ast.literal_eval(m[2])==proc['exe'] and ast.literal_eval(m[3])==proc['argv']
  if proc['kind'] in ('full','link-only'):
   args=proc['argv'];opts={a[2:] for a in args if a.startswith('-Z') and len(a)>2}|{b for a,b in zip(args,args[1:]) if a=='-Z'}
   assert ('link-only' in opts)==(proc['kind']=='link-only')
 assert any(x['kind']=='cc' for x in v['actual_processes']) and any(x['kind']=='collect2' for x in v['actual_processes'])
 assert v['command'][1:]==['+ohm','test','--no-run','-p','reader','--test','reader_case','--locked','--offline','-j1','--message-format=json']
 assert v['shim']['single_worker'] and v['shim']['parent_exe'].endswith('/collect2')
 assert (v['status']==101)==(name=='malformed')
pos=allrows['repeat']
assert pos['shim']['decision']=='fixture-native-fresh' and pos['shim']['before']==pos['shim']['after'] and pos['stock']==0 and not pos['cargo_reported']
assert pos['ru_rows']==[['leaf','full'],['reader_case','link-only']]
assert pos['shim']['key']==allrows['train']['shim']['key'] and pos['shim']['key']!=allrows['higher']['shim']['key']
for n,value in [('higher','83'),('restored','41')]:
 assert allrows[n]['final_file']==allrows[n+'gold']['final_file']==h(rows['abi/'+n+'.elf'])
 assert allrows[n]['stock']>=1 and allrows[n]['app']==('native-value='+value)
 with tempfile.TemporaryDirectory() as tmp:
  exe=Path(tmp)/'case';exe.write_bytes(rows['abi/'+n+'.elf']);exe.chmod(0o700)
  cp=subprocess.run([exe],capture_output=True,timeout=5);assert cp.returncode==0 and cp.stdout.strip()==('native-value='+value).encode()
assert allrows['malformed']['stock']==1 and allrows['malformed']['shim']['status']!=0
g=json.loads((root/'gcc-post.json').read_bytes());s=g['rows'];assert len(s)==8
assert len({r['raw_native_argv_sha256'] for r in s})==len({r['stock_at_child_exit'] for r in s})==len({r['input_object'] for r in s})==1
for i in (0,4):
 a=s[i:i+4];assert [r['gcc_status'] for r in a]==[0,0,1,0] and [r['program_exit'] for r in a]==[41,83,41,41] and all(r['wild_status']==0 for r in a)
 assert a[1]['gcc_out']!=a[1]['stock_at_child_exit'] and a[2]['post']['exit']==7
print('8 actual R2 Cargo commands, real native child choices and statuses, both independently launched ELF oracles, and 8 post-link GCC controls verified.')
