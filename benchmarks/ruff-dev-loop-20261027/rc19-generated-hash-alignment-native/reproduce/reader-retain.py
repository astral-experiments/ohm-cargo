from pathlib import Path
import hashlib,json,os,shutil,subprocess
def compact(p):
 assert p.is_file()and not p.is_symlink()and (p.parent/'reader.rs').is_file()and (p.parent/'reader.out').is_file()and p.name=='reader';compressed=p.parent/'reader.retained.zst';assert not compressed.exists()
 with p.open('rb')as f:old=hashlib.file_digest(f,'sha256').hexdigest()
 with compressed.open('xb')as out:subprocess.run(['zstd','-3','-q','-c',p],stdout=out,check=True)
 with subprocess.Popen(['zstd','-q','-d','-c',compressed],stdout=subprocess.PIPE)as proc:
  new=hashlib.file_digest(proc.stdout,'sha256').hexdigest();assert proc.wait()==0 and old==new
 assert compressed.stat().st_size<p.stat().st_size;rec={'file':p.parent.name,'bytes':p.stat().st_size,'compressed':compressed.stat().st_size,'sha256':old};p.unlink();return rec
if __name__=='__main__':
 w=Path.home()/'.cache/ohm-script-hash-wall-rc19-v1';assert os.uname().nodename==os.environ['OHM_BENCH_INDEPENDENT_HOST'];root=w/'reports';fs=list(root.glob('*/reader'));rs=[compact(p)for p in fs];p=w/'saved-earlier-native-readers.json';assert not p.exists();p.write_text(json.dumps(rs,sort_keys=True));print(len(rs),sum(i['bytes']for i in rs),sum(i['compressed']for i in rs),shutil.disk_usage(w).free,flush=True)
