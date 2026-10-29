"""Offline verifier for the staged native provider. Only the portable strace, Cargo JSON and program output determine the reconstructed jobs."""
import argparse
import ast
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import tarfile
import struct

import importlib.util

ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("packet_inputs",ROOT/"collect.py")
collection=importlib.util.module_from_spec(spec);spec.loader.exec_module(collection)
CASES,inputs=collection.CASES,collection.inputs
def digest(data):return hashlib.sha256(data).hexdigest()
def dump(data):return (json.dumps(data,sort_keys=True,indent=1)+'\n').encode()
def baseline(source):
    return [r for l in source.splitlines() if l.startswith(b'{') for r in [json.loads(l)]]
def args_value(argv,opt):
    return argv[argv.index(opt)+1] if opt in argv else None
def read_exec(data):
    executions=[]
    for line in data.decode().splitlines():
        # The input stream has complete records for each successful execve; disallow any split which would silently undercount.
        assert '<unfinished ...>' not in line and ' resumed>' not in line
        if not re.search(r'\)\s+= 0$',line):continue
        m=re.fullmatch(r'(\d+)\s+execve\(("(?:\\.|[^"\\])*"), (\[.*\]), (.*)\)\s+= 0',line)
        assert m,line[:95]
        image, argv=ast.literal_eval(m[2]),ast.literal_eval(m[3])
        assert isinstance(argv,list) and all(isinstance(x,str) for x in argv) and argv
        executions.append((int(m[1]),image,argv))
    return executions
def inspect_job(read,case,phase,stage,row):
    prefix='/'.join((case,phase,stage))+'/'
    data=read[prefix+'exec.log'];events=read_exec(data)
    text=read[prefix+'stdout'];msgs=baseline(text)
    scripts=[x for x in msgs if x['reason']=='build-script-executed']
    end=[x['success'] for x in msgs if x['reason']=='build-finished']
    expected=stage=='prepare' or row['cargo']==0
    assert len(scripts)==1 and end==[expected] and msgs[-1]['reason']=='build-finished',(case,phase,stage)
    out=scripts[0]['out_dir'];links=scripts[0]['linked_paths']
    assert len(links)==2 and all(s.startswith('native=') for s in links) and scripts[0]['linked_libs']==[]
    early,fallback=[s.removeprefix('native=') for s in links]
    assert [PurePosixPath(p).name for p in (early,fallback)]==['early','fallback']
    is_ext=CASES[case][1]=='external'
    assert [str(PurePosixPath(p).parent) for p in (early,fallback)]==[('/fixture/project/provider/prebuilt' if is_ext else out)]*2
    assert out.startswith('/fixture/') and not out.endswith('/prebuilt')
    artifacts={};diags=[];tests=[];scripts_elfs=set()
    for j in msgs:
        if j['reason']=='compiler-artifact':
            t=j['target']['name'];artifacts[t]=j['fresh']
            if t=='probe':
                assert j['target']['kind']==['test'] and j['executable'] is not None
                tests.append(j['executable'])
            if j['target']['kind']==['custom-build']:
                scripts_elfs.update(j['filenames'])
        if j['reason']=='compiler-message' and j['message']['level']=='error':
            diag=j['message']
            children='\n'.join(x['message'] for x in diag['children'])
            diags.append({'message':diag['message'],'early_archive':early+'/libchoice.a' in children,
                          'malformation':any(s in children for s in ('unknown directive','file format not recognized','Failed to process')),
                          'diagnostic_sha256':digest(dump(diag))})
    if stage=='test':
        assert (len(tests)==1)==expected
        if expected:assert PurePosixPath(tests[0]).name==row['elf'] and artifacts['probe'] is row['fresh']
        else:assert diags and any(d['early_archive'] and d['malformation'] and 'linking with' in d['message'] for d in diags),(case,phase,diags)
    else:assert not tests and not diags
    compiler=[];dispatch=[];terminals=[];script_execs=[];archives=[];c_source=[];cargo=[];other=Counter()
    for _,image,a in events:
        name=PurePosixPath(image).name
        if name=='cargo':
            cargo.append(a);continue
        if name=='rustc':
            assert image in ('/sdk/bin/rustc','/fixture/rustup/toolchains/ohm/bin/rustc'),image
            k=args_value(a,'--crate-name')
            link_only=any(x=='-Zlink-only' or x=='-Z' and i+1<len(a) and a[i+1]=='link-only' for i,x in enumerate(a))
            is_query=k in (None,'___')
            assert not link_only or (not is_query and any(x.endswith('.rlink') for x in a))
            compiler.append({'target':k,'kind':'query' if is_query else 'link-only' if link_only else 'full',
                             'argv_sha256':digest(dump(a))})
            continue
        if name in ('ld.bfd','ld','ld.lld','rust-lld'):
            output=args_value(a,'-o');assert output
            role='probe' if re.fullmatch(r'probe-[0-9a-f]{16}',PurePosixPath(output).name) else 'build-script'
            if role=='build-script':assert re.fullmatch(r'build[_-]script[_-]build(?:-[0-9a-f]{16})?',PurePosixPath(output).name)
            if image.endswith('/wild-ld/ld.bfd'):kind='Wild'
            elif image=='/usr/bin/ld':kind='GNU ld'
            elif image.endswith('/gcc-ld/ld.lld'):kind='LLD dispatcher'
            else:assert image.endswith('/bin/rust-lld');kind='rust-lld'
            if role=='probe':
                search=[a[i+1] if x=='-L' else x[2:] for i,x in enumerate(a) if x.startswith('-L')]
                assert early in search and fallback in search and search.index(early)<search.index(fallback) and '-lchoice' in a,(case,phase,kind)
            record={'kind':kind,'image':image,'output':output,'role':role,'argv_sha256':digest(dump(a))}
            (dispatch if kind=='LLD dispatcher' else terminals).append(record)
            continue
        if image in scripts_elfs:
            assert len(a)==1 and re.fullmatch(r'build[_-]script[_-]build(?:-[0-9a-f]{16})?',name)
            script_execs.append(image);continue
        if re.fullmatch(r'build[_-]script[_-]build(?:-[0-9a-f]{16})?',name):
            # Cargo may execute the original physical path and report a hard-linked output.
            assert len(a)==1 and any(PurePosixPath(x).name==name for x in scripts_elfs),(case,phase,image,scripts_elfs)
            script_execs.append(image);continue
        if name=='ar':
            assert a[1:]==['crs','libchoice.a','choice.o'];archives.append(a[1:]);continue
        if name=='cc' and a[1:]==['-c','choice.c','-o','choice.o']:c_source.append(a[1:]);continue
        other[name]+=1
    assert len(cargo)==2 and cargo[0][1]=='+ohm' and ('-Zohm-defaults=no' in cargo[1]) is CASES[case][2]
    cargo_args=[s for s in cargo[1][1:] if s!='-Zohm-defaults=no']
    assert cargo_args==(['build','-p',CASES[case][1],'--lib','-vv','--message-format=json'] if stage=='prepare' else ['test','-p','app','--test','probe','--no-run','-vv','--message-format=json'])
    if dispatch or any(r['kind']=='rust-lld' for r in terminals):
        assert [(r['output'],r['role']) for r in dispatch]==[(r['output'],r['role']) for r in terminals if r['kind']=='rust-lld']
    if is_ext:assert not archives and not c_source
    assert len(archives)==len(c_source) and len(script_execs)<=1
    if not expected:assert any(l['role']=='probe' for l in terminals)
    original_lines=[l.decode() for l in text.splitlines() if l.startswith(b'[provider ')]
    if script_execs:assert any('cargo:rustc-link-search=native='+early in l for l in original_lines) and any('cargo:rustc-link-search=native='+fallback in l for l in original_lines)
    return {'cargo_argv':cargo_args,'build_finished':end[0],'reported_artifacts':artifacts,'declared_out_dir':out,
            'native_search':[early,fallback],'diagnostics':diags,'rustc':compiler,'probe_links':sum(r['role']=='probe' for r in terminals),
            'linkers':terminals,'linker_dispatchers':dispatch,'script_runs':len(script_execs),'ar_calls':len(archives),
            'cc_compile_choice':len(c_source),'other_executions':other,'all_successful_execs':len(events)}
def choice_return(archive):
    # These two frozen x86-64 ELF objects each export one ordinary C function.
    # Resolve that symbol from the member's actual ELF symbol table before reading its instruction bytes.
    assert archive[:8]==b'!<arch>\n';offset=8;objects=[]
    while offset<len(archive):
        h=archive[offset:offset+60];assert len(h)==60 and h[58:60]==b'`\n'
        size=int(h[48:58]);body=archive[offset+60:offset+60+size];assert len(body)==size
        if h[:16].rstrip()==b'choice.o/':objects.append(body)
        offset+=60+size+(size%2)
    assert offset==len(archive) and len(objects)==1
    b=objects[0];assert b[:6]==b'\x7fELF\x02\x01' and struct.unpack_from('<HH',b,16)==(1,62)
    start=struct.unpack_from('<Q',b,40)[0];sz,count=struct.unpack_from('<HH',b,58);assert sz==64
    sections=[struct.unpack_from('<IIQQQQIIQQ',b,start+i*sz) for i in range(count)]
    symtabs=[s for s in sections if s[1]==2];assert len(symtabs)==1
    tab=symtabs[0];strings=sections[tab[6]];names=b[strings[4]:strings[4]+strings[5]];matches=[]
    assert tab[9]==24
    for i in range(0,tab[5],24):
        name,kind,_,section,address,length=struct.unpack_from('<IBBHQQ',b,tab[4]+i)
        if names[name:].split(b'\0',1)[0]==b'choice':
            assert kind==0x12 and 0<section<len(sections)
            text=sections[section];assert text[2]&4 and address+length<=text[5]
            matches.append(b[text[4]+address:text[4]+address+length])
    assert len(matches)==1
    code=matches[0].removeprefix(bytes.fromhex('f30f1efa'))
    assert len(code)==11 and code[:5]==bytes.fromhex('554889e5b8') and code[-2:]==bytes.fromhex('5dc3')
    return int.from_bytes(code[5:9],'little')
def audit(stream_mutation=None):
    with gzip.open(ROOT/'custody.json.gz','rt') as f: info=json.load(f)
    assert set(info['cases'])==set(CASES) and info['schema']==1
    with tarfile.open(ROOT/'streams.tar.gz','r:gz') as t:
        read={}
        for m in t:
            assert m.isfile() and not m.name.startswith('/') and '..' not in PurePosixPath(m.name).parts and m.name not in read
            data=t.extractfile(m).read()
            read[m.name]=data
    original=info['original_streams']
    assert set(read)==set(original)
    for key,data in read.items():
        ref=original[key]
        assert ref['portable_bytes']==len(data) and ref['portable_sha256']==digest(data) and re.fullmatch('[a-f0-9]{64}',ref['sha256'])
    if stream_mutation is not None:stream_mutation(read)
    assert info['portable_runner']==digest((ROOT/'reproduce.py').read_bytes())
    base,external=inputs((ROOT/'reproduce.py').read_bytes())
    out={};tot=Counter();variants=Counter();elf_values={}
    for label,(arm,provider,off,only,empty) in sorted(CASES.items()):
        case=info['cases'][label];assert [case[x] for x in ('subject','provider','defaults_off','only_native_edit','cold')]==[arm,provider,off,only,empty]
        res=json.loads(read[label+'/result.json']);subject=info['subjects'][arm]
        assert [res[k] for k in ('cargo','rustc')]==[subject['images'][k]['sha256'] for k in ('cargo','rustc')]
        assert res['defaults_off'] is off
        hist={};groups=[]
        for row in res['rows']:
            name=row['phase'];state=row['state'];jobs={}
            source=base.copy()
            if provider=='external':source['provider/build.rs']=external;del source['provider/state']
            else:source['provider/state']=state+'\n'
            value=1 if only else (2 if state=='valid' else 1)
            source['app/src/lib.rs']=f'pub fn value() -> i32 {{ middle::base() + {value} }}\n'
            assert row['sources']=={k:digest(v.encode()) for k,v in source.items()}
            for key,h in row['outputs'].items():assert original['/'.join((label,name,'test',key))]['sha256']==h
            for stage in ('prepare','test'):
                prefix='/'.join((label,name,stage))+'/'
                if prefix+'stdout' not in read:continue
                jobs[stage]=inspect_job(read,label,name,stage,row)
                tot[stage+'_commands']+=1;tot['successful_execves']+=jobs[stage]['all_successful_execs']
                tot['probe_links']+=jobs[stage]['probe_links'];tot['script_runs']+=jobs[stage]['script_runs'];tot['ar_calls']+=jobs[stage]['ar_calls']
            prep='prepare' in jobs
            assert prep==(provider in ('app','provider') and name in ('declared-valid','declared-malformed','restored')),(label,name,prep)
            if prep:
                assert jobs['prepare']['declared_out_dir']==jobs['test']['declared_out_dir'] and jobs['prepare']['native_search']==jobs['test']['native_search']
                identity=case['staged_path_identity'][name]
                assert all(len(set(identity[k]))==3 and all(re.fullmatch('[0-9a-f]{64}',h) for h in identity[k]) for k in ('original_sha256','resolved_sha256'))
                assert jobs['prepare']['script_runs']==1 and jobs['prepare']['ar_calls']==(2 if state=='valid' else 1)
                assert jobs['test']['script_runs']==0
            test=jobs['test'];rc=row['cargo'];assert rc in (0,101) and test['build_finished']==(rc==0)
            actual=None
            if rc==0:
                native=read['/'.join((label,name,'test','native.stdout'))]
                matches=re.findall(rb'(?m)^native-choice=([0-9]+)$',native)
                assert len(matches)==1 and b'1 passed; 0 failed;' in native and b'test prints_choice ... ok' in native
                assert not read['/'.join((label,name,'test','native.stderr'))] and row['native_exit']==0
                actual=int(matches[0]);assert actual==row['value'] and re.fullmatch('[0-9a-f]{64}',row['hash'])
                digest_value=elf_values.setdefault(row['hash'],actual);assert digest_value==actual
                tot['successful_programs']+=1
            else:assert 'value' not in row and test['diagnostics']
            hist[name]={'state':state,'app_addend_verified_from_source':value,'cargo_exit':rc,'native_choice':actual,
                        'elf_sha256':row.get('hash'),'test_fresh':test['reported_artifacts'].get('probe'),'commands':jobs}
            groups.append((rc,actual));tot['phase_count']+=1;tot['diagnostic_failures']+=rc!=0
        if empty:expect=[(0,29)] if empty=='valid' else [(101,None)]
        elif ((provider=='provider' and not off and not only) or (provider=='external' and (not off or only))):
            expect=[(0,17)]*7
            assert len({x['elf_sha256'] for x in hist.values()})==1
            for name in ('declared-valid','repeat-valid','declared-malformed','repeat-malformed'):
                assert hist[name]['commands']['test']['probe_links']==0
                assert all(r['target']!='probe' for r in hist[name]['commands']['test']['rustc'])
            if not only:
                for name in ('declared-valid','declared-malformed'):
                    c=hist[name]['commands']['test'];assert c['reported_artifacts']['probe'] is False
                    assert [(r['target'],r['kind']) for r in c['rustc'] if r['kind']!='query']==[('app','full')]
        else:expect=[(0,17),(0,17),(0,29),(0,29),(101,None),(101,None),(0,17)]
        assert groups==expect,(label,groups,expect)
        seen=set()
        for role,archive in case['terminal_archives'].items():
            if archive is None:
                assert role=='early' and empty is None
                continue
            key='native-inputs/'+archive['sha256'];content=read[key]; assert digest(content)==archive['sha256'] and len(content)==archive['bytes']
            if empty=='malformed' and role=='early':assert content==b'not a valid ar archive'
            else:assert choice_return(content)==(29 if role=='early' else 17)
            seen.add(role)
        assert 'fallback' in seen
        final=res['rows'][-1]
        if final['cargo']==0:assert any(e['sha256']==final['hash'] for e in case['still_present_elf'].values())
        for k in case['still_present_elf']:
            assert PurePosixPath(k).name.startswith('probe-') and case['still_present_elf'][k]['bytes']>0
        variants['histories']+=1;out[label]=hist
    assert len(out)==22 and len(read)==742
    # The two independently empty controls used the same source bytes, command, and true provider value as their respective edited histories.
    for kind,good,bad in [('provider','staged-clean-valid-v3','staged-clean-malformed-v3'),('external','prebuilt-clean-valid-v2','prebuilt-clean-bad-v2')]:
        for label in [l for l,x in CASES.items() if x[1]==kind and not x[3] and x[4] is None]:
            original_rows={r['phase']:r for r in json.loads(read[label+'/result.json'])['rows']}
            for phase,reference in [('declared-valid',good),('declared-malformed',bad)]:
                assert original_rows[phase]['sources']==json.loads(read[reference+'/result.json'])['rows'][0]['sources']
    return {'schema':1,'counts':dict(tot),'histories':out,'unique_executed_elf_hashes_and_values':elf_values}
def selftest():
    # Mutate a copy AFTER stream custody validation. The substantive verdict checks must still reject it.
    def sub(path,old,new):
        def apply(streams):
            assert old in streams[path]
            streams[path]=streams[path].replace(old,new)
        return apply
    def erase_command(path,needle):
        def apply(streams):
            data=streams[path].splitlines(keepends=True)
            new=b''.join(line for line in data if needle not in line)
            assert len(new)<sum(map(len,data))
            streams[path]=new
        return apply
    def fake_source(streams):
        key='staged-only-native-v3/result.json';j=json.loads(streams[key])
        changed=next(r for r in j['rows'] if r['phase']=='declared-valid')
        changed['sources']['app/src/lib.rs']=digest(b'pub fn value() -> i32 { middle::base() + 2 }\n')
        streams[key]=dump(j)
    trials=[
        sub('staged-r19-v3/declared-valid/test/native.stdout',b'native-choice=17',b'native-choice=29'),
        sub('staged-provider-v3/declared-valid/prepare/stdout',b'/1522fd67d56a7a1e/out',b'/changed/out'),
        erase_command('staged-r17-off-v3/declared-malformed/test/exec.log',b'/gcc-ld/ld.lld", ['),
        erase_command('staged-provider-off-v3/declared-malformed/test/exec.log',b'execve("/usr/bin/ld", ['),
        erase_command('staged-r19-v3/declared-valid/prepare/exec.log',b'execve("/usr/bin/ar", ['),
        fake_source,
    ]
    for mutate in trials:
        applied=False
        def alter(streams):
            nonlocal applied
            mutate(streams)
            applied=True
        try:audit(alter)
        except AssertionError:
            assert applied,'the intended mutation did not reach the reconstruction'
            continue
        raise AssertionError('a mutated native/source/scheduler claim was accepted')
    return len(trials)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--seal',action='store_true');p.add_argument('--mutation-test',action='store_true')
    args=p.parse_args();r=audit()
    ledger=ROOT/'verdicts.json.gz'
    if args.seal:
        with ledger.open('wb') as dst,gzip.GzipFile(filename='',fileobj=dst,mode='wb',mtime=0) as f:f.write(dump(r))
    else:
        assert gzip.decompress(ledger.read_bytes())==dump(r),'declared ledger differs from raw-derived output'
    if args.mutation_test:print('Rejected',selftest(),'changed raw records under the independent phase and native checks.')
    print('Verified',len(r['histories']),'histories;',r['counts'])
