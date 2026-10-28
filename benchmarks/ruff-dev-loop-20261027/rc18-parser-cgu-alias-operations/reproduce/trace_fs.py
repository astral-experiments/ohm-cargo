from snapshot import *
import time
D=Y/'archive-fs-restore';D.mkdir();(D/'raw').mkdir();report=Y/'native-archive-inputs/reconstruction/result.json';assert report.is_file();pp=json.loads((Y/'receipts/warm-reverse/processes.json').read_text());arg=next(v['args']for v in pp['jobs']if v['name']=='ruff_python_parser');out=Path(arg[arg.index('--out-dir')+1]);incr=Path(next(a.removeprefix('incremental=')for a in arg if a.startswith('incremental=')));folders=list(incr.glob('ruff_python_parser-*'));assert len(folders)==1

def inventory(label):
 all_out=[{'name':str(p.relative_to(out)),'bytes':p.stat().st_size,'sha256':sha(p)}for p in sorted(out.rglob('*'))if p.is_file()];work=[]
 for p in sorted(folders[0].rglob('*.o')):
  st=p.stat();work.append({'path':str(p),'dev':st.st_dev,'ino':st.st_ino,'bytes':st.st_size,'sha256':sha(p)})
 check={'unit_out':all_out,'incremental_work_products':work,'explicit_rcgu_files':[str(p)for p in out.rglob('*.rcgu.o')],'rlink_files_in_unit':[str(p)for p in out.parent.rglob('*.rlink')]};write(D/(label+'.json'),check)
sp.run(['git','diff','--quiet',OLD,'--'],cwd=W,check=True);inventory('before');sp.run(['git','apply','--check',Y/'change.patch'],cwd=W,check=True);sp.run(['git','apply',Y/'change.patch'],cwd=W,check=True);sp.run(['git','diff','--quiet',H,'--'],cwd=W,check=True);cmd=[PROXY/'cargo','+ohm','build','--message-format=json'];trace='execve,execveat,clone,clone3,fork,vfork,link,linkat,rename,renameat,renameat2,unlink,unlinkat,copy_file_range,sendfile,splice,open,openat,openat2';
with (D/'stdout.jsonl').open('xb') as so,(D/'stderr').open('xb')as se:q=sp.run(['strace','-ff','-qq','-s','65535','-yy','-e','trace='+trace,'-o',D/'raw/exec',*cmd],cwd=W,env=env(),stdout=so,stderr=se)
write(D/'exit.json',{'status':q.returncode,'selected':trace,'stock_cargo':sha(SDK/'bin/cargo')});assert q.returncode==0;inventory('after')
