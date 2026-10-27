from pathlib import Path
from collections import Counter
import json,subprocess
from ids import sip13_low
def keys(stable):
 sid=int(stable,16);mod=sip13_low(sid.to_bytes(8,'little')+bytes([5])+b'lexer\xff'+bytes(4));lex=sip13_low(mod.to_bytes(8,'little')+bytes([6])+b'lex\xff'+bytes(4))
 return [stable,f'{lex:016x}',f'{mod:016x}']
def scan(binpath,graph,sk,kinds):
 r=subprocess.run([str(binpath),str(graph),*keys(sk)],capture_output=True,text=True)
 if r.returncode:return {'failure':r.returncode,'stderr':r.stderr[-320:]}
 out={'named':{},'direct_metadata_inputs':[]};labels=['_','lex','lexer','root']
 for line in r.stdout.splitlines():
  v=line.split()
  if v[0]=='t':
   out.update(nodes=int(v[1]),edges=int(v[2]),parser_keys=int(v[3]),focus_key_count=int(v[4]),metadata_node=bool(int(v[5])))
  elif v[0]=='q':
   _,slot,kind,fp=v
   label=labels[int(slot)];k=kinds[int(kind)];values=out['named'].setdefault(label,{});assert k not in values;values[k]=fp
  elif v[0]=='m':out['direct_metadata_inputs'].append([labels[int(v[1])],kinds[int(v[2])]])
 assert 'nodes'in out;return out
