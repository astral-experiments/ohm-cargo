# cargo-start(1)
## NAME

cargo-start --- Start an experimental Ohm workspace check session

## SYNOPSIS

`cargo -Zohm-check-session start --source` _SOURCE_ [_check-options_]

## DESCRIPTION

Start a workspace-local compiler host, perform the first check, and return. Later
[cargo-check(1)](cargo-check.html) commands in the same workspace can reuse its warm compiler
state. [cargo-stop(1)](cargo-stop.html) shuts down the host and its compiler. A failed first
check leaves the session available for repairs.

This experimental feature currently requires Unix. It retains one supported
library source file; use `-p` and `--lib` to select the library. Other targets and
unsupported edits use fresh checks. See [Ohm check sessions](../reference/unstable.html#ohm-check-session)
for the supported source edits, compatibility checks, and lifecycle.

## OPTIONS

<dl>
<dt class="option-term" id="option-cargo-start---source"><a class="option-anchor" href="#option-cargo-start---source"><code>--source</code> <em>SOURCE</em></a></dt>
<dd class="option-desc"><p>Select the source file whose supported edits may reuse compiler state. The path
is relative to the current directory and must be inside the workspace.</p>
</dd>

</dl>

Other options are the same as [cargo-check(1)](cargo-check.html), except `--no-session`,
`--unit-graph`, and `--compile-time-deps` cannot be used when starting a session.

## EXAMPLES

```console
cargo +ohm -Zohm-check-session start -p my-library --lib --source src/math.rs
cargo +ohm check -p my-library --lib
cargo +ohm stop
```

## SEE ALSO
[cargo(1)](cargo.html), [cargo-check(1)](cargo-check.html), [cargo-stop(1)](cargo-stop.html)
