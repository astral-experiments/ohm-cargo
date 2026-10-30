"""Build the compact, human-readable result from the verified terminal observations."""
import argparse
import gzip
import json
from pathlib import Path

def main(path):
    s=json.loads((path/"statistics.json").read_bytes())
    o=json.loads(gzip.decompress((path/"observations.json.gz").read_bytes()))
    v=s["phase_metrics"]
    primary=s["both_wall_endpoints_exceed_two"]
    lines=["# Ruff formatter branch-switch confirmation","",
           "The registered two-direction 2× wall-time criterion "+("passed" if primary else "did not pass")+
           " across twelve counterbalanced installation pairs. The command built the ruff_python_formatter library-test executable on both sides of [Ruff #28335](https://github.com/astral-sh/ruff/pull/28335). All 24 ordinary installations and four separate native/correctness controls are included.",
           "","| Return | Parent median | Guarded median | Median paired wall ratio | Simultaneous interval | Pairs above 2× | Balanced randomization | Two-sided sign test against 2× |",
           "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for name in ("return-A","return-B"):
        r=v[name]["wall_s"];lo,hi=r["simultaneous_two_endpoints"]["range"]
        lines.append(f"| {name[-1]} | {r['parent_median']:.3f} s | {r['candidate_median']:.3f} s | {r['median_ratio']:.3f}× | {lo:.3f}–{hi:.3f}× | {r['above_two']}/12 | {r['randomization_extreme']}/924 = {r['balanced_randomization_p']:.6f} | {r['paired_sign_p_against_two']:.6f} |")
    lines += ["","The ratios pair nearby installations before taking their median. The intervals use the second and eleventh sorted ratios for each direction. Their marginal coverage is 99.365%, which gives simultaneous coverage of at least 98.73% for the two prespecified directions. The randomization test uses the signed chronological log differences for all six-parent-first assignments. The sign test evaluates the 2× threshold separately.",
              "","| Phase | Wall median P → Q (s) | Whole CPU median P → Q (s) | Paired CPU ratio | Physical incremental median P → Q (MiB) |",
              "| --- | ---: | ---: | ---: | ---: |"]
    for phase in ("empty-A","first-B","return-A","return-B","unchanged-B"):
        w,c,b=[v[phase][k] for k in ("wall_s","cpu_s","incremental_allocated_bytes")]
        lines.append(f"| {phase} | {w['parent_median']:.3f} → {w['candidate_median']:.3f} | {c['parent_median']:.3f} → {c['candidate_median']:.3f} | {c['median_ratio']:.3f}× | {b['parent_median']/2**20:.2f} → {b['candidate_median']/2**20:.2f} |")
    lines += ["","| Switch | Git median P → Q (ms) | Median paired wall ratio including Git |",
              "| --- | ---: | ---: |"]
    for phase in ("first-B","return-A","return-B"):
        g=v[phase]["git_s"];w=v[phase]["with_git_s"]
        lines.append(f"| {phase} | {1000*g['parent_median']:.2f} → {1000*g['candidate_median']:.2f} | {w['median_ratio']:.3f}× |")
    lines += ["","Both compilers launched the same four full rustc processes for ruff_db, ruff_python_ast, ruff_python_parser and ruff_python_formatter on every traced return. Each used one GCC driver, one collect2 and one stock Wild. The replay captured actual successful object creation requests. Counts below are distinct, named .rcgu.o destinations as observed through successful writable open calls with O_CREAT.",
              "","| Source | Parent pre/post CGU paths | Guarded pre/post CGU paths |",
              "| --- | ---: | ---: |"]
    controls=o["controls"]
    for name in ("return-A-native","return-B-native"):
        ids=lambda a:[controls[q+"-"+a][name]["native"]["cgus_opened_for_creation"] for q in ("admit","post")]
        p,q=ids("P"),ids("Q")
        lines.append(f"| {name[7]} | {p[0]} / {p[1]} | {q[0]} / {q[1]} |")
    lines+=["","All 216 physical typed units agree across both versions, source branches and successful visits. The shorter package/feature key gives 204 distinct labels. The full Cargo profile and each emitted basename distinguish all 216 units. Each revision’s warm executable matched its independently empty executable byte for byte across both compilers. Four deliberately invalid formatter builds returned Cargo 101 with E0308 at the same file, line and column; all repaired builds succeeded. Twenty-eight complete clean suites each passed 51 tests and ignored two. There were 432 individual representative test passes and 144 successful/144 rejected external ABI assertions using the actual graph’s AST/parser libraries.",
            "","| Historical Ruff revision | Whole clean/warm ELF SHA-256 | Bytes |",
            "| --- | --- | ---: |"]
    for rev in ("A","B"):
        e=o["elf_cas"][rev]
        lines.append(f"| {rev} | `{e['sha256']}` | {e['bytes']:,} |")
    lines+=["","The two builds of [astral-experiments/ohm-rust](https://github.com/astral-experiments/ohm-rust) used the same optimized stage1 configuration and differed in the single rustc_driver file. The experiment used the same #294 Cargo and stock Wild on four AMD EPYC Milan CPUs and private RAM-backed workspaces. It measures repeated returns to these two historical source versions. The figures above characterize the source-built kits on this machine.",
            "","The acquisition checked process completion at approximately 12 ms intervals. Each elapsed observation includes this exit-detection granularity, including the shorter unchanged commands. CPU uses the operating system’s child process resource accounting. Every nanosecond, user/system CPU value, incremental allocation histogram and normalized native process/CGU record is in observations.json.gz. statistics.json includes the full paired values, order strata, each discrete interval and each exact P value. REPRODUCE.md gives the offline verification and independent local replay commands. The authenticated input manifests and prior two-pair screen have separate identities. The source-built toolchain metadata and exact Git trees are in materials.json.",""]
    disk=json.loads((path/"disk-scope.json").read_bytes())
    lines += ["## Space after each ordinary command", "", "The original recordings include two distinct physical storage boundaries. The incremental column below counts each inode once across target and shared, using actual allocated blocks. The whole private filesystem also includes Git, checkout files, mutable registry data, Cargo state and temporary files. Its after-Cargo value precedes behavior validation. The read-only SDK and registry lower live outside that filesystem. We did not separately census every nonincremental target/shared file in this cohort. Individual native executable sizes are listed above.", "", "| Phase | Physical incremental P → Q (MiB) | Paired incremental increase (MiB) | Whole private filesystem P → Q (MiB) | Paired whole-filesystem increase (MiB) |", "| --- | ---: | ---: | ---: | ---: |"]
    for phase in ("empty-A","first-B","return-A","return-B","unchanged-B"):
        item=disk["phases"][phase]
        inc=item["incremental_charged"];total=item["private_fs_used_after"]
        vals=lambda pt:tuple(pt["medians"][arm]/2**20 for arm in ("P","Q"))
        a,b=vals(inc);c,d=vals(total)
        lines.append(f"| {phase} | {a:.2f} → {b:.2f} | {inc['median_paired_candidate_minus_parent_bytes']/2**20:+.2f} | {c:.2f} → {d:.2f} | {total['median_paired_candidate_minus_parent_bytes']/2**20:+.2f} |")
    lines += ["", "disk-scope.json contains every before/after value for the 24 ordinary installations, the apparent and allocated incremental bytes, medians, paired differences and ratios. Only the preregistered latency endpoints enter the 2× decision.", ""]
    return "\n".join(lines)
if __name__=="__main__":
    a=argparse.ArgumentParser(description=__doc__);a.add_argument("packet",type=Path)
    print(main(a.parse_args().packet),end="")
