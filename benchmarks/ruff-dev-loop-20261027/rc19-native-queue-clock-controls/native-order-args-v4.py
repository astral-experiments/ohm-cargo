"""Only substitute the three observed temporary operands, with their live bytes checked separately."""
from pathlib import Path
import hashlib, os, re

def fingerprints(events, target, temporary):
    results={}
    for event in events:
        role=event["role"]
        if role not in ("gcc","collect2","stock-wild"):continue
        args=event["argv"]; out=Path(event["out"]); assert out.is_relative_to(target)
        native=out.name; parent=out.parent; changes={}; copy=[]
        for pos,token in enumerate(args):
            if role=="gcc" and token.endswith("/raw-dylibs") and token.startswith("/"):
                path=Path(token);kind="raw_dylibs";prefix="";assert args[pos-1]=="-L"
            elif role!="gcc" and token.startswith("-L/") and token.endswith("/raw-dylibs"):
                path=Path(token[2:]);kind="raw_dylibs";prefix="-L"
            elif token.startswith("/") and token.endswith("/symbols.o"):
                path=Path(token);kind="object";prefix=""
            elif token.startswith("-plugin-opt=-fresolution="):
                prefix="-plugin-opt=-fresolution=";path=Path(token[len(prefix):]);kind="resolution"
                assert path.parent==temporary and re.fullmatch(r"cc[A-Za-z0-9_\-]+\.res",path.name),str(path)
            else:
                copy.append(token); continue
            if kind in ("object","raw_dylibs"):
                assert path.parent.parent==parent and re.fullmatch(r"rustc[A-Za-z0-9]+",path.parent.name),str(path)
            assert kind not in changes;changes[kind]=pos; copy.append(prefix+"<"+kind+">")
        assert set(changes)==({"object","raw_dylibs"} if role=="gcc" else {"object","raw_dylibs","resolution"})
        key=(native,role);assert key not in results
        row={"stable_argv":hashlib.sha256(b"\0".join(os.fsencode(x) for x in copy)+b"\0").hexdigest(),
             "roles":changes,"argc":len(args)}
        if role=="stock-wild":
            x=event["temporary"]; assert x["raw_dylibs"]==[] and x["resolution_len"]==0
            row["temporary_contents"]=x
        results[key]=row
    assert len(results)==150
    return [{"target":k[0],"tool":k[1],**v} for k,v in sorted(results.items())]
