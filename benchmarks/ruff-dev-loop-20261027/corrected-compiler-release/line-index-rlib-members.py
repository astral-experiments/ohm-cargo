from pathlib import Path
import hashlib,json,subprocess
d=Path(__file__).resolve().parent;raw=d/'line-index-v7a-release';scratch=Path('/dev/shm/ohm-line-index-v7a-release-20261027');rec=json.loads((raw/'receipts.json').read_bytes())
sha=lambda b:hashlib.sha256(b).hexdigest()
def members(arm,stage):
  store=scratch/(arm+('-warm' if stage=='warm-restore' else '-clean-restored'));h=rec[arm+'/'+stage]['producer_rlib'];matches=[f for f in store.rglob('libruff_source_file*.rlib') if sha(f.read_bytes())==h];assert matches,(store,h)
  file=matches[0];names=subprocess.check_output(['ar','t',file],text=True).splitlines();assert len(names)==len(set(names));parts={n:sha(subprocess.check_output(['ar','p',file,n])) for n in names};return {'archive':h,'members':parts,'order':names}
out={}
for arm in ('parent','candidate'):
 a=members(arm,'warm-restore');b=members(arm,'clean-restored');union=set(a['members'])|set(b['members']);changed=sorted(n for n in union if a['members'].get(n)!=b['members'].get(n));out[arm]={'warm_restored':a,'clean_restored':b,'order_equal':a['order']==b['order'],'changed_member_names':changed};print(arm,len(union),len(changed),a['order']==b['order'],changed[:3],flush=True)
(raw/'rlib-members.json').write_text(json.dumps(out,indent=2)+'\n')
