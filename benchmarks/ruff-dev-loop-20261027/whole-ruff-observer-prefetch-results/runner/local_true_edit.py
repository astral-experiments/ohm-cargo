from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import paired
study=paired.Study(paired.getargs()); study.references(); store=study.init('unit'); output={}
for i in range(4):
    row=study.run(store,'C','prime-'+str(i),trace=True); study.equivalent(row,study.gold[False])
assert not row['roster'] and len(row['readers'])==2 and all(v['complete'] and v['signed'] for v in row['readers'].values())
for direction in (True,False):
    study.edit(store,direction)
    label='add' if direction else 'remove'
    row=study.run(store,'C',label,trace=True);study.equivalent(row,study.gold[direction]);rr=row['roster'];assert len(rr)==5
    assert {r['crate'] for r in rr if r['mode']=='full'}=={'hold_bridge','hold_direct','hold_shapes','hold_indirect'}
    assert {r['crate'] for r in rr if r['mode']=='relink'}=={'hold_plain'}
    noop=study.run(store,'C','after-'+label,trace=True);study.equivalent(noop,study.gold[direction]);assert not noop['roster']
    output[label]={'jobs':rr,'products':row['native_products'],'empty':study.gold[direction]['native_products'],'repeat_jobs':noop['roster']}
paired.log_json(study.logs/'two-edits.json',{'cargo':study.digest['C'],'driver':study.digest['driver'],'endpoints':output})
