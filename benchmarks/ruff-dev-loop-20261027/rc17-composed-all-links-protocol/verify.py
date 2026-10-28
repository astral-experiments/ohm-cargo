"""Independently read the actual native exec/status records and retained raw ELFs."""
import ast
import collections
import json
import mmap
import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wild import R, STOCK, WILD, digest, read, sha, write
from view import phase_check
from worker import F, G, HIST, K, NREF, PHASES, SOURCE, SRC, W, load, original, relative, role_kind


def ref(path):
    assert path.resolve().is_relative_to(R.resolve()) and path.is_file()
    return {'file':str(path.relative_to(R)), 'sha256':sha(path)}


def process(tr, pid, argv):
    """Compare every stock execve operand and the actual child's successful exit."""
    p=tr/('exec.'+str(pid))
    lines=p.read_bytes().splitlines()
    successes=[]
    for raw in lines:
        m=re.match(rb'^execve\(("(?:[^"\\]|\\.)*"),\s*(\[.*\]),\s*(?:0x[0-9a-f]+|NULL).*?\)\s+= 0$',raw)
        if m is not None:successes.append((ast.literal_eval(m[1].decode()), ast.literal_eval(m[2].decode())))
    assert successes==[(str(STOCK),argv)],(p,len(successes),argv[:2])
    assert re.search(rb'\+\+\+ exited with 0 \+\+\+',lines[-1]),p
    return sha(p)


def body_info(path):
    """Use the registered ELF verifier plus independent hashes for each exact unmasked range."""
    given=load(G/'elf.py').fingerprint(path)
    with path.open('rb') as fd,mmap.mmap(fd.fileno(),0,access=mmap.ACCESS_READ) as b:
        section,=struct.unpack_from('<Q',b,40)
        stride,num,st=struct.unpack_from('<HHH',b,58);assert stride==64
        header=[struct.unpack_from('<IIQQQQIIQQ',b,section+i*stride) for i in range(num)]
        names=header[st]
        raw={}
        for i,h in enumerate(header):
            off=names[4]+h[0];name=b[off:b.find(b'\0',off)].decode('ascii')
            if name=='.rodata':
                where=section+i*stride+56;raw['rodata']=[where,b[where:where+8].hex()]
            elif name=='.note.gnu.build-id':
                where=h[4]+16;raw['build_id']=[where,b[where:where+32].hex()]
        assert int.from_bytes(bytes.fromhex(raw['rodata'][1]),'little')==given['rodata_entsize']
        assert raw['build_id'][1]==given['build_id'] and len(b)==given['bytes']
        start=0;ranges=[]
        for off,hexval in sorted(raw.values()):
            ranges.append([start,off,__import__('hashlib').sha256(memoryview(b)[start:off]).hexdigest()])
            start=off+len(bytes.fromhex(hexval))
        ranges.append([start,len(b),__import__('hashlib').sha256(memoryview(b)[start:]).hexdigest()])
    return {**given,'ranges':ranges,'fields':raw,'sha256':sha(path)}


def verify():
    n=load(K/'ruff_worker.py')
    historical=original();assert historical==read(R/'historical.json')
    fresh={};registry={};by_target=collections.defaultdict(dict);all_bodies={};all_fields={};stock_jobs=0
    failure=read(SOURCE/'failed-native-fields.json')['fields']
    extras=['failure-1','failure-2']
    native_anchors={};past_hashes=collections.defaultdict(set)
    for phase in PHASES:
        for target,raw in read(W/phase/'products.json')['native'].items():past_hashes[relative(target)].add(raw)
    for phase in [*extras,*PHASES]:
        d=R/'commands'/phase;jobs=n.trace_jobs(d/'trace');assert jobs==read(d/'physical.json')
        native=[j for j in jobs if j['kind']=='wild']; captures=list((R/'captures'/phase).iterdir())
        assert len(captures)==len(native) and all(j['exit']==0 for j in jobs)
        by_pid={int(j['pid'][5:]):j for j in native}; assert len(by_pid)==len(native)
        keyrows=[];index=collections.Counter();pids=set()
        for cube in sorted(captures,key=lambda f:int(f.name)):
            raw=read(cube/'capture.json');j=by_pid[int(cube.name)]
            assert raw['pid']==int(cube.name) and raw['wild_sha256']==WILD
            argv=read(cube/'raw-argv.json')
            assert argv==j['argv'] and j['target']==raw['target'] and raw['argv_sha256']==digest(argv)
            target=relative(raw['target']);index[target]+=1
            assert raw['default_exit']==0 and raw['literal_bytes_rechecked']
            # Each genuinely observed occurrence gets its own complete sweep and exact
            # transient argument spelling. No input-family classifier is used.
            inputs=read(cube/'positive-inputs.json')
            assert digest(inputs)==raw['inputs_sha256'] and raw['input_names']==len(inputs)
            assert all(len(v['sha256'])==64 and v['bytes']>=0 for v in inputs.values())
            assert all(Path(v['path']).is_absolute() for v in inputs.values())
            assert raw['input_bytes']==sum(x['bytes'] for x in inputs.values())
            assert raw['special_inputs']['symbols_sha256']==inputs[raw['special_inputs']['symbols']]['sha256']
            recipe=digest([phase,raw['pid'],raw['argv_sha256'],raw['inputs_sha256']])
            assert recipe not in by_target[target]
            observed=raw['raw_sha256']
            paths={};widths=[];traces={}
            for row in raw['widths']:
                width=row['width'];plain=[*argv,'--threads='+str(width)]
                dep=cube/(str(width)+'.d');reported=[*plain,'--dependency-file='+str(dep)]
                assert sha(dep)==row['dependency_receipt']
                assert digest(plain)==row['plain_argv_sha256'] and digest(reported)==row['reported_argv_sha256']
                names=__import__('wild').dep_names(dep,Path(raw['target']));assert names<=set(inputs)
                assert row['plain_exit']==row['depfile_exit']==0 and row['plain_sha256']==row['depfile_sha256']
                h=row['plain_sha256'];body=R/'bodies'/h;paths[h]=str(body.relative_to(R))
                if h not in all_bodies:
                    info=body_info(body);assert info['sha256']==h;all_bodies[h]=info
                q=all_bodies[h]
                anchor=all_fields.setdefault(target,(q['normalized'],q['bytes'],q['ranges']))
                assert anchor==(q['normalized'],q['bytes'],q['ranges'])
                for key,user_argv in [('plain_pid',plain),('depfile_pid',reported)]:
                    pid=row[key];assert pid not in pids;pids.add(pid)
                    traces[str(pid)]=process(d/'trace',pid,user_argv)
                widths.append({k:row[k] for k in ('width','plain_sha256','depfile_sha256','plain_exit','depfile_exit')})
            assert sorted(i['width'] for i in widths)==list(range(1,17)) and observed in paths
            pid=raw['default_pid'];assert pid not in pids;pids.add(pid)
            traces[str(pid)]=process(d/'trace',pid,argv);stock_jobs+=33
            row={'target':target, 'kind':role_kind(jobs,j['target']), 'exec_sha256':j['raw'],'argv_sha256':digest(argv),
                 'recipe':recipe,'raw_sha256':observed,'capture':ref(cube/'capture.json'),'occurrence':index[target],
                 'exit':0,'wild_sha256':WILD}
            keyrows.append(row)
            by_target[target][recipe]={'phase':phase,'occurrence':index[target],'inputs_sha256':raw['inputs_sha256'],
                        'stable_argv_sha256':raw['argv_sha256'],'widths':widths,'bodies':paths,
                        'raw_input_file':ref(cube/'positive-inputs.json'),'raw_argv_file':ref(cube/'raw-argv.json'),
                        'stock_trace_set_sha256':digest(traces)}
        if phase in PHASES:
            old=historical[phase];count=lambda rows:collections.Counter((j['target'],j['kind']) for j in rows)
            assert count(old)==count(keyrows)
            post=read(d/'products.json');before=read(W/phase/'products.json')
            assert post['roster']==before['roster'] and post['fresh']==563
            if not phase.startswith('seed'):
                registry[phase]=ref(d/'registry-native.json');assert read(d/'registry-native.json')==read(W/phase/'registry-native.json')
            for key,h in post['native'].items():
                target=relative(key)
                if target in index:assert h in {j['raw_sha256'] for j in keyrows if j['target']==target}
                else:assert h==before['native'][key]
            fresh[phase]=keyrows
        else:
            assert len(keyrows)==1
            target=keyrows[0]['target'];spec=by_target[target][keyrows[0]['recipe']]
            assert failure[Path(target).name]['failed-unchanged']['sha256'] in spec['bodies']
    assert len(by_target)==50 and stock_jobs==299*33 and sum(len(i) for i in historical.values())==297
    totals={};term={}
    prior=read(W.parent/'early-scheduler-wall-admission-v2.json')['native']['allowed']
    for target,recipes in sorted(by_target.items()):
        relative_samples={h for rec in recipes.values() for h in rec['bodies']}
        assert past_hashes[target]<=relative_samples
        # Re-read both preserved first states and both real later states, using the true
        # original paths; this also checks their bytes outside the two ELF fields.
        for role in ('observer','composed'):
            q=W/('selected-'+role)
            key=str(n.can/target);snapshot=read(q/'preserved-native.json')[key]
            later=n.actual(key,W/('state-'+role))
            for file in [q/'native-files'/snapshot['file'],later]:
                info=body_info(file)
                assert info['sha256'] in relative_samples
                assert all_fields[target]==(info['normalized'],info['bytes'],info['ranges'])
        expected={phase:read(W/phase/'products.json')['native'][str(n.can/target)] for phase in PHASES
                  if any(j['target']==target for j in historical[phase])}
        old_fail=failure.get(Path(target).name,{}).get('failed-unchanged',{}).get('sha256')
        ordinary,extra=phase_check(recipes,target,expected,prior[str(n.can/target)],old_fail)
        d=R/'targets'/Path(target).name;d.mkdir()
        result={'target':target,'recipes':recipes,'exact_hashes':sorted(relative_samples),
                'storage':'one raw ELF per SHA-256','capture_count':len(recipes),
                'fields':{h:all_bodies[h] for h in sorted(relative_samples)}}
        write(d/'all-widths.json',result)
        totals[target]={'evidence':ref(d/'all-widths.json'),'recipes':ordinary}
        term[target]={'qualified_occurrences':len(recipes),'allowed_raw':sorted(relative_samples),
                      'recipe_receipt':ref(d/'all-widths.json'),'supplemental_reconstructions':sorted(extra)}
    write(R/'terminal.json',term)
    summary={'accepted':True,'phase_occurrences':{t:len(a) for t,a in fresh.items()},'workspace_linked_targets':50,
             'all_untimed_stock_wild_processes':stock_jobs,'explicit_reported_and_plain':299*32,
             'ordinary_stock_controls':299,'raw_bodies':len(all_bodies),'registry':registry,
             'admitted_or_failed_states_modified':0,'unrecovered_prior_transient_input_bytes':'unknown'}
    write(R/'independent.json',summary)
    view={'schema':1,'native_ref':NREF,'wild_source':SRC,'wild_sha256':WILD,'cpu':list(range(16)),'jobs':8,
          'widths':list(range(1,17)),'historical':historical,'fresh':fresh,'targets':totals,'terminal':ref(R/'terminal.json'),
          'independent_verification':ref(R/'independent.json'),'historical_transient_limitation':
          'Original temp symbols.o, GCC resolution path, and initial overwritten 139 e2e codegen objects were not captured contemporaneously. Fresh exact argv and input bytes are per occurrence.'}
    write(R/'wall-view.json',view)
    print(json.dumps(summary,sort_keys=True))


if __name__=='__main__':
    verify()
