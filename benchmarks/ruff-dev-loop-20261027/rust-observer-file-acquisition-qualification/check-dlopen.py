"""Test whether loading from sealed bytes preserves the native plug-in's ordinary path contract."""
from pathlib import Path
import ctypes,fcntl,hashlib,json,os,subprocess,sys
if len(sys.argv)==1:
    root=Path(__file__).resolve().parent/'dlopen-path-control';root.mkdir(exist_ok=True)
    (root/'sibling.c').write_text('int unique_observer_sibling(void) { return 17; }\n')
    (root/'plugin.c').write_text('''
#define _GNU_SOURCE
#include <dlfcn.h>
#ifdef REQUIRE_ORIGIN
extern int unique_observer_sibling(void);
int read_value(void) { return unique_observer_sibling(); }
#else
int read_value(void) { return 17; }
#endif
const char *owner_path(void) {
    Dl_info info;
    return dladdr((void *)owner_path, &info) ? info.dli_fname : 0;
}
''')
    env=dict(os.environ);env.pop('LD_LIBRARY_PATH',None);commands=[]
    for argv in [
        ['cc','-shared','-fPIC','sibling.c','-Wl,-soname,libunique_ohm_sibling.so','-o','libunique_ohm_sibling.so'],
        ['cc','-shared','-fPIC','plugin.c','-ldl','-o','no-deps.so'],
        ['cc','-shared','-fPIC','-DREQUIRE_ORIGIN','plugin.c','-ldl','-L.','-lunique_ohm_sibling','-Wl,-rpath,$ORIGIN','-o','origin.so'],
    ]:
        subprocess.run(argv,cwd=root,env=env,check=True);commands.append(argv)
    rows={}
    for file in ['no-deps.so','origin.so']:
        for mode in ['file','sealed']:
            proc=subprocess.run([sys.executable,'-B',__file__,str(root/file),mode],capture_output=True,env=env,check=True)
            rows[f'{file}/{mode}']=json.loads(proc.stdout)
    assert rows['no-deps.so/file']['path']==str(root/'no-deps.so') and rows['no-deps.so/sealed']['path'].startswith('/proc/self/fd/')
    assert rows['origin.so/file']['value']==17 and 'libunique_ohm_sibling.so' in rows['origin.so/sealed']['error']
    out=dict(commands=commands,rows=rows,input_hashes={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in root.iterdir() if f.is_file()})
    (root/'result.json').write_text(json.dumps(out,indent=2,sort_keys=True)+'\n');print(json.dumps(rows))
else:
    file=Path(sys.argv[1]);mode=sys.argv[2];name=str(file);fd=None
    if mode=='sealed':
        fd=os.memfd_create('observed-proc-macro',os.MFD_ALLOW_SEALING|os.MFD_CLOEXEC)
        data=file.read_bytes();assert os.write(fd,data)==len(data)
        fcntl.fcntl(fd,fcntl.F_ADD_SEALS,fcntl.F_SEAL_WRITE|fcntl.F_SEAL_SHRINK|fcntl.F_SEAL_GROW|fcntl.F_SEAL_SEAL);name=f'/proc/self/fd/{fd}'
    try:
        lib=ctypes.CDLL(name);lib.owner_path.restype=ctypes.c_char_p
        print(json.dumps(dict(path=os.fsdecode(lib.owner_path()),value=lib.read_value())))
    except OSError as error:
        print(json.dumps(dict(error=str(error))))
