"""Compare names from original PGO/branch profiles to exact release ELF symbol names."""
from pathlib import Path
import gzip,hashlib,sys,json,subprocess
p=Path(sys.argv[1]);out=Path(sys.argv[2]);files=[Path(s) for s in sys.argv[3:]]
def h(p):
 with p.open('rb') as s:return hashlib.file_digest(s,'sha256').hexdigest()
def elf(f):
 s=subprocess.Popen(['nm','--defined-only','--format=posix','--no-demangle',f],stdout=subprocess.PIPE);n={}
 for b in s.stdout:
  x=b.split();
  if len(x)>=3 and x[1] in [b't',b'T',b'W',b'w',b'i',b'I']:n[x[0].decode()]=1
 assert s.wait()==0 and len(n)>40_000;return n
names=[elf(f) for f in files];rows=[{'path':str(f),'sha256':h(f),'unique_function_symbols':len(s),'instrumentation_names':0,'instrumentation_records':0,'instrumentation_max_block_sum':0,'bolt_names':0,'bolt_endpoint_count':0,'bolt_endpoint_weight':0} for f,s in zip(files,names)];diff=[];baseline=names[0];out.parent.mkdir(exist_ok=True,parents=True)
with gzip.open(p,'rt') as g:
 info=json.loads(next(g));weight=[0,0,0,0,0,0]
 for line in g:
  name,pc,pw,bc,bw=json.loads(line);weight=[a+b for a,b in zip(weight,[int(pc>0),pc,pw,int(bc>0),bc,bw])];belongs=[name in ns for ns in names];
  for row,yes in zip(rows,belongs):
   if not yes:continue
   for key,v in zip(['instrumentation_names','instrumentation_records','instrumentation_max_block_sum','bolt_names','bolt_endpoint_count','bolt_endpoint_weight'],[int(pc>0),pc,pw,int(bc>0),bc,bw]):row[key]+=v
  if any(belongs) and not all(belongs):diff.append({'name':name,'present':belongs,'inst_records':pc,'inst_max_block':pw,'branch_endpoints':bc,'branch_weight':bw})
result={'profile':info,'index_sha256':h(p),'totals':weight,'inputs':rows,'all_symbol_pair_difference':{'left_only':len(names[0].keys()-names[1].keys()),'right_only':len(names[1].keys()-names[0].keys())},'original_profile_name_differences':diff};out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='original_profile_name_differences'}),len(diff))
