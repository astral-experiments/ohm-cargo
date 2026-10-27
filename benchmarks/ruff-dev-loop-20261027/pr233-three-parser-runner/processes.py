"""Match actual rustc/cc/Wild invocations to the saved recipe that survived that process."""
import ast, re
from pathlib import Path
from collections import Counter
from common import FROZEN, TARGET, SHARED, need, sha
from state import WASM, PLAN

def records(where):
    for f in sorted(where.glob('exec.*')):
        pending=None
        for row in f.read_text(errors='replace').splitlines():
            if row.startswith(('execve(', 'execveat(')) and row.endswith('<unfinished ...>'):
                need(pending is None,('overlapping exec',f));pending=row.removesuffix('<unfinished ...>');continue
            resumed=re.match(r'^<\.\.\. (execve(?:at)?) resumed>(.*)$',row)
            if resumed:
                need(pending is not None and pending.startswith(resumed[1]+'('),('missing pending exec',f));row,pending=pending+resumed[2],None
            if not re.search(r'\)\s+= 0$',row) or not row.startswith(('execve(', 'execveat(')):continue
            m=re.match(r'execve\(("(?:[^"\\]|\\.)*"),\s*(\[.*\]),\s*(?:0x[\da-f]+|NULL)',row)
            need(m is not None,('unparsed successful exec',f,row[:140]))
            argv=[ast.literal_eval(s) for s in re.findall(r'"(?:[^"\\]|\\.)*"',m[2])]
            yield f.name,ast.literal_eval(m[1]),argv
        need(pending is None,('unfinished exec',f))

def parse(directory,mode,before,after):
    images=[];jobs=[];queries=[];native={'cc':[],'collect2':[],'wild':[]};extern_dirs={};mixed_inputs={};mixed_links={};loaded=False
    for proc,path,args in records(directory):
        img=Path(path);images.append([proc,path])
        if img.name=='cargo' and img.is_file() and img.samefile(FROZEN/'bin/cargo'):loaded=True
        need(not(img.is_relative_to(TARGET) or img.is_relative_to(SHARED)) or '/build/' in path,('executed a test or target program',img))
        if img.name=='rustc':
            crate=args[args.index('--crate-name')+1] if '--crate-name' in args else None
            if not crate or crate in ('___','__') or '--print=file-names' in args:
                queries.append([proc,crate,args[1:]]);continue
            checked=[x.split('=',1)[1] for x in args if 'ohm-checked-mixed-rlink=' in x]
            is_link=any(x in ('-Zlink-only','link-only') for x in args)
            if checked:
                need(len(checked)==1 and crate in WASM and not is_link,('unexpected guarded invocation',crate,checked))
                recipe=checked[0];need(recipe in after,('missing final checked recipe',recipe))
                kind='checked-native' if recipe in before and before[recipe][:2]==after[recipe][:2] else 'checked-full-fallback'
            else:
                recipe=None;kind='link-only' if is_link else 'full'
            jobs.append({'pid':proc,'crate':crate,'kind':kind,'recipe':recipe})
            if crate in WASM and not is_link:
                paths=[]
                for i,x in enumerate(args):
                    if x=='-L':paths+=['-L',args[i+1]]
                    elif x.startswith('-L') and len(x)>2:paths.append(x)
                need(paths,('missing extern search path',crate));extern_dirs[crate]=paths
                externs={}
                for i,arg in enumerate(args):
                    if arg=='--extern' and '=' in args[i+1]:
                        name,p=args[i+1].split('=',1);file=Path(p);externs[name]=[p,sha(file)] if file.is_file() else [p,None]
                mixed_inputs[crate]={'argv':args,'externs':externs}
        elif img.name=='collect2':native['collect2'].append(proc)
        elif img.name=='ld.bfd' and img.parent.name=='wild-ld':
            native['wild'].append(proc)
            if '-o' in args:
                dst=Path(args[args.index('-o')+1]);cr=next((w for w in WASM if dst.name.startswith('lib'+w) and '.so' in dst.name),None)
                if cr:
                    mixed_links[cr]={'argv':args,'retained_archive_inputs':{p:sha(Path(p)) for p in args if p.endswith(('.a','.rlib')) and Path(p).is_file()}}
        elif img.name in ('cc','gcc','x86_64-linux-gnu-gcc','x86_64-linux-gnu-gcc-13','gcc-13'):native['cc'].append(proc)
    need(loaded,('trace never loaded selected Cargo',directory))
    return {'images':images,'jobs':jobs,'queries':queries,'native':native,'extern_dirs':extern_dirs,'mixed_inputs':mixed_inputs,'mixed_links':mixed_links}

def qualify(trace,mode,arm,expected):
    jobs=trace['jobs'];q=trace['queries'];by=Counter(x['kind'] for x in jobs);native=trace['native']
    need(not any(any('crate-hash' in s or 'crate_hash' in s for s in args) for _,_,args in q),('standalone hash query',q))
    if expected=='fresh':
        need(not jobs and not any(native.values()),('non-fresh trace',jobs,native));return
    if expected not in ('conditioning','edit','forced'):return
    want=PLAN['endpoints'][mode];both=arm=='C' and expected=='edit'
    f=[j['crate'] for j in jobs if j['kind'] in ('full','checked-full-fallback')]
    required=['ruff_python_parser'] if mode=='build' else ['api','api','ruff_python_parser','ruff_python_parser']
    if expected=='conditioning' and arm=='C':
        # An initially empty capsule may need a first genuine checked-full fallback
        # before an edit/restore in this exact consumer graph becomes reusable.
        for crate in WASM:
            kinds=[j['kind'] for j in jobs if j['crate']==crate and j['kind']!='link-only']
            need(len(kinds)==1 and kinds[0] in ('full','checked-full-fallback','checked-native'),('conditioning mixed job',crate,kinds))
            if kinds[0]!='checked-native':required.append(crate)
    elif not both:required.extend(WASM)
    need(sorted(f)==sorted(required),('unexpected true full jobs',f,required,by))
    if expected!='conditioning' or arm!='C':
        need(sorted(x['crate'] for x in jobs if x['kind']=='checked-native')==(sorted(WASM) if both else []),('guarded hits',jobs))
    need(by['link-only']==(6 if mode=='build' else 62),('ordinary link-only',by))
    n=want['expect_same_wild'];need(len(native['wild'])==len(native['cc'])==len(native['collect2'])==n,('native link phases',native))
    if both:need(by['checked-full-fallback']==0,'unexpected fallback')

