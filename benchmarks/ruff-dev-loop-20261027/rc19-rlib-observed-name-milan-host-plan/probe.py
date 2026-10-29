"""Read only the platform, tool identities and available space for the two Milan locations."""
from pathlib import Path
import hashlib,json,os,platform,re,shutil,subprocess as sp,sys


def sha(p):
 with p.open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()

def capture(*args):return sp.check_output(args,text=True).strip()

def usage(p):
 s=shutil.disk_usage(p);m=capture('findmnt','-n','-o','SOURCE,FSTYPE,OPTIONS','-T',str(p)).split();return {'size':s.total,'free':s.free,'filesystem':m[1],'source':m[0],'options':m[2]}

def main():
 role=sys.argv[1];assert role in ('original','new');home=Path.home();scratch_vols=[Path(x) for x in capture('findmnt','-rnt','ext4','-o','TARGET').splitlines() if Path(x).name.endswith('-scratch')];assert len(scratch_vols)==1;scratch=scratch_vols[0]/home.name
 # Keep separate logical capacities even where two paths have a common physical device.
 cpu={k.strip():v.strip()for line in capture('lscpu').splitlines()if ':'in line for k,v in [line.split(':',1)]}
 required={'os_release':platform.release(),'model':cpu['Model name'],'family':int(cpu['CPU family']),'stepping':int(cpu['Stepping']),'model_id':int(cpu['Model']),'count':int(cpu['CPU(s)']),'sockets':int(cpu['Socket(s)']),'threads_per_core':int(cpu['Thread(s) per core']),'numa_nodes':int(cpu['NUMA node(s)'])}
 hashes={k:sha(p)for k,p in {'proxy':home/'.cargo/bin/cargo','llvm-ar-18':Path('/usr/bin/llvm-ar-18'),'btrfs':Path('/usr/bin/btrfs'),'g++':Path('/usr/bin/g++'),'bwrap':Path('/usr/bin/bwrap'),'cc':Path('/usr/bin/cc'),'collect2':Path(capture('cc','-print-prog-name=collect2'))}.items()}
 ps=Path('/proc');seen=[]
 for p in ps.glob('[0-9]*'):
  try:comm=(p/'comm').read_text().strip()
  except FileNotFoundError:continue
  if comm in ('cargo','rustc','wild','wild-linker','ld.bfd','collect2','gcc','cc1','cc1plus','clang','zstd','rsync','valgrind'):seen.append(comm)
 placements={k:[p.stat().st_uid,p.stat().st_gid,oct(p.stat().st_mode&0o7777)]for k,p in [('root',Path('/')),('home-root',Path('/home')),('owner',home),('code',home/'code'),('oss',home/'code/oss'),('scratch',scratch.parent),('scratch-owner',scratch)]}
 mem={k:int(v.split()[0])*1024 for line in (ps/'meminfo').read_text().splitlines()if ':'in line for k,v in[line.split(':',1)]if k in ('MemTotal','MemAvailable','SwapTotal','SwapFree','Shmem')}
 c=Path('/sys/fs/cgroup');n=Path((ps/'self/cgroup').read_text().strip().split(':',2)[2].lstrip('/'));cgroups=[{k:(p/k).read_text().strip()for k in ('memory.max','memory.high','memory.swap.max')if(p/k).is_file()}for p in [c/n,*list((c/n).parents)[:len(n.parts)]]]
 resp=dict(role=role,cpu=required,uid=os.getuid(),gid=os.getgid(),affinity=sorted(os.sched_getaffinity(0)),owners=placements,native_executables=hashes,memory_bytes=mem,cgroup_limits=cgroups,mounts={'home':usage(home),'scratch':usage(scratch),'shm':usage(Path('/dev/shm'))},active_compilers=seen,load1=os.getloadavg()[0],boot_id=(ps/'sys/kernel/random/boot_id').read_text().strip(),hardware_name='Milan')
 if role=='new':
  G=home/'.cache/ohm-archive-ruff-milan-20261029-v1';O=scratch/'ohm-rlib-origin-product-20261029';uk='ohm-archive-names-milan-h4-20261029-v1'
  resp['new_destinations_absent']={k:not p.exists()for k,p in {'physical-home':home/'.cache'/uk,'physical-scratch':scratch/uk,'canonical-runtime':G,'canonical-sdk':O,'canonical-ruff':home/'code/oss/ohm-ruff-archives-1029-h2-bench','canonical-common':home/'code/oss/ohm-ruff-archives-1029-h2-source'}.items()}
 print(json.dumps(resp,sort_keys=True,indent=2))

if __name__=='__main__':main()
