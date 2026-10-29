set -euo pipefail
r=$1;p=$2;uid=$3;gid=$4;userhome=$5;n=$6;pos=$7
o=$r/genoa-supplement-v1;v=$p/volume;w=$userhome/code/oss/ruff-ohm-rmeta-second-host-20261029
mount -t btrfs -o loop,nosuid,nodev,user_subvol_rm_allowed "$r/common-store-v1.btrfs" "$v"
g=$userhome/code/oss/ruff-ohm-rmeta-second-host-seed-20261029/.git/worktrees/ruff-ohm-rmeta-second-host-20261029
bound=no;gb=no
clean(){ if test "$gb" = yes; then umount "$g"; fi; if test "$bound" = yes; then umount "$w"; fi; umount "$v"; }
trap clean EXIT
asuser=(setpriv --reuid="$uid" --regid="$gid" --clear-groups --no-new-privs --bounding-set=-all --inh-caps=-all --ambient-caps=-all env HOME="$userhome" USER=dev-user LOGNAME=dev-user /usr/bin/taskset -c 0-7 /usr/bin/python3 -IB)
"${asuser[@]}" "$o/reset.py" "$n" "$pos"
printf -v ns '%02d' "$n"
shopt -s nullglob
id=("$r/genoa-supplement-scored/pair-$ns-visit-$pos-"*.deleted-id)
if ((n>0 || pos>0)); then test "${#id[@]}" = 1; read -r old_id <"${id[0]}"; [[ "$old_id" =~ ^[0-9]+$ ]]; btrfs subvolume sync "$v" "$old_id"; else test "${#id[@]}" = 0; fi
test -f "$v/stable-pgo-live/workspace/.git" && test -f "$w/.git"; mount --bind "$v/stable-pgo-live/workspace" "$w";bound=yes
test -d "$g" && test ! -L "$g"; mount --bind "$v/stable-pgo-live/git-admin" "$g";gb=yes
"${asuser[@]}" "$o/clock.py" "$n" "$pos"
