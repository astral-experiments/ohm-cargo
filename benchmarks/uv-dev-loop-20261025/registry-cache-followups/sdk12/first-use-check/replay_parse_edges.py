"""Replay direct TOML edges from the same 32 qualified full profiles."""
from pathlib import Path
from collections import Counter
import argparse,gzip,hashlib,importlib.util,json,re,statistics

OUTER = re.compile(r"_RNvNtNtCs[0-9A-Za-z_]+_4toml2de6parser14parse_document(?:\.llvm\.\d+)?")

NESTED = re.compile(r"_RNvNtNtCs[0-9A-Za-z_]+_11toml_parser6parser8document14parse_document(?:\.llvm\.\d+)?")

def graph(raw, expected):
    names = {};calls = Counter();costs = Counter();self_cost = Counter()
    current = callee = None;pending = None
    for line in raw.decode().splitlines():
        symbol = re.fullmatch(r"(c?)fn=\((\d+)\)(?: (.*))?", line)
        if symbol:
            assert pending is None
            foreign, key, name = symbol.groups()
            if name:
                assert key not in names or names[key] == name
                names[key] = name
            if foreign:callee = key
            else:current = key
        elif line.startswith("calls="):
            assert pending is None and current in names and callee in names
            count = int(line.split("=", 1)[1].split()[0]);assert count >= 0
            pending = current, callee, count
        elif line and line[0] in "0123456789+-*":
            match = re.fullmatch(r"(?:\d+|[+-]\d+|\*)\s+(\d+)\s*", line);assert match
            cost = int(match[1])
            if pending is None:
                assert current in names;self_cost[current] += cost
            else:
                caller, target, count = pending;calls[caller, target] += count;costs[caller, target] += cost;pending = None
    assert pending is None and sum(self_cost.values()) == expected
    def function(pattern):
        selected = [key for key, value in names.items() if pattern.fullmatch(value)]
        assert len(selected) == 1, selected
        key = selected[0]
        incoming = [{"caller": names[caller], "calls": calls[caller, dest], "inclusive_ir": costs[caller, dest]}
                    for caller, dest in calls if dest == key]
        outgoing = [{"callee": names[dest], "calls": calls[caller, dest], "inclusive_ir": costs[caller, dest]}
                    for caller, dest in calls if caller == key]
        total = sum(row["inclusive_ir"] for row in incoming)
        assert total == self_cost[key] + sum(row["inclusive_ir"] for row in outgoing)
        return {"symbol": names[key], "calls": sum(row["calls"] for row in incoming), "entry_ir": total,
                "self_ir": self_cost[key], "incoming": sorted(incoming, key=lambda x: -x["inclusive_ir"]),
                "outgoing": sorted(outgoing, key=lambda x: -x["inclusive_ir"]), "self_plus_outgoing_equals_incoming": True}
    return {"final_ir": expected, "outer_toml": function(OUTER), "nested_toml_parser": function(NESTED)}


def main():
    p=argparse.ArgumentParser();p.add_argument('--record',action='store_true');args=p.parse_args()
    root=Path(__file__).resolve().parent
    spec=importlib.util.spec_from_file_location('count_replay',root/'reproduce.py')
    reader=importlib.util.module_from_spec(spec);spec.loader.exec_module(reader)
    read=lambda p:json.loads(p.read_bytes())
    for name,row in read(root/'CORE-MANIFEST.json')['files'].items():reader.checked_blob(root/name,row)
    manifest=read(root/'profiles/PROFILE-MANIFEST.json')['profiles'];counts=read(root/'counts.json')['blocks']
    assert len(manifest)==32 and len(counts)==2
    profiles={}
    for key,row in sorted(manifest.items()):
        raw=gzip.decompress(reader.checked_blob(root/'profiles'/row['file'],row))
        assert len(raw)==row['raw_bytes'] and hashlib.sha256(raw).hexdigest()==row['raw_sha256']
        metric=reader.final_ir(raw,row['counter_line']+'\n',reader.COMMAND)
        assert metric==row['metric'] and not metric['brk_overflow_warning']
        profiles[key]=graph(raw,metric['final_ir'])
    blocks=[]
    for i,block in enumerate(counts):
        pairs=[]
        for pair,order in enumerate(reader.ORDERS[i]):
            values={('baseline' if letter=='A' else 'candidate'):profiles[f"block-{i+1}/pair-{pair}-{position}-{'baseline' if letter=='A' else 'candidate'}"] for position,letter in enumerate(order)}
            a,b=values['baseline'],values['candidate']
            assert a['final_ir']==block['pairs'][pair]['baseline'] and b['final_ir']==block['pairs'][pair]['candidate']
            total=b['final_ir']-a['final_ir'];outer=b['outer_toml']['entry_ir']-a['outer_toml']['entry_ir']
            pairs.append({'pair':pair,'order':order,'signed_total_ir':total,'signed_outer_parse_ir':outer,
                          'signed_remainder_ir':total-outer,'outer_call_difference':b['outer_toml']['calls']-a['outer_toml']['calls'],
                          'signed_nested_ir_contained_not_additive':b['nested_toml_parser']['entry_ir']-a['nested_toml_parser']['entry_ir']})
        ranges={}
        for arm in ('baseline','candidate'):
            rows=[v for k,v in profiles.items() if k.startswith(f'block-{i+1}/') and k.endswith(arm)]
            assert len(rows)==8
            ranges[arm]={field:[min(r['outer_toml'][field] for r in rows),max(r['outer_toml'][field] for r in rows)] for field in ('calls','entry_ir','self_ir')}
        blocks.append({'block':i+1,'pairs':pairs,'outer_ranges':ranges,
                       'mean_signed_total_ir':statistics.fmean(r['signed_total_ir'] for r in pairs),
                       'mean_signed_outer_ir':statistics.fmean(r['signed_outer_parse_ir'] for r in pairs),
                       'mean_signed_remainder_ir':statistics.fmean(r['signed_remainder_ir'] for r in pairs)})
    result={'state':'qualified-profile-direct-edge-accounting','profiles':profiles,'blocks':blocks,
            'signed_convention':'candidate minus R1, independently per pair and per host',
            'cost_boundary':'Direct incoming inclusive Ir for the pinned outer toml::de::parser::parse_document symbol. Nested toml_parser edges are contained and never added to it.',
            'interpretation':'The remainder contains all other changes; gross eliminated parser work is not the net process saving. No elapsed or additive cross-study claim.'}
    if args.record:
        with (root/'parse-edges.json').open('x') as f:json.dump(result,f,sort_keys=True,indent=2);f.write('\n')
    else:assert read(root/'parse-edges.json')==result
    print(json.dumps({'state':'direct-edge-replay-passed','blocks':[{k:v for k,v in b.items() if k!='pairs'} for b in blocks]},indent=2))

if __name__=='__main__':main()
