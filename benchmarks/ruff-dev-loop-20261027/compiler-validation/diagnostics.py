"""Keep complete rustc messages and account for placement of one spanless deduplicated lint note."""
from collections import Counter
import hashlib,json
NOTE='`#[warn(mismatched_lifetime_syntaxes)]` on by default'
def stable(obj):return json.dumps(obj,sort_keys=True,separators=(',',':'))
def digest(obj):return hashlib.sha256(stable(obj).encode()).hexdigest()
def diagnose(ds):
    primary=[];notes=[];locations=[]
    for original in ds:
        d=json.loads(json.dumps(original));msg=d['message']
        selected=[c for c in msg['children'] if c['level']=='note' and c['message']==NOTE]
        if selected:
            assert msg['code']['code']=='mismatched_lifetime_syntaxes' and len(selected)==1
            s=selected[0];assert not s['spans'] and not s['children'] and s.get('code') is None
            msg['children'].remove(s)
            for c in selected:notes.append(stable([d['package_id'],d['target'],msg['code'],c]))
            lines=msg['rendered'].splitlines(keepends=True);removed=[line for line in lines if line.strip()=='= note: '+NOTE]
            assert len(removed)==1,removed;lines.remove(removed[0]);msg['rendered']=''.join(lines)
            spans=msg['spans'];locations.append([d['target']['name'],spans[0]['file_name'],spans[0]['line_start']])
        primary.append(stable(d))
    return {'full_raw_messages_sha256':digest(sorted(stable(d) for d in ds)),'messages_and_all_notes_sha256':digest([sorted(primary),sorted(notes)]),'spanless_note_count':len(notes),'spanless_note_locations':sorted(locations)}
