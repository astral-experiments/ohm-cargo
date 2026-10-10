# cargo-stop(1)
{{~*set command="stop"}}

## NAME

cargo-stop --- Stop the experimental Ohm workspace check session

## SYNOPSIS

`cargo stop` [_options_]

## DESCRIPTION

Stop the workspace host created by {{man "cargo-start" 1}}. Wait for any active
request, terminate the retained compiler, and remove its private outputs before
returning. Stopping a workspace without a running session succeeds.

Later {{man "cargo-check" 1}} commands use ordinary Cargo until a new session is
explicitly started. Sessions are scoped to canonical workspace roots; stopping
one workspace does not stop another.

## OPTIONS

### Manifest Options
{{#options}}
{{> options-manifest-path }}
{{> options-locked }}
{{/options}}

{{> section-options-common }}

## SEE ALSO
{{man "cargo" 1}}, {{man "cargo-start" 1}}, {{man "cargo-check" 1}}
