from pathlib import Path
import json,os,shutil,subprocess as sp,sys,hashlib
rr=Path(__file__).resolve().with_name('recover.py').read_text();exec(compile(rr.split("rr=root/'remove_files_before_macro'")[0],__file__,'exec'))
item=main/'leaf/src/lib.rs';orig=item.read_bytes();out=root/'producer-tables';out.mkdir(exist_ok=False)
for name,buf in [('short',orig),('long',orig.replace(b'#[cfg(any())]',b'#[cfg(all())]')),('short-restored',orig)]:
 assert buf.count(b'#[cfg(')==9;item.write_bytes(buf)
 art,_=run(out/name,'leaf');p=next(Path(x) for x in art['leaf']['filenames'] if x.endswith('.rmeta'));shutil.copyfile(p,out/(name+'.rmeta'));print(name,sha(p),flush=True)
