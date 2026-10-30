from pathlib import Path
import argparse,gzip,hashlib,json,os
def sha(path):
 with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
 a=argparse.ArgumentParser();a.add_argument('root',type=Path);a.add_argument('observations',type=Path);a.add_argument('output',type=Path);q=a.parse_args()
 with gzip.open(q.observations,'rt') as f:data=json.load(f)
 details={};store={}
 for arm,phases in data['arms'].items():
  for phase,visit in phases.items():
   d=q.root/'state'/arm/'evidence'/phase;a=json.loads((d/'complete.json').read_bytes());assert set(a['selected'])==set(visit['targets']) and sha(d/'complete.json')==visit['raw']['complete']
   for k,v in a['selected'].items():
    file=d/v['list_file'];raw=file.read_bytes();digest=hashlib.sha256(raw).hexdigest()
    assert digest==v['list_sha256']==visit['targets'][k]['list_sha256']
    if digest in store:assert store[digest].encode()==raw
    else:store[digest]=raw.decode('utf-8')
    details.setdefault(k,{})[arm+'/'+phase]=digest
 assert len(details)==50 and all(len(x)==6 and len(set(x.values()))==1 for x in details.values())
 public={'roster':details,'original_stdout_by_sha256':store}
 with q.output.open('xb') as raw,gzip.GzipFile(filename='',fileobj=raw,mode='wb',mtime=0) as out:out.write(json.dumps(public,sort_keys=True,separators=(',',':')).encode()+b'\n')
 print('complete list files',sum(map(len,details.values())),len(store),q.output.stat().st_size,sha(q.output))
if __name__=='__main__':main()
