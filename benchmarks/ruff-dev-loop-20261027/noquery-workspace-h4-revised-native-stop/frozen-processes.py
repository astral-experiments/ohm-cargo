"""Classify successful execs by the actual packaged compiler and linker inodes."""
from pathlib import Path
from collections import Counter
import ast
import hashlib
import json
import re


def read(out, sdk, public):
    driver = sdk / 'bin/rustc'
    cargo = sdk / 'bin/cargo'
    wild = sdk / 'lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd'
    files, jobs, links, probes, cargos, cc, collect2 = {}, [], [], [], [], [], []
    observer_queries = []
    for f in sorted((out/'trace').glob('exec.*')):
        raw = f.read_bytes(); pid = int(f.suffix[1:]); files[f.name] = hashlib.sha256(raw).hexdigest()
        pending = None; calls = []; last = None
        for row in raw.splitlines():
            _, _, line = row.partition(b' ')
            if m := re.match(rb'^\+\+\+ exited with (\d+) \+\+\+', line):
                last = int(m[1])
            if line.startswith((b'execve(', b'execveat(')) and line.endswith(b'<unfinished ...>'):
                assert pending is None; pending = line.removesuffix(b'<unfinished ...>'); continue
            if m := re.match(rb'^<\.\.\. (?:execve|execveat) resumed>(.*)$', line):
                assert pending; line = pending + m[1]; pending = None
            if not line.startswith((b'execve(', b'execveat(')) or not re.search(rb'\)\s+= 0$',line):
                continue
            match = re.match(rb'execve\(("(?:[^"\\]|\\.)*"),\s*(\[.*\]),\s*(?:0x[\da-f]+|NULL)',line)
            assert match, (pid,line[:130])
            image = Path(ast.literal_eval(match[1].decode())); args = ast.literal_eval(match[2].decode())
            assert isinstance(args,list) and all(isinstance(s,str) for s in args)
            calls.append((image,args,hashlib.sha256(row).hexdigest()))
        assert pending is None
        for image, args, sig in calls:
            assert str(image) not in public
            if image.name == 'cargo' and image.is_file() and image.samefile(cargo): cargos.append(pid)
            if image.name == 'rustc' and image.is_file() and image.samefile(driver):
                if '-Zohm-observer-dep-info' in args and '--print=sysroot' in args:
                    observer_queries.append([pid,sig])
                if '--crate-name' not in args or any(s.startswith('--print') for s in args):
                    probes.append([pid,sig]); continue
                crate = args[args.index('--crate-name')+1]
                if crate in ('__','___'): probes.append([pid,sig]); continue
                link = '-Zlink-only' in args or any(args[i:i+2] == ['-Z','link-only'] for i in range(len(args)))
                jobs.append([pid,crate,'link-only' if link else 'full',last,sig])
            if image.name in ('ld','ld.bfd','ld.gold','ld.lld','rust-lld','mold','wild','ld.wild'):
                if '-o' in args:
                    dest = args[args.index('-o')+1]
                elif any(s in args for s in ('--help','--version','-V','-v')):
                    continue
                else:
                    assert any(s.endswith('/crti.o') for s in args) and any(s.endswith('/crtn.o') for s in args)
                    assert any(Path(s).parent in (Path('/tmp'),sdk.parent/'tmp') and s.endswith('.o') for s in args), (pid,image,args[:4])
                    dest = 'a.out'
                is_wild = image.is_file() and image.samefile(wild)
                links.append([pid,is_wild,dest,last,sig,str(image)])
            if '-o' in args and image.name in ('gcc','cc','gcc-13','x86_64-linux-gnu-gcc-13'):
                cc.append(pid)
            if '-o' in args and image.name == 'collect2': collect2.append(pid)
    assert len(cargos) == 1 and files, (cargos,len(files))
    assert all(isinstance(x[3],int) for x in jobs+links)
    result = {'cargo':cargos,'jobs':jobs,'linkers':links,'rustc_queries':probes,'first_observer_capability_queries':observer_queries,'cc':cc,'collect2':collect2,
              'counts':{'rustc':dict(Counter(x[2] for x in jobs)), 'wild':sum(x[1] for x in links),
                        'system':sum(not x[1] for x in links), 'queries':len(probes)}}
    for name,obj in [('native-processes.json',result),('trace-files.json',files)]:
        (out/name).write_text(json.dumps(obj,sort_keys=True,indent=2)+'\n')
    return result
