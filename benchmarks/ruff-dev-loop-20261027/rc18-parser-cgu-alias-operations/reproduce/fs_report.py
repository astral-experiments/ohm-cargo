from snapshot import *
from collections import Counter,defaultdict
D=Y/'archive-fs-restore';assert json.loads((D/'exit.json').read_text())['status']==0; R=D/'raw';files={int(p.name.split('.')[-1]):p for p in R.glob('exec.*')};term=re.compile(r'\)\s+= ([0-9]+)(?:<[^\n]*>)?$');qre=re.compile(r'"((?:[^"\\]|\\.)*)"');clones=defaultdict(set);c=[];pref='ruff_python_parser-';rmeta='lib.rmeta';linkmeta='lib.rmeta-link'
for tid,p in files.items():
 for ln in p.open(errors='surrogateescape'):
  if ln.startswith(('clone(','clone3(')) and 'CLONE_THREAD' in ln and (m:=term.search(ln.rstrip())):clones[tid].add(int(m[1]))
  elif ln.startswith('execve(') and ln.rstrip().endswith('= 0') and '"--crate-name", "ruff_python_parser"'in ln and '/bin/rustc"' in ln:c.append((tid,ln.rstrip()))
assert len(c)==1,c;pid,line=c[0];m=re.match(r'^execve\("[^"\\]*", (\[.*\]), ',line);assert m;argv=ast.literal_eval(m[1]);family={pid};pending=[pid]
while pending:
 new=clones[pending.pop()]-family;family.update(new);pending.extend(new)
cmds=Counter();success=Counter();events=defaultdict(list);each=defaultdict(lambda:defaultdict(list));copy_names={'copy_file_range','sendfile','splice'};other_alias=Counter();saved=[]
for tid,p in files.items():
 isparser=tid in family
 for ln in p.open(errors='surrogateescape'):
  v=ln.rstrip();func=v.partition('(')[0];
  if not isparser and not (pref in v and '.rcgu.o' in v and func in ('link','linkat','rename','renameat','renameat2','unlinkat','unlink')):continue
  if isparser:cmds[func]+=1
  mt=term.search(v);r=int(mt[1]) if mt else None;args=qre.findall(v);paths=[z for z in args if ('/'in z or '.'in z) and not z.startswith('--')];cg=[Path(z).name for z in paths if Path(z).name.startswith(pref) and z.endswith('.rcgu.o')];raw=dig(v.encode(errors='surrogateescape'))
  if not isparser:
   if cg:other_alias[(func,r is not None)]+=1
   continue
  if r is not None:success[func]+=1
  if func in ('link','linkat','rename','renameat','renameat2','unlinkat','unlink','open','openat','openat2')and r is not None:
   for nm in set(cg):
    tag=func;sv={'tid':tid,'raw':raw}
    if func in ('link','linkat'):
     sv.update({'source_class':'incremental working generation' if any('/incremental/'in a and '-working/'in a and a.endswith('.o')for a in paths) else 'other','source':Path(paths[0]).name,'target':Path(paths[-1]).name})
    if func in ('open','openat','openat2'):sv['mode']='read' if 'O_RDONLY'in v else 'write'
    each[nm][tag].append(sv)
  if func in copy_names:
   rec={'syscall':func,'bytes':r,'alias_in_argument':bool('.rcgu.o'in v and pref in v),'raw':raw};events['copy'].append(rec)
  if func in ('rename','renameat','renameat2')and r==0 and any(a.endswith('.rlib') for a in paths):events['archive_rename'].append({'syscall':func,'from':Path(paths[0]).name,'to':Path(paths[-1]).name,'raw':raw})
  if func in ('unlink','unlinkat') and (r==0)and any(Path(a).name in (rmeta,linkmeta) for a in paths):events['metadata_cleanup'].append({'syscall':func,'name':Path(paths[-1]).name,'raw':raw})
  if isparser and func in ('link','linkat')and r==0 and not cg:
   cls='old incremental -> working generation' if len(paths)>1 and all('/incremental/'in a for a in paths[:2]) and '-working/'in paths[1] else 'other'
   events['other_links'].append({'class':cls,'source':Path(paths[0]).name if paths else None,'target':Path(paths[-1]).name if paths else None,'raw':raw})
assert len(each)==78,(len(each),pid,len(family));before=json.loads((D/'before.json').read_text());after=json.loads((D/'after.json').read_text());wp={Path(x['path']).name:x for x in before['incremental_work_products']};postwp={Path(x['path']).name:x for x in after['incremental_work_products']};assert len(wp)==78;rows=[]
for n,ops in sorted(each.items()):
 link=ops['linkat']+ops['link']; un=ops['unlinkat']+ops['unlink']; reads=[p for k in ('open','openat','openat2')for p in ops[k]if p['mode']=='read'];assert len(link)==1 and len(un)==1 and len(reads)>=1,(n,dict(ops));ws=link[0]['source'];assert link[0]['source_class']=='incremental working generation';a,b=wp[ws],postwp[ws];assert a['sha256']==b['sha256'] and (a['dev'],a['ino'])==(b['dev'],b['ino']);rows.append({'name':n,'workspace_cgu':ws,'bytes':a['bytes'],'input_sha256':a['sha256'],'work_product_same_inode_and_bytes':True,'hard_link_tid':link[0]['tid'],'hard_link_sha256':link[0]['raw'],'archive_input_open_sha256':[v['raw']for v in reads],'unlink_tid':un[0]['tid'],'unlink_sha256':un[0]['raw']})
stdout=[json.loads(l)for l in (D/'stdout.jsonl').read_text().splitlines()];srows=[r for r in stdout if r['reason']=='compiler-artifact' and r['target']['name']=='ruff_python_parser'];assert len(srows)==1;res={'parser_root':pid,'family':sorted(family),'argv_sha256':dig(json.dumps(argv,separators=(',',':')).encode()),'raw_successful_exec_sha256':dig(line.encode()),'expected_crate_types':[a for i,a in enumerate(argv)if i and argv[i-1]=='--crate-type'],'emit':[a for a in argv if a.startswith('--emit')],'save_temps_flags':[v for v in argv if 'save-temps'in v],'rlink_flags':[v for v in argv if 'relink-only'in v or v=='link-only'],'raw_file_sha256':{str(t):sha(files[t]) for t in family},'declared_outputs':[Path(p).name for p in srows[0]['filenames']],'before_visible':before['unit_out'],'after_visible':after['unit_out'],'rlinks_before_after':[before['rlink_files_in_unit'],after['rlink_files_in_unit']],'cgu_aliases_before_after':[before['explicit_rcgu_files'],after['explicit_rcgu_files']],'counts_parser_success':dict(success),'all_successful_new_logical_aliases':len(rows),'all_parser_removals_of_those_aliases':len(rows),'other_process_related_name_syscalls':dict((str(k),v)for k,v in other_alias.items()),'events':dict(events),'aliases':rows,'before_after_78_native_bytes':sum(v['bytes']for v in rows),'root_exec_trace_hash':sha(D/'exit.json')};write(D/'result.json',res)
