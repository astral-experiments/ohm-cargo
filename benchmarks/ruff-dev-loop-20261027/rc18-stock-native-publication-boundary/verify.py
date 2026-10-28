"""Verify the recorded physical subjects, launch modes, ordinary outputs, and independent controls."""
from pathlib import Path
import gzip
import hashlib
import json

here=Path(__file__).resolve().parent
def sha(data):return hashlib.sha256(data).hexdigest()
def read(name):return json.loads((here/name).read_bytes())
def read_gz(name):return json.loads(gzip.decompress((here/(name+'.json.gz')).read_bytes()))
proof=read('original-sha256.json')
assert proof['stock-wild']=='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'
assert proof['publish-target/debug/publish-probe']=='d09d9881be866d48598d3a6fd82aeedc983469556bf2e711eed18980ca52aa41'
for name in ('Cargo.toml','Cargo.lock','src/main.rs','src/publish.rs'):
 n='publish-probe/'+name;assert sha((here/n).read_bytes())==proof[n]
for name,orig in [('publication','publish3/result.json'),('volatile-roles','roles2/result.json'),('all-events','watch2/result.json'),('traced-events','outtrace2/result.json')]:
 assert sha(gzip.decompress((here/(name+'.json.gz')).read_bytes()))==proof[orig]
def by_case(rows):return {(r['case'],r['arm']):r for r in rows}
rows=read_gz('publication');cases=by_case(rows)
policy=dict(ordinary='hit',hardlink='output-type',symlink='output-type',missing='output-type',directory='output-type',running='output-open',unsealed='unsealed-input',readonly='output-type')
policy.update({'single-worker':'single-worker','user-xattr':'output-xattrs','changed-bytes':'output-digest-mismatch','bad-script':'unsupported-arguments','changed-code':'uncertified-inputs','native-sidecar':'wild-options'})
assert len(rows)==len(cases)==2*len(policy)
for k,decision in policy.items():
 stock,probe=cases[k,'stock'],cases[k,'proof']
 for field in ['main_o','expected_before','status','program_exit','stdout','stderr','image_after','write_events','was_same_inode','sidecar_sha256']:
  assert stock[field]==probe[field],(k,field)
 assert probe['decision']==decision
 for phase in ['before','after']:
  s,p=stock[phase],probe[phase]
  if s:
   assert all(s[f]==p[f] for f in ['mode','size','nlink','symlink','xattrs'])
  else:assert p is None
 argv=probe['native_argv']; assert '-plugin' in argv and '-lc' in argv and any(x.endswith('/crti.o') for x in argv)
 assert (probe['status']==1)==(k in ('readonly','directory','bad-script'))
 if k not in ('directory','changed-code'):assert probe['program_exit']==41
assert cases['ordinary','proof']['write_events']==[2,4,8]
assert cases['ordinary','proof']['was_same_inode']
assert cases['native-sidecar','proof']['sidecar_sha256']
assert cases['changed-code','proof']['program_exit']==83
assert len(cases['bad-script','proof']['stderr'])>3 and len(cases['directory','proof']['stderr'])>3
c=read('capability.json')
for k,r in c.items():
 assert r['capability_was_present'] and not r['capability_after'] and r['same_inode'] and r['inotify']==[2,4,8]
assert c['stock']['sha256']==c['candidate']['sha256'] and c['candidate']['action']=='output-xattrs'
r=read_gz('volatile-roles')['cases'];assert len(r)==8
assert r['spelling-A']['image']==r['spelling-B']['image'] and r['spelling-A']['raw']==r['spelling-B']['raw']==[] and r['spelling-A']['program']==r['spelling-B']['program']==42
assert len({r['fresh-native-'+k]['image'] for k in ('first','second','unwritable')})==1
for k in ('first','second'):
 assert r['gcc-lto-'+k]['native_lto_section'] and r['gcc-lto-'+k]['resolver_size']==154
assert r['gcc-lto-unwritable']['status']==0 and not r['gcc-lto-unwritable']['created_image'] and 'fatal error' in r['gcc-lto-unwritable']['stderr']
g=read('gcc-specs.json');assert sha((here/'gcc-specs.json').read_bytes())==proof['gcc-specs18/results.json'];assert g['wild']==proof['stock-wild']
assert [v['actual'] for v in g['rows']]==[41,83,41] and all(v['prior_wild_inputs_unchanged'] for v in g['rows'])
s=read_gz('all-events'); assert len(s)==8
for v in s:assert len(v['tokens_restored'])==v['tokens'] and v['before']==v['after'] and v['program_exit']==41
for n in ('all-events','traced-events'):
 a,b=read_gz(n)[:2];assert a['masks']==[32,2,4,8,32,1,16] and b['masks']==[32,1,32,2,4,8,16]
assert not s[2]['same_held_inode'] and not s[3]['same_held_inode']
assert s[5]['probe_width']==16 and 'count=20' in s[6]['loglines'][0]
assert 'O_RDONLY|O_NONBLOCK|O_NOFOLLOW|O_NOATIME' in (here/'probe-output-syscalls.txt').read_text()
assert 'pread64(' not in (here/'stock-output-syscalls.txt').read_text()
j=read('rehearsal-c5.json')
assert j['rehearsal-workspace-raw']['all_existing_regular_mode_0775_single_name_no_xattr']
assert j['rehearsal-workspace-raw']['native_counts']=={'full':1,'link-only':50,'wild':50}
a,b=(j['rehearsal-workspace-'+x+'-inputs'] for x in ('same','edit'))
assert (a['with_equal_elf'],a['with_same_observed_explicit_inputs'],a['shared_targets'])==(49,50,50) and a['literal_three_in_all']
assert (b['with_equal_elf'],b['with_same_observed_explicit_inputs'],b['shared_targets'])==(48,43,50)
assert a['e2e']['actual_elf_equal'] and not b['e2e']['all_observed_explicit_inputs_equal']
assert j['rehearsal-workspace-lookups']['absent_psm_libgcc_s']==50
print('28 publication arms, capability pair, 8 volatile native roles, 3 GCC-specs cases, 8 all-mask/jobserver + 2 traced controls and 50 workspace targets verified.')
