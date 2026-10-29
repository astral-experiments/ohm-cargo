import json
from pathlib import Path

root = Path(__file__).resolve().parent
data = json.loads((root / "observed.json").read_bytes())
source = json.loads((root / "source.json").read_bytes())
known = {
    "check": {"6b9874c016d55a10": "65ba488117ac9e2f250067ae19e4523517f235630325250768f35425cae0c1d6"},
    "build": {"f0838d7cb39b023c": "c30769cd5e18fd543ba5cfae9cef2b554d4edf3efb5fad6c6744a99599c0c8b8"},
    "test": {"4987c8ded2339593": "50ec8e3c8fb4821c0dfa71ba90d22268f80876f5d0b2453c8e46f00e62d1d708", "105e97d570d35e4b": "2d1aa443f58255a95364f6eba5a9a2f779348b7259b917b1939e19cc852fb29f"},
}
assert set(known) == set(data)
for unit, phases in data.items():
    assert set(phases) == {f"{name}-unchanged-{i}" for name in ("parent", "child") for i in (1, 2)}
    for phase in phases.values():
        assert set(phase["raw"]) == {"native.json", "cargo.jsonl", "stderr", "status.json"}
        assert all(len(bytes.fromhex(s)) == 32 for s in phase["raw"].values())
        assert {"wrap_proc_macro", "proc_macro_span"} <= set(phase["proc_macro2_cfg"])
        assert phase["salsa_macro_artifact"] == ["libsalsa_macros-2862d9bcd7fb08e4.so"]
        assert {r["stem"]: r["argv_sha256"] for r in phase["semantic"]} == known[unit]
        for r in phase["semantic"]:
            assert r["missing"] == f"ty_python_semantic-{r['stem']}.d/ohm-foreign-span-bytes"
            assert set(r["typed_externs"]) == {"salsa", "bitflags"}
            assert r["test_harness"] == (r["stem"] == "105e97d570d35e4b")
assert source["all_bitflags_invocations"] == 12
assert set(source["bitflags_updates"]) == {"TypeQualifiers", "DataclassTransformerFlags", "LiteralFlags", "TypedDictFieldFlags"}
assert source["registry"]["bitflags"]["archive_sha256"] == "843867be96c8daad0d758b57df9392b6d8d271134fce549de6ce169ff98a92af"
assert source["sources"]["salsa/components/salsa-macros/src/update.rs"]["git_blob"] == "e3a78ee1a19d1cfc9dfc057f8f141375b64b61cd"
assert source["sources"]["synstructure-0.13.2/src/lib.rs"]["literal_source_lines"]["Span::call_site().located_at(field.span())"] == [495]
assert source["sources"]["quote-1.0.45/src/spanned.rs"]["literal_source_lines"]["first.join(last)"] == [36]
assert source["sources"]["rust/compiler/rustc_expand/src/proc_macro_server.rs"]["literal_source_lines"]["self.observe_foreign_span()"] == [811, 824, 865]
print("12 qualifying commands, 16 semantic rustc invocations, 4 argv identities, 4 source-predicted Salsa join sites; no native method counts")
