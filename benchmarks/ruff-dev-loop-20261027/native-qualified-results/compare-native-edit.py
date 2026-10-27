"""Classify native ELF section changes between the original Ruff sources and each actual edit."""
from collections import Counter
import json
from pathlib import Path
import sys

root=Path(sys.argv[1]);tag=sys.argv[2]
allowed={'.note.gnu.build-id':{'digest'},'.rodata':{'entsize'}}
summary={}
for ep in ('doc-build','doc-test','parser-build','parser-test'):
    d=root/f'pairs-{tag}-{ep}'
    result={}
    for arm in ('parent','candidate'):
        def read(label):return json.loads((d/f'{arm}-{label}'/'sections.json').read_bytes())
        prior=read('before');rows={}
        for label in ('verify-edit','verify-final-edit'):
            current=read(label);assert prior.keys()==current.keys()
            names={};totals=Counter()
            for path,elf in prior.items():
                after=current[path]
                if elf['raw_sha256']==after['raw_sha256']:totals['byte-identical']+=1;continue
                changes={}
                for section in elf['sections'].keys()|after['sections'].keys():
                    x,y=elf['sections'].get(section,{}),after['sections'].get(section,{})
                    if x!=y:changes[section]=sorted(k for k in x.keys()|y.keys() if x.get(k)!=y.get(k))
                if not changes:kind='outside-recorded-sections'
                elif all(k in allowed and set(fields)<=allowed[k] for k,fields in changes.items()):kind='only-known-Wild-fields-in-sections'
                else:kind='other-section-changes'
                totals[kind]+=1
                names[path]={'classification':kind,'changed_sections':changes,'before':elf['raw_sha256'],'after':after['raw_sha256']}
            rows[label]={'total':len(prior),'counts':dict(totals),'changes':names}
        result[arm]=rows
    summary[ep]=result
print(json.dumps(summary,sort_keys=True,indent=2))
