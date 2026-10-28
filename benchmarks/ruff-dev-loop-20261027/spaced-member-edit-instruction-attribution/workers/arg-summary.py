from pathlib import Path
import sys,json
p=Path(sys.argv[1]);d=p/'spaced-dirty-attribution-20261028'
for image in 'BC':
    state=d/'states'/(image+'wasm-ty_wasm')/'state'
    file=d/('observations/03-'+image+'/edit/life.json')
    r=json.loads(file.read_bytes())
    for job in r['records']:
        args=job['argv']
        if '--crate-name' not in args:continue
        name=args[args.index('--crate-name')+1]
        if name not in ('ty_wasm','ty_vendored'):continue
        options=[arg for arg in args if arg.startswith(('incremental=','codegen-units=','debuginfo=','metadata=','-Zohm','-Zthreads','relink','public-api-hash','cache-proc-macros','-Zchecksum'))]
        inc=next((arg[12:] for arg in args if arg.startswith('incremental=')),None)
        cells={}
        if inc:
            r=Path(inc).relative_to(p/'member-build-matched-canonical-v1/ruff target')
            idir=state/'target'/r
            if idir.exists():
                import collections
                cells=collections.Counter((f.suffix if f.suffix else f.name) for f in idir.rglob('*') if f.is_file())
        print(image,name,options, 'IC_FILES',cells)
