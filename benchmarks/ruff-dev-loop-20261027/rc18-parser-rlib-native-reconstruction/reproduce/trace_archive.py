from snapshot import *
import time
if __name__=='__main__':
 while not (Y/'slice-result.json').exists():time.sleep(3)
 D=Y/'native-archive-inputs';D.mkdir();P.rename(Y/'states/slice-trial-terminal');sp.run(['cp','-a','--reflink=auto','--',Y/'states/full-history-terminal',P],check=True);q=sp.run(['g++','-O2','-std=c++20','-Wall',Y/'archive_observer.cc','-o',D/'observer'],capture_output=True);(D/'build.stderr').write_bytes(q.stderr);assert q.returncode==0,q.stderr
 # The restored workspace is a physical copy of the previous true whole-build state at the same canonical paths.
 baseline=Y/'receipts/settle-current';actual=read=lambda p:json.loads(p.read_text());z=next(u for u in actual(baseline/'artifacts.json')if u['local'] and u['target']=='ruff_python_parser');orig=next((Path(f),v['sha256'])for f,v in z['files'].items() if f.endswith('.rlib'));baseline_h=sha(orig[0]);ag=actual(Y/'objects'/('ar-'+baseline_h+'.json'));old={m['sha256']:m for m in ag['members']if m['name'].endswith('.rcgu.o')};assert len(old)==78;assert all(m['name'].endswith('.rcgu.o')for m in old.values());args=next(v['args']for v in actual(Y/'receipts/warm-reverse/processes.json')['jobs']if v['name']=='ruff_python_parser');incr=Path(next(v.removeprefix('incremental=')for v in args if v.startswith('incremental=')));roots=sorted(incr.glob('ruff_python_parser-*'));found={};candidates=0
 for root in roots:
  for p in sorted(root.rglob('*.o')):
   candidates+=1;hh=sha(p)
   if hh in old:
    held=D/'previous-work-products'/hh;held.parent.mkdir(exist_ok=True)
    if not held.exists():sp.run(['cp','--reflink=auto','--',p,held],check=True);assert sha(held)==hh
    found.setdefault(hh,[]).append({'path':str(p),'dev':p.stat().st_dev,'ino':p.stat().st_ino,'bytes':p.stat().st_size})
 write(D/'previous.json',{'archive':baseline_h,'old_product':str(orig[0]),'roots':list(map(str,roots)),'files_checked':candidates,'found':found,'required_all':sorted(old)});assert set(found)==set(old),(candidates,len(found),len(old),roots)
 sp.run(['git','apply','--reverse','--check',Y/'change.patch'],cwd=W,check=True);sp.run(['git','apply','--reverse',Y/'change.patch'],cwd=W,check=True);assert sp.run(['git','diff','--quiet',OLD,'--'],cwd=W).returncode==0
 with (D/'cargo-stdout.jsonl').open('xb')as stdout,(D/'cargo-stderr').open('xb')as err:
  q=sp.run([D/'observer',D,PROXY/'cargo','+ohm','build','--message-format=json'],cwd=W,env=env(),stdout=stdout,stderr=err)
 write(D/'exit.json',{'rc':q.returncode,'cargo':sha(SDK/'bin/cargo'),'observer':sha(D/'observer'),'parser_archive_after':capture(orig[0])});assert q.returncode==0,q.returncode
