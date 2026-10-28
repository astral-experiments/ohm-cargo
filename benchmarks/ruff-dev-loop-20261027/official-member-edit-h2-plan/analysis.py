from member_stats import endpoint

def analyze(plan,ledger):
    assert set(ledger)=={'edit','first_unchanged','edit_plus_first'}
    result={key:endpoint(rows,plan['bootstrap'][key]) for key,rows in ledger.items()}
    highest=0
    for rank,key in enumerate(sorted(result,key=lambda key:result[key]['p'])):
        row=result[key];highest=max(highest,min(1,(3-rank)*row['p']));row['holm']=highest
        row['qualifies']=highest<.05 and row['ci95'][0]>1 and row['pairs_faster']>=16
        row['material_regression']=highest<.05 and row['ci95'][1]<-1
    return result
