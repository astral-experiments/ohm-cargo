"""Bind each successful kernel exec and raw stream before substituting private mount paths."""
from pathlib import Path
import argparse, ast, gzip, hashlib, json, re, runpy

HERE=Path(__file__).resolve().parent
native=runpy.run_path(str(HERE/'native_detail.py'))
FULL='resolve_with_registry:resolve_with_previous:register_patch_entries:'
HIT='reusing the cached workspace resolution'
WILD='lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd'

def sha(raw): return hashlib.sha256(raw).hexdigest()
def dump(value): return (json.dumps(value,indent=2,sort_keys=True)+'\n').encode()
def save(path,value): path.write_bytes(gzip.compress(dump(value),mtime=0) if path.suffix=='.gz' else dump(value))

def norm(text, paths):
    for original, alias in paths:
        text=text.replace(original,alias)
    return re.sub(r'(<arena>/cargo-home/registry/(?:src|index|cache)/)[^/\s\x22]+/',r'\1<registry>/',text)

def project(root,view,sdk,proxies,report):
    complete=json.loads((root/'complete.json').read_text())
    assert [a['arm'] for a in complete['arms']]==['A','B']
    replacements=[(str(view),'<arena>'),(str(sdk),'<sdk>'),(str(proxies),'<proxies>')]
    data={}; index={}
    for arm,terminal in zip('AB',complete['arms'],strict=True):
        armroot=root/arm
        assert json.loads((armroot/'terminal.json').read_text())==terminal
        assert len(terminal['rows'])==28
        data[arm]={}
        for name,digest in terminal['rows'].items():
            path=armroot/name; row=json.loads((path/'row.json').read_bytes())
            assert sha((path/'row.json').read_bytes())==digest
            events=native['native_execs']((path/'exec').read_bytes())
            assert [{k:v for k,v in e.items() if k!='argv'} for e in events]==row['events']
            raw={file.name:file.read_bytes() for file in path.iterdir() if file.is_file() and file.name!='row.json'}
            assert all(sha(raw[f])==row[k] for f,k in [('stdout','stdout'),('stderr','stderr'),('exec','trace')])
            lines=raw['exec'].decode().splitlines()
            for event in events:
                match=re.search(r'execve(?:at)?\((?:[^\x22,]+, )?(\x22(?:[^\x22\\]|\\.)*\x22)',lines[event['lines'][0]-1]); assert match
                native_path=Path(ast.literal_eval(match[1])); program=event['program']
                if program=='ld.bfd': assert native_path.resolve(strict=True)==(sdk/WILD).resolve(strict=True)
                elif program=='rustc': assert native_path==view/'ru/toolchains/ohm/bin/rustc'
                elif program=='cargo': assert native_path==(proxies/'cargo' if event['cargo_args'][:1]==['+ohm'] else view/'ru/toolchains/ohm/bin/cargo')
            normed={f:norm(v.decode(),replacements) for f,v in raw.items()}; assert all(str(view.parent) not in v and str(proxies) not in v and '.internal.' not in v for v in normed.values())
            data[arm][name]={'row':row,'streams':normed};index[arm+'/'+name]={f:{'bytes':len(raw[f]),'sha256':sha(raw[f]),'projection':sha(normed[f].encode())} for f in raw}
    save(report/'streams.json.gz',data);save(report/'raw-file-index.json.gz',index);save(report/'complete.json',complete)

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for key in ('raw','view','sdk','proxies','out'):ap.add_argument('--'+key,type=Path,required=True)
    a=ap.parse_args();a.out.mkdir(exist_ok=True);project(a.raw.resolve(),a.view.resolve(),a.sdk.resolve(),a.proxies.resolve(),a.out)
