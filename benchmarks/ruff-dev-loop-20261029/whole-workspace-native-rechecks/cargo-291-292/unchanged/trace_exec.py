"""Decode real successful execve and execveat records, including split/resumed ptrace lines."""
import ast
import collections
import hashlib
import json
import re

def digest_bytes(b):
    return hashlib.sha256(b).hexdigest()

def token(s,pos,end):
    start=pos;quoted=False;escape=False;depth=0
    while pos<len(s):
        c=s[pos];pos+=1
        if quoted:
            if escape:escape=False
            elif c=="\\":escape=True
            elif c=='"':quoted=False
        elif c=='"':quoted=True
        elif c=="[":depth+=1
        elif c=="]":depth-=1
        if not quoted and depth==0 and c==end:
            return ast.literal_eval(s[start:pos]),pos
    raise ValueError("unterminated exec field")

def collect_execs(trace):
    success=collections.Counter();hashes=[];resumed=0
    for f in sorted(trace.glob("exec.*")):
        assert f.name[5:].isdigit()
        pending=None;raw=f.read_bytes();hashes.append((f.name,digest_bytes(raw)))
        for line in raw.decode().splitlines():
            if line.endswith("<unfinished ...>"):
                assert pending is None;pending=line[:line.rfind("<unfinished ...>")];continue
            if line.startswith("<... "):
                assert pending is not None
                old,sep,rest=line.partition(" resumed>")
                assert sep and old[5:]==pending.split("(",1)[0]
                line=pending+rest;pending=None;resumed+=1
            if not (line.startswith(("execve(","execveat(")) and re.search(r"=\s*0\s*$",line)):continue
            pos=line.index("(")+1
            if line.startswith("execveat("):pos=line.index(", ",pos)+2
            assert line[pos]=='"'
            path,pos=token(line,pos,'"')
            assert line[pos:pos+2]==", ";pos+=2;assert line[pos]=="["
            argv,pos=token(line,pos,"]");assert line[pos:pos+2]==", " and isinstance(argv,list)
            success[path,tuple(argv)]+=1
        assert pending is None
    assert hashes
    return success,digest_bytes(json.dumps(hashes,separators=(",",":")).encode()),len(hashes),resumed
