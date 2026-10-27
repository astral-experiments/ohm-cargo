"""Audit the private-doc cutoff, the parser win, all fresh repeats and ELF/CLI parity from raw receipts."""
import argparse, csv, json
from collections import Counter
from pathlib import Path
cli=argparse.ArgumentParser(description=__doc__)
cli.add_argument('base',type=Path)
cli.add_argument('tag')
args=cli.parse_args()
def read(p): return json.loads(p.read_bytes())
summary={}
valid_counts={'doc-build':(2,3),'doc-test':(4,19),'parser-build':(35,8),'parser-test':(93,67)}
for endpoint,(parent_full,link_count) in valid_counts.items():
 where=args.base/('pairs-'+args.tag+'-'+endpoint)
 check=args.base/('clean-'+args.tag+'-'+endpoint)
 assert read(where/'complete.json')['source_clean'] and read(check/'complete.json')['source_clean']
 item={'traces':{},'samples':len(list(csv.DictReader((where/'observations.csv').open()))),'outputs':{}}
 assert item['samples']==24
 cold=read(check/'candidate-cold/receipt.json')
 cold_elf=read(check/'candidate-cold/sections.json')
 assert len(cold_elf)==(15 if endpoint.endswith('build') else 110)
 for who in ('parent','candidate'):
  start=read(where/(who+'-verify-edit/receipt.json'))
  end=read(where/(who+'-verify-final-edit/receipt.json'))
  counts=start['processes']
  assert counts==end['processes'] and start['crates']==end['crates'] and counts['wild']==link_count, (endpoint,who,counts,end['processes'])
  assert [start[k] for k in ('roster_sha','parser_diagnostics','dataclass')]==[cold[k] for k in ('roster_sha','parser_diagnostics','dataclass')]
  assert start['compiler_messages']==end['compiler_messages']
  item['traces'][who]=counts
  for path in sorted(where.glob(who+'*fresh*/receipt.json')):
   repeated=read(path)
   assert repeated['fresh']==(501 if endpoint.endswith('build') else 619) and repeated['dirty']==[]
  for label in ('verify-noop','final-noop'):
   noop=read(where/(who+'-'+label)/'receipt.json')
   assert not noop['dirty'] and not any(noop['processes'].values()), (endpoint,who,label,noop['processes'])
  if who=='candidate':
   assert counts['rustc_full'] <= parent_full if endpoint.startswith('doc') else counts['rustc_full'] < parent_full
   assert start['compiler_messages']==cold['compiler_messages']
   for label in ('verify-edit','verify-final-edit'):
    warm=read(where/(who+'-'+label)/'sections.json')
    assert warm.keys()==cold_elf.keys()
    changes={}
    for path in warm:
     a,b=warm[path],cold_elf[path]
     if a['raw_sha256']==b['raw_sha256']: continue
     diff={}
     for name in sorted(a['sections'].keys()|b['sections'].keys()):
      x=a['sections'].get(name,{});y=b['sections'].get(name,{})
      if x!=y:diff[name]=[f for f in sorted(x.keys()|y.keys()) if x.get(f)!=y.get(f)]
     # The prior Wild warm/cold control occasionally varied these two ELF fields.
     # An unexplained difference requires investigating that binary before publishing.
     assert diff and all(name in {'.note.gnu.build-id','.rodata'} for name in diff), (endpoint,path,diff)
     assert diff.get('.note.gnu.build-id',['digest'])==['digest'] and diff.get('.rodata',['entsize'])==['entsize'], (endpoint,path,diff)
     changes[path]=diff
    item['outputs'][label]=dict(total=len(warm),byte_identical=len(warm)-len(changes),differing_sections=changes)
  else:
   assert counts['rustc_full']==(11 if endpoint=='doc-build' else 26 if endpoint=='doc-test' else parent_full)
 summary[endpoint]=item
print(json.dumps(summary,indent=2,sort_keys=True))
