"""Compare the complete native Cargo roster across the two known release namespaces."""
import json
from pathlib import Path
import re

from common import TARGET, need
from witness import as_digest

SCOPES = {'B':'v2-c95b8d54c8a62c02-all-native-all', 'C':'v2-8b4edd970c9a0df5-all-native-all'}
PREFIX = str(TARGET/'debug/build/workspaces/2a0346c599559020') + '/'
KEYS = ('package_id','manifest_path','target','profile','features','filenames','executable')

def release_output_roster(rows, arm):
    canonical=[]
    replaced=0
    for row in rows:
        if row.get('reason') != 'compiler-artifact':
            continue
        values={k:row[k] for k in KEYS}
        paths=[]
        for path in [*values['filenames'],values['executable']]:
            if path is None:
                paths.append(None)
                continue
            if path.startswith(PREFIX):
                scope,sep,rest=path[len(PREFIX):].partition('/')
                need(sep=='/' and scope==SCOPES[arm] and bool(rest),('unexpected physical output namespace',arm,path))
                path=PREFIX+'<registered-compiler-release>/'+rest
                replaced+=1
            need(not re.search(r'/v2-[0-9a-f]{16}-all-native-all/',path),'unbound toolchain namespace in an output')
            paths.append(path)
        values['filenames']=paths[:-1]
        values['executable']=paths[-1]
        canonical.append(json.dumps(values,sort_keys=True))
    need(replaced>0 and canonical,('no release paths',arm))
    return {'sha256':as_digest(sorted(canonical)),'units':len(canonical),'mapped_output_path_count':replaced}
