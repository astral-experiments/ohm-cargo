"""Replay the verified Linux x86-64 GNU driver and stock Wild filename selector."""
import argparse,hashlib,json,shutil,subprocess,tempfile
from pathlib import Path
def digest(path):
 with path.open('rb') as handle:return hashlib.file_digest(handle,'sha256').hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--wild-ld',type=Path,required=True,help='Directory containing the qualified ld.bfd binary');a=p.parse_args();sdk=a.wild_ld.resolve();base=Path(__file__).resolve().parent/'genuine-cgu-name-selector-v2';subjects=json.loads((base/'complete.json').read_bytes());result={}
 for r in subjects:
  assert digest(sdk/'ld.bfd')==r['rows'][0]['sha256_executed_wild'];s=base/r['target'];source=s/'genuine-input.rcgu.o';assert digest(source)==r['source_object_sha'];assert digest(s/'selector.ld')==r['selector_sha256']
  with tempfile.TemporaryDirectory() as name:
   d=Path(name);script=d/'selector.ld';shutil.copyfile(s/'selector.ld',script);subprocess.run(['cc','-c',str(s/'start.s'),'-o',str(d/'entry.o')],check=True,capture_output=True);lib=d/'shadow';lib.mkdir();shutil.copyfile(script,lib/'libutil.so');out={}
   for mode in ('explicit-script','earlier-search-library'):
    pair=[]
    for raw in r['actual_source_argv_paths']:
     obj=d/Path(raw).name;shutil.copyfile(source,obj);assert digest(obj)==r['source_object_sha'];exe=d/'program';subprocess.run(['gcc','-B'+str(sdk)+'/', '-fuse-ld=bfd','-nostdlib','-static','-no-pie','-Wl,--gc-sections','-Wl,--build-id=none','-o',str(exe),str(d/'entry.o'),str(obj),*(['-Wl,-T,'+str(script)] if mode=='explicit-script' else ['-L'+str(lib),'-Wl,-Bdynamic','-lutil'])],cwd=d,check=True,capture_output=True);pair.append(subprocess.run([str(exe)],cwd=d,timeout=2).returncode)
    assert pair==[r['section_size'],0];out[mode]=pair
   result[r['target']]=out
 print(json.dumps(result,indent=2,sort_keys=True))
if __name__=='__main__':main()
