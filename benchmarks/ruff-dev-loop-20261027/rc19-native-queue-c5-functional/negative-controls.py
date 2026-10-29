"""Mutation checks against actual projected observations without modifying any evidence."""
import copy
from pathlib import Path
import runpy

base=Path(__file__).resolve().parent
v=runpy.run_path(str(base/"verify.py"))
read=v["read"]
meta=read(base/"provenance.json")
a=read(base/"phases/A-cold-edit.json")
b=read(base/"phases/B-cold-edit.json")
def rejected(call):
    try:call()
    except AssertionError:return
    raise RuntimeError("mutation admitted")
def test_phase(change):
    c=copy.deepcopy(a);change(c)
    rejected(lambda:v["phase_checked"]("A","cold-edit",c,meta["receipts"]["A"]["cold-edit"]))
def test_pair(field,value):
    c=copy.deepcopy(a);c["products"][0][field]=value
    rejected(lambda:v["comparison"]({("A","cold-edit"):c,("B","cold-edit"):b},("A","cold-edit"),("B","cold-edit")))
test_phase(lambda c:c["counts"].update({"stock-wild":187}))
test_phase(lambda c:c["products"].pop())
test_phase(lambda c:c["behavior"]["tests"]["notebook::hover_past_end_of_cell"].update({"exit":0}))
test_phase(lambda c:c["raw_sha256"].update({"execs.json":"0"*64}))
test_pair("normalized","0"*64)
test_pair("size",-1)
# Exact identical input-control row with one made-up raw change but unchanged decoded fields.
r=copy.deepcopy(a);r["products"][0]["sha256"]="0"*64
rejected(lambda:v["comparison"]({("A","cold-edit"):a,("B","cold-edit"):r},("A","cold-edit"),("B","cold-edit")))
print("Rejected seven altered count, roster, verdict, raw-evidence or ELF records")
