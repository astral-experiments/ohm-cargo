"""Verify the complete observed lockfile, serializer and marker history independently."""
import argparse
import copy
import gzip
import hashlib
import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CARGO_ARGS = ['cargo', '+ohm', 'build', '-p', 'ruff_text_size', '--locked', '--offline', '--message-format=json']
PRODUCTS = [
    ['libruff_text_size.rlib', 107926, 'ca93d901b6e0be5852aa1833abe663f4bc1f57c8e8ef4d0156d1a62c1367ef59'],
    ['libruff_text_size-48f333158b244f36.rmeta', 95995, 'af8f228d9e5e76c736b54649f65b2d4089f01edc16ee615df49142e8f373f9a9'],
]
CALLER = '9fd6acb5896e86a2c59526eb0b1c63aa1b5cdd02f8fd0f50e9f7012540a2e53d'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def expectations():
    """Each row names the snapshots Cargo read and the two possible encoder outcomes."""
    rows = {}

    def add(name, reads='o', write=None, publish=None, mark=False, verdict='success', changed=False, actor=None, early=False, off=False):
        assert name not in rows
        rows[name] = (reads, write, publish, mark, verdict, changed, actor, early, off)

    for name in ('01-hydrate', '02-hit', '04-reverse-repeat', '06-restore-repeat', 'optout-restore'):
        add(name)
    for name in ('03-reverse', '05-restore', 'publish-comment-recover', 'crlf-recover', 'no-final-lf-recover'):
        add(name, 'oooo', 'oo', mark=True, changed=True)
    for mode, letter, verdict in [('stale','s','locked-stale'), ('malformed','m','malformed'), ('comment','c','success')]:
        add('publish-'+mode, 'ooo'+letter, 'oo', letter+('c' if letter=='c' else 'o'), True, changed=letter=='c', actor=mode)
        if mode=='stale':
            add('publish-stale-next', 'sss', 'so', verdict=verdict)
        else:
            add('publish-'+mode+'-next', letter, verdict=verdict)
        if mode!='comment':
            add('publish-'+mode+'-recover')
            add('decode-'+mode, 'o'+('ss' if letter=='s' else 'm'), 'so' if letter=='s' else None, verdict=verdict, actor=mode, early=True)
            add('decode-'+mode+'-static', 'sss' if letter=='s' else 'm', 'so' if letter=='s' else None, verdict=verdict)
            add('decode-'+mode+'-recover')
    for name in ('blank','blank-repeat'):
        add(name, 'bbbb', 'bo', 'bo', True)
    add('blank-recover')
    for name, letter in [('crlf','r'),('no-final-lf','n')]:
        add(name, letter*4, letter+'o', mark=True, changed=True)
        add(name+'-repeat', letter)
    for name in ('optout','optout-repeat'):
        add(name,'oo','oo',off=True)
    assert len(rows)==33
    return rows


def verify(rows, subjects, original):
    bodies = {
        'o': original,
        's': original.replace(b'name = "ruff_text_size"\nversion = "0.0.17"', b'name = "ruff_text_size"\nversion = "0.0.16"'),
        'm': b'version = [\n',
        'c': original.replace(b'version = 4\n', b'# Independent lockfile writer.\nversion = 4\n', 1),
        'b': original.replace(b'[[package]]',b'\n[[package]]',1),
        'r': original.replace(b'\n',b'\r\n'),
        'n': original.removesuffix(b'\n'),
    }
    ids = {key:sha(body) for key,body in bodies.items()}
    assert ids['o']==subjects['lock']=='c9e345325bec5ff08dbbe3916edd39ad0c3d1c7797a8c241ae32f62754e764bf'
    assert len(original)==138994 and len(tomllib.loads(original.decode())['package'])==553
    assert len(set(ids.values()))==7
    assert subjects['candidate']=='d2480173d7362899271f21aed543b24348bf5ba8ddf4696e5fed10dc58d68b9b'
    assert subjects['subject']=='24c98100d04843e60a830951f843ab40f6e60414'
    assert sha((ROOT/'candidate.patch').read_bytes())=='eab12242ee13a0618046b960978a917086f3d2d89602e8e3ef9829ee438b049d'
    plan=expectations()
    assert rows.keys()==plan.keys()
    write_pc=subjects['direct_return_sites']['write'][2:]
    publish_pc=subjects['direct_return_sites']['mark'][2:]
    for name,record in rows.items():
        reads,write,publish,mark,verdict,changed,actor,early,off=plan[name]
        assert record['argv']==CARGO_ARGS and record['early']==early and record['cache_override']==('0' if off else None)
        assert record['manifest']==subjects['manifest'][record['state']]
        assert record['verdict']==verdict and record['exit']==(0 if verdict=='success' else 101)
        assert re.fullmatch('[0-9a-f]{16}',record['before']) and re.fullmatch('[0-9a-f]{16}',record['after'])
        assert (record['before']!=record['after'])==changed
        assert record['native']==[]
        if record['exit']==0:
            assert record['artifacts']==[{'target':'ruff_text_size','kind':['lib'],'fresh':True,'package':'0.0.17','outputs':PRODUCTS}]
            assert record['oracle']==[['consumer',0,'17 29 12',CALLER]]
        else:
            assert record['artifacts']==[] and record['oracle']==[]
        files=record['open']
        assert [item['sha'] for item in files]==[ids[k] for k in reads]
        assert all(item['size']==len(bodies[k]) and item['locks']==[[5,0],[8,0]] for item,k in zip(files,reads))
        assert [item['same_initial_inode'] for item in files]==[not(actor=='malformed' and n>=(1 if early else 3)) for n in range(len(files))]
        if actor:
            letter={'stale':'s','comment':'c','malformed':'m'}[actor]
            assert record['actor']=={'mode':actor,'exclusive_acquired':True,'original':ids['o'],'changed':ids[letter], 'same_inode':actor!='malformed','same_length':actor=='stale'}
        else:
            assert record['actor'] is None
        expected_functions=[]
        if early:
            expected_functions.append(('registry_loader','a79d01',0,None))
        def pair(tag,pc,io):
            for func,key in zip(('serialize_resolve',tag),io):
                expected_functions.append((func,pc,len(bodies[key]),ids[key]))
        if write:
            pair('encoded_at_write',write_pc,write)
        if mark:
            expected_functions.append(('mark_workspace_cache','b75604',0,None))
        if publish:
            pair('encoded_at_mark',publish_pc,publish)
        index={};locks={};offset={};events=record['events']; functions=[]; mutations=0;execs=[]; previous=0
        for event in events:
            sequence,kind,*args=event
            assert sequence>previous
            previous=sequence
            if kind=='OPEN':
                fd,size=args
                assert fd not in index and len(index)<len(files)
                k=reads[len(index)]; assert size==len(bodies[k]) and fd==files[len(index)]['id']
                index[fd]=k;locks[fd]=0;offset[fd]=0
            elif kind=='FLOCK':
                fd,op,status=args;assert locks[fd] in (0,1) and op==(5 if locks[fd]==0 else 8) and status==0
                locks[fd]+=1
            elif kind=='READ':
                fd,requested,actual,digest=args;assert locks[fd]==1 and 0<=actual<=requested
                body=bodies[index[fd]]; start=offset[fd]; assert start+actual<=len(body)
                assert digest==(sha(body[start:start+actual]) if actual else None)
                offset[fd]+=actual
            elif kind=='CLOSE':
                fd,=args;assert locks[fd]==2 and offset[fd]==len(bodies[index[fd]])
                locks[fd]=3
            elif kind=='FUNCTION':
                functions.append(tuple(args))
                if args[0]=='mark_workspace_cache':assert len(index)==3 and all(v==3 for v in locks.values())
            elif kind=='CHANGED':
                assert actor and all(v==3 for v in locks.values()) and len(index)==(1 if early else 3)
                mutations+=1
            elif kind=='EXEC':
                exe,digest=args;assert re.fullmatch('[0-9a-f]{64}',digest);execs.append(exe)
            else:
                assert kind=='RESULT' and event is events[-1] and args==[record['exit']]
        assert functions==expected_functions and execs==['rustup','cargo-stack'] and mutations==bool(actor)
        assert len(index)==len(reads) and all(v==3 for v in locks.values())
    checkpoints=['01-hydrate','02-hit','03-reverse','04-reverse-repeat','05-restore','06-restore-repeat']
    for mode in ('stale','malformed','comment'):
        checkpoints.extend(['publish-'+mode,'publish-'+mode+'-next','publish-'+mode+'-recover'])
    for mode in ('stale','malformed'):
        checkpoints.extend(['decode-'+mode,'decode-'+mode+'-static','decode-'+mode+'-recover'])
    for mode in ('blank','crlf','no-final-lf'):
        checkpoints.extend([mode,mode+'-repeat',mode+'-recover'])
    checkpoints.extend(['optout','optout-repeat','optout-restore'])
    assert len(checkpoints)==len(rows) and all(rows[a]['after']==rows[b]['before'] for a,b in zip(checkpoints,checkpoints[1:]))
    assert rows[checkpoints[0]]['before']==rows[checkpoints[-1]]['after']
    assert len({rows[n]['after'] for n in ('02-hit','03-reverse','publish-comment','crlf','no-final-lf')})==5
    return '33 Cargo builds verified, 27 successful identical caller ELFs, six expected rejections, five synchronized mutations'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test',action='store_true');args=parser.parse_args()
    if (ROOT/'SHA256SUMS').is_file():
        for line in (ROOT/'SHA256SUMS').read_text().splitlines():
            digest,name=line.split('  ',1); assert Path(name).name==name and sha((ROOT/name).read_bytes())==digest
    subjects=json.loads((ROOT/'subjects.json').read_bytes());rows=json.loads(gzip.decompress((ROOT/'commands.json.gz').read_bytes()));source=gzip.decompress((ROOT/'original-lockfile.gz').read_bytes())
    print(verify(rows,subjects,source))
    if args.self_test:
        for phase,key in [('publish-comment','return'),('publish-stale','marker'),('crlf','bytes'),('03-reverse','exec')]:
            bad=copy.deepcopy(rows);row=bad[phase]
            if key=='return':row['events']=[e for e in row['events'] if e[1:3]!=['FUNCTION','encoded_at_mark']]
            elif key=='marker':row['after']='1'*16
            elif key=='bytes':next(e for e in row['events'] if e[1]=='READ' and e[-1])[-1]='0'*64
            else:row['native']=[['rustc','ruff_text_size','0'*64]]
            try:verify(bad,subjects,source)
            except AssertionError:continue
            raise ValueError('accepted corrupted '+phase)
        print('Rejected all four event, marker, input and execution mutations')

if __name__=='__main__':
    main()
