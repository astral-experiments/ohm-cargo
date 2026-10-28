"""Inventory every argument in 150 real released-Wild execs; preserve actual spellings and typed operand roles."""
from pathlib import Path
import ast,collections,gzip,hashlib,json,re,sys
O=Path.home()/'.cache';base=O/'ohm-ron-fixed-whole-native-h4-20261028-v1';src=O/'ohm-noquery-full-native-h4-20261028-v2/protocol';sys.path.insert(0,str(src));import engine as q
st=base/'states/fixed-release-rust';root=base/'results/fixed-release-rust'
def dig(x):return hashlib.sha256(json.dumps(x,separators=(',',':'),sort_keys=True).encode()).hexdigest()
def loc(p):
    for k,o,to in [('target',q.TARGET,st/'target'),('build',q.BUILD,st/'build'),('sdk',q.FROZEN,q.FROZEN)]:
        if p.is_relative_to(o):return k,str(p.relative_to(o)),to/p.relative_to(o)
    if p.is_relative_to('/usr') or p.is_relative_to('/lib') or p.is_relative_to('/lib64'):return 'system',str(p),p
    if p.is_relative_to('/tmp'):return 'temporary',str(p),p
    return 'other',str(p),p
def typed_dir(s):
    p=Path(s);area,rel,f=loc(p)
    if area in ('target','build'):
        parts=rel.split('/');out=parts.index('out')if'out'in parts else None
        if p.name=='raw-dylibs':return area+'/unit-compiler-temp/raw-dylibs'
        if out is not None:return area+'/unit/'+parts[out-2]+'/out'+('/'+'/'.join(parts[out+1:])if len(parts)>out+1 else '')
        return area+'/'+rel
    if area=='sdk':return 'SDK/'+rel
    return rel
def actual_file(s):
    p=Path(s);area,rel,f=loc(p);v={'as_passed':rel,'root':area,'canonical_argument_sha256':dig(s)}
    if area not in ('target','build','sdk'):
        v['exists_at_export']=f.is_file()
        if f.is_file():
            v.update(resolved=str(f.resolve()),size=f.stat().st_size,sha256=q.sha(f),kind=('elf'if f.read_bytes()[:4]==b'\x7fELF'else'archive'if f.read_bytes()[:8]==b'!<arch>\n'else'opaque'))
    return v
rx=re.compile(rb'execve\(("(?:[^"\\]|\\.)*"),\s*(\[.*\]),\s*(?:0x[\da-f]+|NULL)')
def process(folder):
    pro=q.load(folder/'native-processes.json');cargo=[v for l in (folder/'stdout').read_bytes().splitlines()if(v:=json.loads(l)).get('reason')=='compiler-artifact'];table={}
    for pid,stock,out,rc,sig,exe in pro['linkers']:
        assert stock and rc==0
        line,=[l for l in (folder/'trace'/('exec.'+str(pid))).read_bytes().splitlines()if b'/ld.bfd",' in l and re.search(rb'\)\s+= 0$',l)]
        m=rx.search(line);args=ast.literal_eval(m[2].decode());dst=Path(out);name=dst.name;suf=name.rsplit('-',1)[-1];target=dst.parents[2].name
        rows=[r for r in cargo if any(str(dst)==n or suf in Path(n).parts or n.endswith('-'+suf) for n in r['filenames']+[r['executable'] or ''])]
        if len(rows)!=1:
            raw_names={name.rsplit('-',1)[0].replace('-','_')};rows=[r for r in cargo if r['executable'] and Path(r['manifest_path']).parent.name==target and r['target']['name'].replace('-','_')in raw_names and r['profile']['test']]
        assert len(rows)==1,(name,target,len(rows));meta=rows[0]
        libs=[];dirs=[];bare=[];options=[];native_meta=[];system=[];script_args=[];response=[];bound=[];i=1;mode='default'
        while i<len(args):
            a=args[i];i+=1
            if a in ['-L','--library-path'] or a.startswith('-L') or a.startswith('--library-path='):
                d=args[i] if a in ('-L','--library-path')else a[2:]if a.startswith('-L')else a.split('=',1)[1]
                i+=a in ('-L','--library-path');dirs.append({'role':typed_dir(d),'given':loc(Path(d))[:2],'canonical_argument_sha256':dig(d)});continue
            if a in ['-l','--library'] or a.startswith('-l') or a.startswith('--library='):
                lib=args[i]if a in('-l','--library')else a[2:]if a.startswith('-l')else a.split('=',1)[1];i+=a in('-l','--library');libs.append({'name':lib,'mode':mode});continue
            if a in ('-Bdynamic','-Bstatic'):
                mode=a[2:];options.append(a);continue
            if a in ('-o','--output','-dynamic-linker','--dynamic-linker','-plugin','--plugin','-m','-z','-T','--script','--version-script','--dynamic-list','--retain-symbols-file'):
                value=args[i];i+=1
                if a in ('-o','--output'):assert value==out;bound.append(a+' <target-output>')
                elif a in ('-plugin','--plugin','-dynamic-linker','--dynamic-linker'):native_meta.append([a,actual_file(value)]);bound.append(a+' '+value)
                elif a in ('-m','-z'):bound.append(a+' '+value)
                else:script_args.append([a,value]);bound.append(a+' '+value)
                continue
            if a.startswith('-plugin-opt='):
                v=a.split('=',1)[1]
                if v.startswith('-fresolution='):bound.append('-plugin-opt=-fresolution=<gcc-temporary>');native_meta.append(['plugin-resolution',{'root':'temporary','filename_digest':dig(v.split('=',1)[1])}])
                elif v.startswith('/'):native_meta.append(['plugin-option-path',actual_file(v)]);bound.append('-plugin-opt='+v)
                else:bound.append(a)
                continue
            if a.startswith('@'):response.append(a);continue
            if a.startswith('-'):
                options.append(a)
                if any(a.startswith(v) for v in ['--script=','--version-script=','--dynamic-list=','-T','--retain-symbols-file=']):script_args.append(a)
                continue
            fd=actual_file(a);fd['role']='ron-rlib'if Path(a).name=='libron-f3d684a377188226.rlib'else 'other-rlib'if a.endswith('.rlib')else 'object'if a.endswith('.o')else 'standalone-rmeta'if a.endswith('.rmeta')else 'other-literal';bare.append(fd)
            if fd['root'] not in('sdk','target','build'):system.append(fd)
        key=','.join(z['mode']+':'+z['name']for z in libs);dkey=','.join(z['role']for z in dirs)
        kv={'name':meta['target']['name'],'package':Path(meta['manifest_path']).parent.name,'kind':meta['target']['kind'],'profile_test':meta['profile']['test']}
        table[name]={'target':kv,'pid':pid,'raw_trace_line_sha256':hashlib.sha256(line).hexdigest(),'raw_argv_sha256':dig(args),'positive_input_count':len(bare),'typed_direct_inputs':dict(collections.Counter(fd['root']+'/'+fd['role'] for fd in bare)),'operand_native_files':system,'compiler_and_plugin_options':native_meta,'search_directories_in_order':dirs,'libraries_in_order':libs,'bare_options_in_order':options,'bound_options_in_order':bound,'explicit_scripts':script_args,'response_files':response,'bundle_rlibs':sum(fd['role']=='ron-rlib'for fd in bare),'dir_layout_group':dkey,'library_group':key}
    assert len(table)==50
    return table
v={p:process(root/p)for p in ('unchanged-1','unchanged-2','unchanged-3')};out={'by_phase':v,'does_not_observe': ['implicit selected DSO or script bodies','unsuccessful path searches','whether GCC claimed any LTO input']};sys.stdout.buffer.write(gzip.compress(json.dumps(out,sort_keys=True,separators=(',',':')).encode(),mtime=0))
