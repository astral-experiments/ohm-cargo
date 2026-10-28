"""Recompute every exported file hash and cross-check native execution, ELF sections and program outputs."""
from pathlib import Path
import argparse, ast, hashlib, io, json, re, tarfile

HERE = Path(__file__).resolve().parent
SHIPPED = '618ebac16b7d4ec01a2af89661d25b8f26ff347edbb69c6dcaa78f10115914a7'
BASE = '748e5862ece9b0e3098cdae472e1b0d94c50da724b8438f2e267c9007aee8737'
CARGO = '0aa04df8023984b83ef676d1494d43e482472e1b2bccdb82a4d0bd390578a322'
RUN_MAKE = {'rmake-incremental-proc-macro-native-inputs','rmake-incremental-attribute-proc-macro-cache','rmake-incremental-proc-macro-parse-source'}
HASH=lambda b:hashlib.sha256(b).hexdigest()
def archive(label):
    with tarfile.open(HERE/(label+'-native.tar.gz')) as t:
        files={m.name:t.extractfile(m).read() for m in t if m.isfile()}
        assert len(files)==len(t.getmembers()) and all(not Path(x).is_absolute() and '..' not in Path(x).parts for x in files)
    physical=json.loads(files.pop('PHYSICAL-SHA256.json'))
    assert physical=={k:[len(v),HASH(v)] for k,v in files.items()}
    return files
def load(a,k):return json.loads(a[k])
def direct(row, expected_driver, fixed=False):
    assert row['driver']==expected_driver
    slots=row['phases']
    for phase,r in slots.items():
        want=17 if phase in ['prime','prime_again','restore','restore_again','restored_clean'] else 29 if fixed or phase in ['clean'] else 17
        assert r['run']['exit']==0 and r['run']['stdout']==f'{want},{want}\n'
        assert r['reader']['exit']==0 and '-Zcache-proc-macros' in r['reader']['argv']
        reran = fixed or phase in ['prime','clean','restored_clean']
        calls=sorted(r['reader']['stderr'].splitlines())
        assert calls==([f'ran attribute {want}',f'ran derive {want}'] if reran else []),(phase,calls)
    if not fixed:
        left,right=slots['prime'],slots['c_edit']
        assert all(left[f]==right[f] for f in ['input','native_rs']) and all(left[f]!=right[f] for f in ['object','native_c','macro_dso'])
        assert {s for s in left['elf'] if left['elf'][s]!=right['elf'][s]}=={'.text'}
    else:
        for p in ['upgrade','again']:assert slots[p]['executable']==slots['clean']['executable']
        for p in ['restore','restore_again']:assert slots[p]['executable']==slots['restored_clean']['executable']
def suite(a,p,driver,fixed):
    r=load(a,p+'/results.json');assert load(a,p+'/identity.json')['driver']==driver
    assert set(r)==RUN_MAKE|{'macro-aux','dep-graph-rpass1','dep-graph-rpass2'}
    for n,x in r.items():
        assert x['exit']==(101 if not fixed and n in RUN_MAKE else 0),(p,n,x['exit'])
        for field,ext in [('trace','.exec'),('stderr','.stderr'),('stdout','.stdout')]:assert x[field]==HASH(a[p+'/'+n+ext])
    raw=a[p+'/rmake-incremental-proc-macro-native-inputs.stderr']
    if not fixed:assert b'=== ACTUAL TEXT ===\n17,17\n=== EXPECTED ===\n29,29' in raw
def docs(a,p,driver,fixed):
    d=load(a,p+'/terminal.json');assert d['driver']==driver
    for key,row in d['rows'].items():
        assert row['stdout_sha']==HASH(a[p+'/'+key+'.stdout']) and row['stderr_sha']==HASH(a[p+'/'+key+'.stderr'])
    for stage in ['prime','edit','again','cold']:
        want=17 if stage=='prime' else 29
        for flags in ['bare','last-no','last-yes']:
            key=stage+'-'+flags;r=d['rows'][key];c=d['rows']['rustc-'+key]
            assert r['items']==[f'constant.DERIVED_{want}.html',f'constant.MARKED_{want}.html'] and r['exit']==c['exit']==0 and not r['incremental_exists']
            index=a[p+'/doc-'+key+'/reader/index.html'];assert all(n.encode() in index for n in r['items'])
            assert sorted(r['reported'])==[f'attribute {want}',f'derive {want}']
            assert c['incremental_exists'] and sorted(c['reported'])==([f'attribute {want}',f'derive {want}'] if fixed or flags=='last-no' or stage in ('prime','cold') else [])
    for tool in ('rustc','rustdoc'):
        assert d['rows']['invalid-compile-'+tool]['exit']!=0 and b'incorrect value' in a[p+'/invalid-compile-'+tool+'.stderr']
        if fixed:assert 'accepted for compatibility' in d['rows']['help-'+tool]['cache_summary'][0]
def same_compiler_switch():
    r=json.loads((HERE/'effective-flag-only.json').read_bytes());assert r['driver']==SHIPPED
    at=r['rows']; inputs=r['inputs'];names=['edited','edited-again','first-disabled','disabled-again','empty-enabled']
    assert len({json.dumps(inputs[n],sort_keys=True) for n in names})==1
    assert at['first-disabled']['argv']==[x.replace('-Zcache-proc-macros=yes','-Zcache-proc-macros=no') for x in at['edited-again']['argv']]
    for n in ['original','original-again',*names]:
        value=17 if n in ('original','original-again','edited','edited-again') else 29
        calls=[] if n in ('original-again','edited','edited-again') else [f'ran attribute {value}',f'ran derive {value}']
        assert at[n]['exit']==at[n+'-run']['exit']==0 and at[n+'-run']['stdout']==f'{value},{value}\n' and sorted(at[n]['stderr'].splitlines())==calls
    assert at['first-disabled']['executable']==at['disabled-again']['executable']==at['empty-enabled']['executable']
    print('The shipped compiler recovered the two native values on its first compile after changing only the effective cache option.')
def actual_html(outputs,sub,doc_subject):
    def declared(body,name,value):
        a=re.search(rb'item-decl"><code>(.*?)</code></pre>',body,re.S);assert a is not None
        assert re.sub(rb'<[^>]+>',b'',a.group(1)).decode()==f'pub const {name}: u32 = {value};'
    for lab in ['shipping-docs','common-r2-matched-docs']:
        for phase in ['prime','edit','again','cold']:
            n=17 if phase=='prime' else 29
            for flag in ['bare','last-yes','last-no']:
                for prefix in ['DERIVED','MARKED']:
                    name=f'{prefix}_{n}';declared(outputs[f'{lab}/doc-{phase}-{flag}/reader/constant.{name}.html'],name,n)
    for arm in ['released','combined']:
        base='doc-native-counter/'+arm+'/';term=load(outputs,base+'terminal.json')
        assert term['driver']==(SHIPPED if arm=='released' else sub['driver'])
        assert arm=='released' or term['rustdoc']==doc_subject['rustdoc']
        for step in ('first','next'):
            row=term['rows'][step];pid=row['actual_pid'];d=base+step+'/'
            assert row['actual_calls']==[[pid,'DERIVE','1'],[pid,'ATTR','2']]
            assert row['exit']==0 and row['stdout']==HASH(outputs[d+'stdout']) and row['stderr']==HASH(outputs[d+'stderr'])
            assert outputs[d+'stderr'].splitlines()==[f'counter {pid} DERIVE 1'.encode(),f'counter {pid} ATTR 2'.encode()]
            assert re.search(rb'execve\("[^"\n]+/rustup/toolchains/ohm/bin/rustdoc",.* = 0$',outputs[d+'exec.'+pid],re.M)
            assert HASH(outputs[d+'html/sample/index.html'])==row['index']
            for name,n in [('DERIVE_1',1),('ATTR_2',2)]:
                item=f'constant.{name}.html';body=outputs[d+'html/sample/'+item];assert HASH(body)==row['docs'][item];declared(body,name,n)
    print('All 48 original/edited item pages and 8 in-process counter pages contain the expected actual Rust declarations. Both native macro calls use the traced rustdoc PID in every counter run.')
def artifact_identity(subject):
    b=(HERE/'final-build-receipt.json').read_bytes();r=json.loads(b);assert HASH(b)==subject['physical_receipt_sha256']
    assert r['candidate_postbolt']==subject['driver'] and r['frontend']==subject['frontend'] and r['source_identity']['selected_compiler_tree']==subject['combined_compiler_tree']
    assert r['source_identity']['selected_commit']==subject['combined_source'] and r['source_identity']['base']==subject['base']
    assert r['source_identity']['audit']['compiler/rustc_session/src/options.rs']['selected']==subject['compiler_options_sha256']
    assert HASH((HERE/'production-common.patch').read_bytes())==subject['product_patch_sha256']
    c=json.loads((HERE/'private-pr-ci.json').read_bytes());assert c['headRefOid']==subject['source'] and c['baseRefOid']==subject['base'] and len(c['statusCheckRollup'])==3 and all(j['conclusion']=='SUCCESS' for j in c['statusCheckRollup'])
    pairs=json.loads((HERE/'rustdoc-abi-control.json').read_bytes());old=pairs['frozen-donor'];mixed=pairs['old-rustdoc-with-new-driver']
    assert old['rustdoc']==mixed['rustdoc'] and old['frontend']==mixed['frontend'] and old['driver']!=mixed['driver']==subject['driver'] and pairs['installed-17']['driver']==SHIPPED
    for n,row in pairs.items():
        for mode in ('bare','off'):
            outcome=row['rows'][mode];assert outcome['argv']==old['rows'][mode]['argv']
            if n=='old-rustdoc-with-new-driver':assert (outcome['exit'],outcome['signal'])==(-11,'SIGSEGV') and not row['htmls']
            else:assert outcome['exit']==0 and row['htmls']==['constant.DERIVED_17.html','constant.MARKED_17.html']
    sessions=json.loads((HERE/'single-session-state.json').read_bytes())
    assert sessions['released']['driver']==SHIPPED and sessions['combined']['driver']==subject['driver']
    assert sessions['released']['source']==sessions['combined']['source']
    for arm,r in sessions.items():
        assert set(r['rows'])=={f'{m}-{s}-{p}' for m in ['same-thread','cross-thread'] for s in ['yes','no'] for p in ['cold','warm']}
        for k,x in r['rows'].items():
            ran=[] if arm=='released' and k.endswith('-yes-warm') else ['derive Left 1','attr FIRST 2','derive Right 3','attr SECOND 4']
            assert x['exit']==0 and x['value']==[1,2,3,4] and x['stderr']==ran
    print('Both native strategies retained the same four-call order and process-local state in 16 genuine full compiles.')
    print('The released and donor rustdoc matched pairs generated HTML. The donor rustdoc combined with the final driver received SIGSEGV for both flag spellings.')

def sync(a,p,fixed,macro='derive'):
    for time in (['preserved','current'] if macro=='derive' else ['preserved']):
        stem=p+'/dso-'+time;arm=load(a,stem+'/complete.json');ident=load(a,stem+'/original-and-replacement-elf.json')
        assert ident['old_full']==arm['compiled']['17']['product'] and ident['replacement_full']==arm['compiled']['29']['product']
        assert arm['compiled']['17']['bytes']==arm['compiled']['29']['bytes'] and arm['compiled']['17']['source']==arm['compiled']['29']['source']
        for n,row in ident['sections'].items():
            assert [row['before'],row['after']]==arm['sections'][n]
            if n=='.text':assert len(row['changed_bytes'])==1 and row['changed_bytes'][0][1:]==[17,29]
            else:assert not row['changed_bytes']
        assert ('r-xp' in next(r['permissions'] for r in arm['observed_old_maps'] if r['exe']=='rustc'))
        assert arm['old']['inode']!=arm['replacement']['inode'] and (arm['old']['mtime_ns']==arm['replacement']['mtime_ns'])==(time=='preserved')
        for phase,r in arm['rows'].items():
            assert load(a,stem+'/'+phase+'/result.json')==r and r['exit']==0 and not r['unit_fresh']
            prefix=stem+'/'+phase+'/'
            assert r['trace_sha256']=={n[len(prefix):]:HASH(b) for n,b in a.items() if n.startswith(prefix+'exec.')}
            actual=[line for n,b in a.items() if n.startswith(prefix+'exec.') for line in b.splitlines() if line.startswith(b'execve(') and b'"--crate-name", "hold_direct"' in line and line.endswith(b' = 0')]
            assert actual and all(b'-Zcache-proc-macros=yes' in l for l in actual)
            want=17 if phase=='initial' or not fixed and phase in ['repeat','again'] else 29
            assert (r['value'],r['join'])==(want,17 if phase=='initial' else 29)
            assert r[macro+'_calls']==([str(want)] if fixed or phase in ('initial','clean') else [])
def cargo(a,p,phase,driver):
    r=load(a,p+'/'+phase+'.json')
    required={'before':['prime','prime-again','c-edit','c-edit-again','empty-edited'],'after':['compiler-switch','compiler-switch-again','reader-edit','reader-edit-again','empty-after','restore','restore-again','empty-restored']}[phase]
    for n in required:
        x=r[n];assert load(a,p+'/'+n+'/result.json')==x and x['cargo']==CARGO and x['driver']==driver
        assert not any(v[1] for v in x['raw_deps'].values())
        native=sorted(t['crate'] for t in x['rustcs']);assert all(t['full'] and '-Zcache-proc-macros=yes' in t['argv'] for t in x['rustcs'])
        oracle=17 if n in ['prime','prime-again','c-edit','c-edit-again','restore','restore-again','empty-restored'] else 29
        assert x['value']==oracle,(p,n,x['value'],oracle,native)
        if n in ['c-edit-again','prime-again','compiler-switch-again','reader-edit-again','restore-again']:assert not native
        if n=='c-edit':assert native==['native_derive','plain_reader']
        if n=='reader-edit':assert native==['plain_reader']
        if n=='compiler-switch':assert 'plain_reader' in native
    return {n:(r[n]['value'],len(r[n]['rustcs'])) for n in required}
def diagnostic(a,p,driver,fixed):
    x=load(a,p+'/terminal.json');assert x['driver']==driver
    rows=x['rows']
    for n,r in rows.items():
        assert HASH(a[p+'/'+n+'.stdout'])==r['stdout'] and HASH(a[p+'/'+n+'.stderr'])==r['stderr']
    assert len({rows[n]['source_rust'] for n in ['prime','changed','again','independent','restored']})==1
    for n in ['prime','changed','again','independent','restored']:
        r=rows[n];fail=n=='independent' or fixed and n in ['changed','again']
        assert r['exit']==int(fail)
        if fail:
            assert len(r['diagnostics'])==2 and all(e['code']=='E0308' for e in r['diagnostics']) and r['diagnostics']==rows['independent']['diagnostics']
            assert r['native_calls']==['native ATTRIBUTE 29','native DERIVED 29']
        else:assert r['output']=='17,17\n'
arg=argparse.ArgumentParser();arg.add_argument('--baseline-only',action='store_true');arg.add_argument('--include-intermediate',action='store_true');args=arg.parse_args()
same_compiler_switch()
sh=archive('shipping');direct(load(sh,'released/results.json')[0],SHIPPED)
suite(sh,'checked-release-1',SHIPPED,False);suite(sh,'equivalent-off',SHIPPED,True);docs(sh,'shipping-docs',SHIPPED,False)
before=archive('before');direct(load(before,'direct.json')[0],BASE);suite(before,'phase-before/checked',BASE,False);sync(before,'phase-before/synced',False);print('Matched baseline Cargo',cargo(before,'ordinary-retained','before',BASE))
real=archive('source-upgrade-before');print('Shipped baseline Cargo',cargo(real,'ordinary-retained','before',SHIPPED))
print('The two matched macro libraries have equal metadata and symbol tables and one differing executable byte. The released rustdoc emits the current constants in all 12 source and argument cases.')
diagnostic(archive('diag-shipping'),'shipping-diagnostics',SHIPPED,False)
sync(archive('attr-released'),'attr-sync-released',False,'attribute')
if args.include_intermediate or not args.baseline_only:
    r1='56c284f25daf2ca93cac7bd2f37838dd024205725fd3cb51efac960c0f307708';a=archive('r1');q=load(a,'r1-preview/direct-results.json')
    assert q[0]==load(before,'direct.json')[0];direct(q[1],r1,True);suite(a,'r1-preview/suite',r1,True)
    sync(archive('r1-sync'),'r1-preview/synced',True);diagnostic(archive('diag-rustc-r1'),'rustc-r1-diagnostics',r1,True)
    assert load(a,'r1-preview/identity.json')['source_seed_unchanged'];print('Intermediate Cargo recovery',cargo(a,'r1-preview/cargo-copy','after',r1))
if not args.baseline_only:
    subject=json.loads((HERE/'final-subject.json').read_bytes());artifact_identity(subject);candidate=subject['driver']
    after=archive('after');dr=load(after,'direct.json');assert dr[0]==load(before,'direct.json')[0];direct(dr[1],candidate,True)
    sync(archive('attr-common-r2'),'attr-sync-common-r2',True,'attribute');diagnostic(archive('diag-common-r2'),'common-r2-diagnostics',candidate,True);suite(after,'phase-after/checked',candidate,True);sync(after,'phase-after/synced',True);print('Matched upgrade Cargo',cargo(after,'ordinary-retained','after',candidate))
    real=archive('source-upgrade-after');print('Shipped upgrade Cargo',cargo(real,'ordinary-retained','after',candidate))
    doc_archive=archive('doc-r2');meta=json.loads((HERE/'final-rustdoc.json').read_bytes());measured=load(doc_archive,'common-r2-matched-docs/terminal.json')
    assert meta['rustdoc']==measured['rustdoc'] and meta['runtime_driver']==candidate==measured['driver'] and measured['rustc']==subject['frontend']
    assert meta['compiler_tree']==subject['combined_compiler_tree'] and meta['rustdoc']!=json.loads((HERE/'rustdoc-abi-control.json').read_bytes())['frozen-donor']['rustdoc']
    docs(doc_archive,'common-r2-matched-docs',candidate,True);actual_html(archive('doc-native-html'),subject,meta)
    print('The source-complete compiler repaired both stale programs on the first upgrade compile and passed the native, diagnostic, and option-order controls.')
