"""Two independent full Cargo runs from the same original training history, with ELF metadata reads."""
from pathlib import Path
import sys

label = sys.argv[1]
program = Path(__file__).with_name("fixed-ruff-parser-source.py")
P = Path("/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027")
driver = P / ("parse-source-replay-" + label) / "candidate-driver.so"
import hashlib
with driver.open("rb") as f: expected = hashlib.file_digest(f, "sha256").hexdigest()
sys.argv = [str(program), "--driver", str(driver), "--sha", expected, "--label", label + "-repeat"]
exec(compile(program.read_text().split("with (P/'native-measure.lock')")[0], str(program), "exec"))
old = J / ("fixed-source-ruff-" + label)
original = load(old / "results.json")

def archive(state, row, dest):
    dest.mkdir()
    rlib = phys(state, Path(row["rlib"]))
    assert sha(rlib) == row["rlib_sha256"]
    shell = dest / "archived-lib.rmeta"
    with shell.open("xb") as handle:
        subprocess.run(["ar", "p", str(rlib), "lib.rmeta"], stdout=handle, check=True)
    out = subprocess.run(["readelf", "-SW", str(shell)], check=True, capture_output=True)
    (dest / "sections.txt").write_bytes(out.stdout)
    part, = [n for n in (".rmeta", ".rustc") if re.search(r"\]\s+" + re.escape(n) + r"\s", out.stdout.decode())]
    payload = dest / "metadata-section.bin"
    subprocess.run(["objcopy","--dump-section",part+"="+str(payload),str(shell), str(dest/"objcopy-repack")], check=True)
    raw = phys(state, Path(row["rmeta"])).read_bytes()
    off = payload.read_bytes().find(raw)
    info = dict(rlib_sha256=sha(rlib), shell_sha256=sha(shell), section=part, section_sha256=sha(payload),
                section_length=payload.stat().st_size, raw_sha256=row["rmeta_sha256"], raw_length=len(raw),
                stored_raw_offset=off)
    dump(dest / "result.json", info)
    return info

with (P / "native-measure.lock").open("a") as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    idx = source_clean()
    gate_free(J, 16*2**30)
    O.mkdir(mode=0o700)
    skeleton_base = skeleton(O)
    train = old / "state/training"
    inc, = [Path(s.removeprefix("incremental=")).relative_to(TARGET) for s in original["train"]["parser"] if s.startswith("incremental=")]
    rows = {}
    for name in ("warm","empty"):
        st = O / ("state-" + name)
        gate_free(J, 7*2**30)
        subprocess.run(["cp", "-a", "--reflink=auto", "--", str(train),str(st)], check=True)
        idir, = (st/"target"/inc).glob("ruff_python_parser-*")
        assert any(idir.glob("s-*-*-*/query-cache.bin"))
        if name == "empty": idir.rename(O / "disabled-parser-session")
        data = run(name, st, "edited")
        orig = original[name]
        sections = {"original":archive(old/"state"/name,orig,O/("archived-"+name+"-original")),
                    "repeat":archive(st,data,O/("archived-"+name+"-repeat"))}
        fields = ["units","parser","externs","get_size_sha256","header","rmeta_sha256","native_ruff_diagnostic_sha256"]
        rows[name] = {"fields_equal":{k:data[k]==orig[k] for k in fields},"headers":data["header"],
                      "sections":sections, "argv_same":data["parser"]==orig["parser"],
                      "original_raw":orig["rmeta_sha256"],"repeat_raw":data["rmeta_sha256"]}
        dump(O/"results.json",rows)
        print(name,rows[name]["fields_equal"],sections,flush=True)
        assert all(rows[name]["fields_equal"].values()) and all(sections["original"][k]==sections["repeat"][k] for k in ("shell_sha256","section_sha256"))
    assert source_clean()==idx
    dump(O/"complete.json",dict(results_sha256=sha(O/"results.json"),driver_sha256=expected,index=idx,timings=0))
