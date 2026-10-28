"""Rebuild the five-phase physical stock-linker census from the traced -18 source trial."""
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys
import tarfile

ARCHIVE = 'ee336c50bac854f16648f19f870d5dbe915892f9fd5c9cedb08e50ab14e2779d'
TARGET = 'e2e-27d34c779ecc8418'
PHASES = ('cold','unchanged','edited','restored','final-unchanged')
EXEC = re.compile(r'^execve\(("(?:[^"\\]|\\.)*"), (\[.*\]), (?:0x[\da-fA-F]+|NULL)')

def sha(b):return hashlib.sha256(b).hexdigest()

def parse(r):
    line=r['line']; assert line.endswith(' = 0')
    m=EXEC.match(line);assert m
    args=ast.literal_eval(m[2]);assert args and all(isinstance(a,str) for a in args)
    return args

def cef(args):
    if any('/rustlib/' in a and a.endswith('/wild-ld') for a in args): family='bundled_gcc'
    else: family='unknown'
    out=Path(args[args.index('-o')+1]); names=[a[2:] for a in args if a.startswith('-L')]; named=[a[2:] for a in args if a.startswith('-l')]
    dirsets=[n for n in ('psm','zstd-sys','tikv-jemalloc-sys')if any(n in Path(d).parts for d in names)]
    ron=[Path(a).name for a in args if Path(a).name.startswith('libron-') and a.endswith('.rlib')]
    return {'package':out.parts[-4],'file':out.name,'argc':len(args),'rlibs':sum(a.endswith('.rlib') for a in args),'ron':ron,'codegen_objects':sum(a.endswith('.rcgu.o')for a in args),'native_path_family':dirsets,'search_count':len(names),'library_names':named,'linker_driver':family,'raw_dylibs_first':names[0].endswith('/raw-dylibs'),'ltoplugin_driver':any(a=='-plugin' for a in args) and any(a.startswith('-plugin-opt=-fresolution=')for a in args),'explicit_threads':any(a.startswith('--threads')for a in args),'raw_response_or_script_option':any(a.startswith('@') or a.startswith('-T')or a.startswith('--script')for a in args)}

def arg_kind(s):
    if s.endswith('/symbols.o'):return 'rustc symbol object pathname'
    if s.startswith('-L') and s.endswith('/raw-dylibs'):return 'rustc raw-dylibs search directory'
    if s.startswith('-plugin-opt=-fresolution='):return 'GCC plugin resolution pathname'
    if s.endswith('.rcgu.o'):return 'crate codegen object pathname'
    return 'other'

def summarize(bundle):
    with bundle.open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==ARCHIVE
    raw={}
    members={'native-exec-lines.json','actual-processes.json','retained-links.json','stdout','command.json'}
    with tarfile.open(bundle,'r|xz')as t:
        for item in t:
            parts=item.name.split('/')
            if len(parts)==3 and parts[0]=='test' and parts[1]in PHASES and parts[2]in members:raw[parts[1],parts[2]]=t.extractfile(item).read()
    result={};target_argv={};unchanged_rosters={}; native_by_phase={}
    repeated_outputs={r['output'] for r in json.loads(raw['unchanged','retained-links.json'])['wild']}; assert len(repeated_outputs)==50
    for phase in PHASES:
        def read(k):return json.loads(raw[phase,k])
        messages=[json.loads(line)for line in raw[phase,'stdout'].splitlines()]; artifact=[m for m in messages if m['reason']=='compiler-artifact']; assert len(artifact)==619
        command=read('command.json'); exe=read('native-exec-lines.json'); processes=read('actual-processes.json');ret=read('retained-links.json');pids={(x['kind'],x['pid']):x for x in processes['processes']}
        native_by_phase[phase]={};output_by_pid={r['pid']:r['output'] for r in ret['wild']}
        for event in exe:
            if event['kind']!='wild':continue
            path=output_by_pid[event['pid']]
            if path not in repeated_outputs:continue
            argv=parse(event); assert argv[argv.index('-o')+1]==path and event['sha256']==sha(event['line'].encode());native_by_phase[phase].setdefault(path,[]).append(argv)
        out_row,=[k for k in ret['elf']if k.endswith('/ty_server/27d34c779ecc8418/out/'+TARGET)]; native,=[row for row in exe if row['kind']=='wild'and out_row in row['line']];a=parse(native);assert Path(a[a.index('-o')+1]).name==TARGET
        target_argv[phase]=a; el=ret['elf'][out_row];tr=next(x for x in ret['wild']if x['pid']==native['pid']);assert tr['sha256']==el['sha256']and tr['size']==el['size'];assert sha(native['line'].encode())==native['sha256']
        me={'units':len(artifact),'fresh':sum(r['fresh']for r in artifact),'cargo':command['cargo'],'rust_driver':command['driver'],'command':command['argv'],'source_state':command['source_state'],'e2e_elf':el,'e2e_wild':cef(a),'raw_e2e_wild_exec_sha256':native['sha256'],'counts':dict(Counter(r['kind']for r in exe))};result[phase]=me
        if phase not in ('unchanged','final-unchanged'):continue
        dirty=[r for r in artifact if not r['fresh']]; libs=sorted(r['target']['name']for r in dirty if r['executable']is None); assert libs==sorted(['ron','insta','insta_cmd','ty_test','mdtest','ruff_mdtest']);terminals={r['executable']:r for r in dirty if r['executable']is not None};wrows={};
        for row in exe:
            if row['kind']!='wild':continue
            args=parse(row);dest=args[args.index('-o')+1];assert dest in terminals; assert sha(row['line'].encode())==row['sha256'];facts=cef(args);assert facts['linker_driver']=='bundled_gcc' and facts['raw_dylibs_first']and facts['ltoplugin_driver']and not facts['explicit_threads']; assert facts['library_names']==['gcc_s','util','rt','pthread','m','dl','c'];assert not facts['raw_response_or_script_option']; assert row['pid'] in [s['pid']for s in ret['wild']]; assert ('wild',row['pid'])in pids; wrows[dest]=facts
        assert wrows.keys()==terminals.keys() and len(wrows)==50
        links={}
        for row in (x for x in exe if x['kind']=='link-only'):
            args=parse(row); recipe,=[x for x in args if x.endswith('.rlink')]; tgt=recipe.removesuffix('.rlink');assert tgt in wrows and tgt not in links and args[-2:]==['-Z','link-only']; links[tgt]=row
        assert links.keys()==wrows.keys();cargo_units=[(x['target']['name'],x['target']['kind'])for x in dirty];assert len(cargo_units)==56
        lone,=[x for x in exe if x['kind']=='full'];fa=parse(lone);assert fa[fa.index('--crate-name')+1]=='ron'
        me.update({'dirty_libraries':libs,'dirty_terminal_count':len(terminals),'full_rustc':['ron'],'native_directory_families':dict(Counter(','.join(r['native_path_family'])for r in wrows.values())),'with_ron':sum(bool(v['ron'])for v in wrows.values()),'without_ron':sorted([v['package']+'/'+v['file']for v in wrows.values()if not v['ron']]),'each_default_raw_dylibs_psm_system_names':True,'e2e_rustc_argv_count':len(parse(links[out_row])),'e2e_rustc_raw_exec_sha256':links[out_row]['sha256'],'target_rows':[wrows[k] for k in sorted(wrows)]})
        unchanged_rosters[phase]=sorted(wrows)
    assert unchanged_rosters['unchanged']==unchanged_rosters['final-unchanged'];changes={}
    for left,right in zip(PHASES,PHASES[1:]):
        a,b=target_argv[left],target_argv[right];changes[left+' to '+right]={'equal_length':len(a)==len(b),'mismatch_groups':dict(Counter(arg_kind(x)if arg_kind(x)==arg_kind(y)else 'different role' for x,y in zip(a,b)if x!=y)),'differing_field_positions':sum(x!=y for x,y in zip(a,b)),'same_complete_elf':result[left]['e2e_elf']==result[right]['e2e_elf']}
    fanout={}
    for left,right in [('cold','unchanged'),('restored','final-unchanged')]:
        rows={}
        for path in sorted(repeated_outputs):
            before=native_by_phase[left].get(path,[]);after=native_by_phase[right][path];assert len(after)==1
            witness=[]
            for argv in before:
                after_argv=after[0]; ds=Counter(arg_kind(x) if arg_kind(x)==arg_kind(y)else 'different role'for x,y in zip(argv,after_argv)if x!=y)
                witness.append({'before_argc':len(argv),'after_argc':len(after_argv),'mismatches':dict(sorted(ds.items()))})
            rows[Path(path).name]={'before_physical_occurrences':len(before),'comparisons_to_single_repeat':witness}
        three={'GCC plugin resolution pathname':1,'rustc raw-dylibs search directory':1,'rustc symbol object pathname':1}
        fanout[left+' to '+right]={'only_three_transient_fields':sum(bool(r['comparisons_to_single_repeat'])and all(v['before_argc']==v['after_argc']and v['mismatches']==three for v in r['comparisons_to_single_repeat']) for r in rows.values()),'earlier_occurrence_counts':dict(sorted(Counter(str(r['before_physical_occurrences']) for r in rows.values()).items())),'rows':rows}
    return {'archive_sha256':ARCHIVE,'target':TARGET,'phases':result,'e2e_argv_comparison':changes,'fanout_argv':fanout}

if __name__=='__main__':print(json.dumps(summarize(Path(sys.argv[1])),sort_keys=True,indent=2))
