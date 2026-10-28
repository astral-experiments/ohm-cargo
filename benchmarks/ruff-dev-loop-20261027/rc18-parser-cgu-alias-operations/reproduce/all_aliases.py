"""Count observed incremental-work-product links per full Rust compiler from the retained trace."""
import ast
import collections
import hashlib
import json
import re
import sys
from pathlib import Path

def digest(value):
    return hashlib.sha256(value).hexdigest()

def load(raw):
    files={int(p.name.split('.')[-1]):p for p in raw.glob('exec.*')}
    children=collections.defaultdict(set)
    records={}
    matcher=re.compile(r'^execve\("[^"\\]*", (\[.*\]), ')
    term=re.compile(r'\)\s+= ([0-9]+)(?:<[^\n]*>)?$')
    quote=re.compile(r'"((?:[^"\\]|\\.)*)"')
    for tid,path in files.items():
        for line in path.open(errors='surrogateescape'):
            v=line.rstrip()
            if v.startswith(('clone(','clone3(')) and 'CLONE_THREAD'in v and (m:=term.search(v)):
                children[tid].add(int(m[1]))
            if v.startswith('execve(') and '/bin/rustc"' in v and '"--crate-name",' in v and v.endswith('= 0'):
                match=matcher.match(v)
                assert match
                argv=ast.literal_eval(match[1])
                assert tid not in records
                records[tid]=(argv,digest(v.encode('utf-8','surrogateescape')))
    receipts=[]
    for top,(argv,raw_sha)in sorted(records.items()):
        types=[a for i,a in enumerate(argv)if i and argv[i-1]=='--crate-type']
        name=argv[argv.index('--crate-name')+1]
        if 'link-only'in argv or '-Zlink-only'in argv:
            receipts.append({'name':name,'types':types,'kind':'link-only','root':top,'exec_sha256':raw_sha})
            continue
        family={top}; todo=[top]
        while todo:
            extra=children[todo.pop()]-family
            todo.extend(extra)
            family.update(extra)
        out=Path(argv[argv.index('--out-dir')+1])
        assert out.is_absolute()
        successes,removals,reads,errors=collections.Counter(),collections.Counter(),collections.Counter(),collections.Counter()
        other_classes=collections.Counter()
        native_copy_calls=collections.Counter()
        first={}
        raws=collections.defaultdict(list)
        for tid in family:
            for line in files[tid].open(errors='surrogateescape'):
                v=line.rstrip(); f=v.partition('(')[0]
                if f in ('copy_file_range','sendfile','splice'):
                    if (m:=term.search(v)):native_copy_calls[f]+=int(m[1])
                if '.rcgu.o'not in v or f not in ('open','openat','openat2','link','linkat','unlink','unlinkat'):continue
                q=quote.findall(v); paths=[Path(p) for p in q]
                if not paths:continue
                t=paths[-1] if f in ('link','linkat') else paths[0]
                if t.parent!=out or not t.name.endswith('.rcgu.o'):continue
                s=term.search(v);h=digest(v.encode('utf-8','surrogateescape'))
                if not s:
                    err=re.search(r'= -1 ([A-Z0-9]+)',v)
                    errors[(f,err[1] if err else 'unfinished')]+=1
                    continue
                if f in ('link','linkat'):
                    assert len(paths)==2
                    src=paths[0]
                    c='incremental working CGU' if ('incremental' in src.parts and
                        any(p.endswith('-working') for p in src.parts) and
                        src.suffix=='.o') else 'other'
                    other_classes[c]+=1
                    if c=='incremental working CGU':
                        successes[t.name]+=1;first[t.name]=src.name;raws['link_'+t.name].append(h)
                elif f in ('unlink','unlinkat'):
                    removals[t.name]+=1;raws['unlink_'+t.name].append(h)
                elif 'O_RDONLY' in v:
                    reads[t.name]+=1;raws['read_'+t.name].append(h)
        pure=types in (['lib'],['rlib'])
        assert all(n==1 for n in successes.values())
        counts={'hardlinked':len(successes),'removed':sum(0<removals[n] for n in successes),
                'read_in_rustc':sum(0<reads[n] for n in successes),
                'unlinked_not_from_working_link':len(removals.keys()-successes.keys())}
        rows=[[n,first[n],raws['link_'+n],raws['read_'+n],raws['unlink_'+n]] for n in sorted(successes)]
        receipts.append({'name':name,'types':types,'kind':'full','root':top,'exec_sha256':raw_sha,
                         'family':len(family),'pure':pure,'counts':counts,
                         'hardlink_source_classes':dict(other_classes),
                         'matched_error_counts':[[a,b,c] for (a,b),c in sorted(errors.items())],
                         'kernel_copy_returned_bytes_over_all_family_files':dict(native_copy_calls),
                         'matched_event_roster_sha256':digest(json.dumps(rows,separators=(',',':')).encode()),
                         'emit':[a for a in argv if a.startswith('--emit')],
                         'rlink_flags':[a for a in argv if 'relink-only'in a],
                         'save_temps_flags':[a for a in argv if 'save-temps'in a]})
    return {'all_rustc_jobs':receipts}
if __name__=='__main__':
    result=load(Path(sys.argv[1]))
    print(json.dumps(result,sort_keys=True,indent=2))
