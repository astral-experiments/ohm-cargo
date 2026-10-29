import json
from pathlib import Path
r=json.loads((Path(__file__).resolve().parent/'registration.json').read_bytes())
assert r['native_source_pins']['new_host']=='82caf305a49bdcd62e366f9e9a16d58a7b486e28'
assert r['new_native_order']==['A unchanged','B unchanged','B H-to-P','A H-to-P','B P-to-H','A P-to-H']
assert r['raw_filemap']['H']=='64619248a515a474eb68e13b778d3d2ac5cdea6c7e96b4e5b7af53fa5e0023d0'
assert r['raw_filemap']['P']=='bb7bc674e996caf08bbfb3e03d89dc83df4ab2dbcff23251dd02407316e1ffa5'
assert r['qualified_existing_source']['archive_sha256']=='39268dec6160e5b3812330e903e7e3ccb6408f7eb0954af6041e3d274af856df'
assert r['independent_opposite_source']['archive_sha256']=='62e3465c98795e1f975a2b564758b61fc09c18120bebf3ce69669c0385955fec'
assert r['new_unchanged_each']=={'units':248,'fresh':248,'paths':452,'cargo':1,'rustc_full':0,'rustc_query':0,'linkers':0,'old_fd_and_all_bytes':True}
assert not any((r['score_authorized'],r['previous_slots_reused'],r['registered_direction_order_and_thresholds_changed']))
assert all(r['free_bytes_at_stop'][k]>=v for k,v in r['floor_bytes'].items()) and r['previous_observed_fresh']==0
assert r['all_future_controls']['expected_clones']=={'A':0,'B':1} and r['all_future_controls']['matched_fields']==512
print('New local seed identity, all raw maps, fresh-command gates, host floors and untouched four-direction design verified.')
