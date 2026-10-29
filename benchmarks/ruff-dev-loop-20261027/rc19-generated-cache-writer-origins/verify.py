"""Recheck the source commitments and diagnostic transcripts without running Cargo."""
import hashlib
import json
import re
from pathlib import Path

root = Path(__file__).resolve().parent
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path): return json.loads((root/path).read_bytes())
e = read("evidence.json")
s = read("test-source.json")
assert e["parent_source"] == s["parent"] == "5394ce8817e224971230b80a9066cc28d504ff94"
assert e["fixed_source"] == s["fixed"] == "8dc33c9cc641e2b641c5b8e7075652a3e9e1f70b"
assert digest(root/"test-only.patch") == s["diff"] == e["test_only_patch_sha256"]
assert s["production_bytes_equal_parent"] and e["parent_source"] in e["parent_cli"]["version"]
assert e["parent_cli"]["sha256"] == "5cc0517d944c86d10dd8595ee8941f33ad5b15183fd56493cb799e3222b44021"
orig = read("source/result.json")
assert [k["pr"] for k in orig["rows"]] == [53,66,75,147]
for row in orig["rows"]:
    fn = f"source/pr-{row['pr']}.json"
    d = read(fn)
    assert digest(root/fn) == row["sha"] and d["state"] == "open" and d["draft"] is False
    assert d["active_ancestor_of"] == e["parent_source"] and d["parent_had_writer"] is False
    assert d["introducing_line"] == row["line"] and d["current_line"] == row["current_line"]
    assert any(x["line"] == row["line"] and d["writer"] in x["text"] for x in d["context"])
    assert d["source_url"].endswith(f"{d['introducing_commit']}/{d['path']}#L{row['line']}")
    assert len(d["introduced_blob"]["git_blob"]) == 40 and ((d["parent_blob"] is None) == (row["pr"] == 66))
u = e["unit"]
ut = root/"transcripts/red-unit.stdout"
assert digest(ut) == u["raw_stdout_sha256"] and u["exit"] == 101
assert "0 passed; 1 failed;" in ut.read_text() and u["name"]+" ... FAILED" in ut.read_text()
assert u["minimum_observed_free_bytes"] >= u["floor_bytes"] >= 45*2**30
def operands(body):
    m = re.search(r"left: (\[.*?\])\s+right: (\[.*?\])",body)
    return [bytes(json.loads(t)).decode() for t in m.groups()]
assert operands(ut.read_text()) == [u["after"],u["before"]]
assert u["before"] == "keep" and json.loads(u["after"]) == {"version":1,"value":"1"*32}
for i in e["integrations"]:
    label = i["label"]
    assert i["cli_sha256"] == e["parent_cli"]["sha256"]
    assert i["namespace_isolated"] and i["private_scratch"] and i["bound_cli_readonly"]
    assert i["result"] == 101 and len(i["real_child_commands"]) == {"symlink":1,"neighbor":3}[label]
    assert all(c["command"] == ["cargo","check","--package","selected"] and c["exit"] == 0 for c in i["real_child_commands"])
    stdout = (root/("transcripts/"+label+".stdout")).read_text()
    stderr = (root/("transcripts/"+label+".stderr")).read_text()
    assert "0 passed; 1 failed;" in stdout and "4820 filtered out" in stdout
    if label == "symlink":
        v = i["test_data"]
        assert operands(stderr) == [v["sentinel_after"],"keep"] and re.fullmatch("[0-9a-f]{16}",v["sentinel_after"])
        assert v["symlink_remained"] and v["assertion_saw_exact_target_bytes"]
    else:
        assert "error: expected not to find:" in stderr and "DEBUG cargo::ops::resolve: reusing the cached workspace resolution" in stderr
        assert "Checking selected" in stderr and "Checking external" in stderr
print("4 direct-parent writer introductions, 2 red regression assertions, 1 inherited neighbor failure, 4 successful traced child Cargo commands")
