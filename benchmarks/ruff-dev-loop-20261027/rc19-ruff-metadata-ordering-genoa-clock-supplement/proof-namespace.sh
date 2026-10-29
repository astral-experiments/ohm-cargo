set -euo pipefail
r=$1; p=$2; uid=$3; gid=$4; hm=$5; mode=$6; case=$7
v=$p/volume;work=$hm/code/oss/ruff-ohm-rmeta-second-host-20261029
gitdir=$hm/code/oss/ruff-ohm-rmeta-second-host-seed-20261029/.git/worktrees/ruff-ohm-rmeta-second-host-20261029
mount -t btrfs -o loop,ro,nosuid,nodev "$r/common-store-v1.btrfs" "$v"
if test "$mode" = rehearse; then
  [[ "$case" =~ ^(child-to-parent|parent-to-child)-(A|A2|B|B2)$ ]]
  child=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["cases"][sys.argv[2]]["root"])' "$r/real-linter-readers-v1/geometry.json" "$case")
  [[ "$child" =~ ^(stable-pgo-live|prior-to-admin-[A-Za-z0-9-]+)$ ]]
else
  test "$mode" = score; [[ "$case" =~ ^pair-[0-9]{2}-visit-[01]-[AB]$ ]]; child=supplement-held-$case
fi
root=$v/$child;live=$v/stable-pgo-live;test -f "$root/workspace/Cargo.toml";test -d "$root/git-admin";test ! -L "$root"
if test "$root" != "$live"; then mount --bind "$root" "$live";fi
mount --bind "$live/workspace" "$work";mount --bind "$live/git-admin" "$gitdir"
setpriv --reuid="$uid" --regid="$gid" --clear-groups --no-new-privs --bounding-set=-all --inh-caps=-all --ambient-caps=-all env HOME="$hm" USER=dev-user LOGNAME=dev-user taskset -c 0-7 python3 -IB "$r/genoa-supplement-v1/proof.py" "$mode" "$case"
