from pathlib import Path
import copy,hashlib,json,math,statistics,sys
D=Path(__file__).resolve().parent
def read(n):return json.loads((D/n).read_bytes())
def h(n):
    with (D/n).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def need(v,msg):
    if not v:raise ValueError(msg)
def check(o):
    need(o['schema']==1 and o['n_pairs']==12 and o['score_files']==48 and o['physical_installations']==28,'cohort')
    need(o['registrations']==['c0ff49ab4428b3a07a28c8ddec47e6e40ea51eaccd7b6d6321b08809d0344829','292b13cc1d59ae054e64911727fbef7f10d034682827787da4e2c030258717d3'],'registration')
    need(o['qualified_commands']==140 and o['qualified_positive_readers']==138,'full commands')
    need(o['order'].count('PQ')==o['order'].count('QP')==6,'balance')
    need(len(o['scores'])==48,'number of observations')
    keys={(i+1,p,a) for i in range(12) for p in ('return-A','return-B') for a in 'PQ'}
    obs={(x[0],x[2],x[3]):x for x in o['scores']};need(set(obs)==keys,'roster')
    for x in obs.values():
        need(x[1]==o['order'][x[0]-1] and len(x)==9 and all(isinstance(v,(int,float)) and v>0 for v in x[4:]),'order/numerics')
    for p in ('return-A','return-B'):
        for k,ix in (('wall_s',4),('cpu_s',5),('git_wall_s',6),('observer_s',8)):
            z=[obs[(i,p,'P')][ix]/obs[(i,p,'Q')][ix] for i in range(1,13)]
            actual=o['summary'][p+'-'+k]
            v=sorted(z);need(math.isclose(statistics.median(z),actual['paired_median_ratio']) and all(math.isclose(j,t) for j,t in zip((v[2],v[9]),actual['paired_ratio_order_stat_CI'])),'recomputed pairs')
            need(actual['above_two']['above']==sum(i>2 for i in v),'threshold')
    native=read('native.json')
    need(native['original']!=native['edited'] and all(o['consumers'][k]['sha256']==native[k] for k in ('original','edited')),'independent empty executable')
    for a in 'PQ':
        for p in ('return-A','return-B'):
            both=o['cold_and_negative'][p+'/'+a]
            rn=o['cold_and_negative']['unchanged-B/'+a]
            need(both['commands']==13 and both['typed']==[97] and both['dirty']==[2] and rn['dirty']==[0],'actual dirty')
            data=native['controls'][a][p]
            found=o['changes_in_probe']
            selected=[x for x in found if x['arm']==a and x['direction']==p]
            need(len(selected)==1 and selected[0]['real_rustcs']==['ruff_python_ast','ruff_python_parser'] and selected[0]['object_create_opens']==data['object_opens'],'native open')
    term=read('terminal.json');need(term['slots']==28 and o['raw_terminal']==h('terminal.json') and term['native_sha256']==h('native.json'),'physical readback')
def main():
    o=read('observations.json');check(o)
    for mutation in ('duration','duplicate','order','ELF','native'):
        z=copy.deepcopy(o)
        if mutation=='duration':
            for row in z['scores']:
                if row[2]=='return-A' and row[3]=='P':row[4]*=2
        if mutation=='duplicate':z['scores'][-1]=z['scores'][0]
        if mutation=='order':z['scores'][0][1]='bad'
        if mutation=='ELF':z['consumers']['original']['sha256']=z['consumers']['edited']['sha256']
        if mutation=='native':z['changes_in_probe'][0]['object_create_opens']+=1
        try:check(z)
        except ValueError:continue
        raise ValueError('accepted mutation '+mutation)
    print('verified 12 chronological pairs, 48 raw observations, four native return traces, 140 Cargo commands, 138 native consumers, five rejection controls')
if __name__=='__main__':main()
