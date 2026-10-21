This is one prospective retry of a metadata-only analysis closure after its first
launch stopped at the remote pre-staging quiet guard. It adds no Cargo calls,
samples, warmups, tests, statistical choices or quiet-guard exceptions.

The original package remains at `work/inheritance-ir-closure/`. Its failed
`launch-finalize.json`, `.stdout` and `.stderr` remain in place and are also copied
verbatim into `retry/history/` here. The failure was the exact frozen setup
program's line 15, before it read the capsule or created its remote directory.
The reported competing `uv-main` process is recorded as observed; this package
neither changes nor terminates that process. Control flow supports the original
pre-staging interpretation; a new read-only observation must prove the current
absence before this retry can launch.

All 47 files in the original closure source freeze, plus that freeze itself, are
byte-identical copies in this sibling package. The original source-freeze hash
is still `befbcd80ecdbfa09a14a39faf11891a01b65cb544522417fbbc29b3aa4352d10`;
the original capsule hash is still
`87271d54298ea323702ef858034bc82595717d3893e8de23a2a7b8e6c6f83642`.
The copied launcher therefore writes its new receipt into this distinct package,
without moving, replacing or concealing the failed receipt in the first package.
The added controls have their own `retry/source-freeze.json` and must be reviewed
and authorized before execution. Both packages must remain sibling directories
of `work/inheritance-measurement` because the unchanged source resolves that
relative layout. Root owns host availability and all remote execution.

`retry/launch.py` is single-use. It first rehashes both original/copy source sets,
the original failed closure launch, and the complete original 477-file failed IR
capture. A read-only remote probe requires the original host, UID, root, driver,
measurement seal and failed IR status, and checks `lexists` for the capsule
directory, all six analysis outputs, and native status. A dangling symlink also
fails. The resulting JSON absence proof and both raw streams are retained. Only
after success does it invoke the byte-identical original launcher. That launcher
still applies its exact quiet guard, exclusive capsule-directory creation,
full raw/input validation, and original analysis/gate tail. Its finalizer again
rejects changed raw bytes or preexisting analysis outputs before effects. Thus
the preliminary observation does not replace the later guards or imply an
atomic lock across two remote processes. Any failure stops this wrapper without
an automatic retry; all created files remain.

After root releases this exact retry on an available host:

```sh
taskset -c 8 /usr/bin/python3 -I -B work/inheritance-ir-closure-retry/retry/launch.py \
  --retry-source-freeze-sha256 RETRY_FREEZE_SHA256
```

After the original closure has completed, collect through the extra wrapper:

```sh
taskset -c 8 /usr/bin/python3 -I -B work/inheritance-ir-closure-retry/retry/collect.py \
  --phase ir --retry-source-freeze-sha256 RETRY_FREEZE_SHA256
```

The original collector and its remote code are byte-identical. Its raw archive,
manifest, receipt, and `collections/ir-closed-postguard` destination are unchanged.
The wrapper adds separate `local-operational-retry/`,
`operational-retry-manifest.json`, `operational-retry.tar` and archive descriptor
files. These bind both closure launches, the absence proof, extra controls, the
original 47 source files and the collector's streams to the original remote
collection, with SHA-256, sizes and a safely checked archive. It does not rewrite
the original transport manifest or receipt. The original failed IR capture and
the first failed closure launch remain separately retained.

Independent review uses the copied byte-identical raw/statistical reviewer,
surrounded by extra lineage checks. Statistics require the explicit flag after
root confirms the fixed phase is terminal; absent that flag the existing reviewer
only verifies raw integrity. Both workflows are still checked before any effects.

```sh
taskset -c 8 /usr/bin/python3 -I -B work/inheritance-ir-closure-retry/retry/review.py \
  --phase ir --output work/inheritance-raw-review/ir-closed-retry \
  --retry-source-freeze-sha256 RETRY_FREEZE_SHA256 --analyze-after-terminal
```

`review.json` remains the original reviewer's result; separate `retry-review.json`
binds it to this extra history. A valid negative result remains nonqualifying.
If both IR gates pass, the already frozen conditional native phase is unchanged.
Its later collection uses `--phase native`; its review additionally supplies
`--ir-review work/inheritance-raw-review/ir-closed-retry/review.json`, and requires
the matching qualifying `retry-review.json`. No old and new binary results are
pooled. No measurements or analysis have run during preparation of these sources.
