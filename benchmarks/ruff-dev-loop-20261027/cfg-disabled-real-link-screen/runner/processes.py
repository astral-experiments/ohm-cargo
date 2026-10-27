"""Count actual compiler, native probe and linker commands in independently traced runs."""
from pathlib import Path
import ast,re
from shared import *

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

def parsed(out,j):
    jobs=[]; links=[]; probes=[]; images=[]; cc=[];collect=[];public=set(j['executables']); cargo=False
    native=load(TRANSFER/'installation.json')['bundled_wild']
    for pid,path,args in records(out):
        exe=Path(path);images.append((pid,str(exe)))
        need(str(exe) not in public,('cargo ran test',exe))
        if exe.name=='cargo' and exe.is_file() and exe.samefile(FROZEN/'bin/cargo'):cargo=True
        if exe.name=='rustc' and '--crate-name' in args:
            cr=args[args.index('--crate-name')+1]
            if cr in ('__','___') or any(x.startswith('--print=') for x in args):continue
            mode='link-only' if any(x in ('-Zlink-only','link-only') for x in args) else 'full'
            target=next((a for a in args if a.endswith('tests/api.rs')),None)
            if cr=='api':need(target is not None and target.split('/')[-3] in ('ty_wasm','ruff_wasm'),('api source',pid,target))
            jobs.append([pid,cr,mode,(target.split('/')[-3] if target else None),any('--threads=1' in a for a in args)])
        if exe.name=='collect2' and '-o' in args:collect.append(pid)
        if exe.name in ('cc','gcc','gcc-13','x86_64-linux-gnu-gcc-13') and '-o' in args:cc.append(pid)
        if exe.name in ('ld','ld.bfd','wild','ld.wild','rust-lld','ld.lld','ld.gold','mold'):
            if '-o' not in args:
                need('--help' in args or '--version' in args,('unexpected native call',exe,args[:12]));probes.append([pid,exe.name,args[-1]]);continue
            dest=args[args.index('-o')+1]; links.append([pid,Path(dest).name,exe.is_file() and exe.samefile(P/native),'--threads=1' in args])
    need(cargo,'selected Cargo image not in exec trace')
    return {'rustc':jobs,'native_links':links,'native_probes':probes,'cc_with_output':cc,'collect2_with_output':collect,'total_execs':len(images)}
