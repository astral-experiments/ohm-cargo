"""Check refusal of partial effects and an incorrect schedule without any real timing data."""
from pathlib import Path
from copy import deepcopy
import runpy
root=Path(__file__).resolve().parent
f=runpy.run_path(str(root/'verify.py'));plan=runpy.run_path(str(root/'screen.py'))
x={
 'no_replacements':True,'schedule':[list(z)for z in plan['schedule']('milan')],
 'grant_sha256':'b9243fe575b5e98131f32677ce3ba3a81b158773a45fdf68dff6421ac1e85b7e',
 'prepared_sha256':'0a5252a7911761b7dc66287efce56942a77c7d5b8a2382878edaf9afc3b6b96d',
 'grant':{'genoa_native_sha256':'165c876d4d9050b7f80f5688ca8135b75a7976b521a8940ed97d2f5214b2577b',
          'milan_native_sha256':'36f81452fe7d4b51bc3fbab1768ede3558faf5b0f5b1c02a113d1f701921be02'},
 'enrolled_bidirectional_golden':{
    'parent':{'archive_sha256':'80f07ae75685b8fc2f39e5a4d401d0b84b2a557a0114c02cbd0bb1f75133b322'},
    'historical':{'archive_sha256':'8f70068d10b763a31ea84bc6f36fc65d19010366bdec9b5ecb9edcf149599eea'}},
 'initial_sha256':'0'*64,'all_16_slots':[],'pair_seals':{},'actual_started_commands':0,'score':None,'terminal_exit':1}
assert f['check'](x)=={'terminal_exit':1,'verified_slots':0,'complete_pairs':0,'recorded_command_results':0,'effect_calculated':False}
for label,mutate in [('spurious effect',lambda y:y.update(score={'eligible':True})),
                     ('missing all results after success',lambda y:y.update(terminal_exit=0)),
                     ('unregistered first order',lambda y:y['schedule'][0].__setitem__(0,y['schedule'][0][0][::-1])),
                     ('different native release',lambda y:y['grant'].update(milan_native_sha256='f'*64))]:
 y=deepcopy(x);mutate(y)
 try:f['check'](y)
 except (AssertionError,KeyError):pass
 else:raise AssertionError(label)
print('A scored partial, success without outcomes, changed schedule and wrong native release were rejected.')
