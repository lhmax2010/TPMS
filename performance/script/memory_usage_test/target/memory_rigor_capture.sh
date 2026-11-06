#!/bin/bash
# Noninteractive UEP payload, executed only through checked bash -c.
set -u
set -o pipefail
export LC_ALL=C
mode=${1:?mode}; out=${2:?destination}; sid=${3:-probe}
case "$out" in /opt/usr/tpms/result/memory_rigor/*) ;; *) echo 'invalid destination' >&2; exit 2;; esac
case "$out" in *..*) echo 'invalid destination' >&2; exit 2;; esac
finish() { local rc=$?; printf '已结束 %s 状态 %s\n' "$(date -Iseconds)" "$rc"; }
trap finish EXIT
command -v tar >/dev/null 2>&1 || { echo 'tar unavailable' >&2; exit 2; }
command -v sha256sum >/dev/null 2>&1 || { echo 'sha256sum unavailable' >&2; exit 2; }
mkdir -p "$out" || exit 2
operation_failed=0; last_rc=0
stamp() { local up rest; read -r up rest < /proc/uptime; printf '%s\n' "$up"; }
record() {
    local name=$1; shift
    if [[ "$name" == */* ]]; then mkdir -p "$out/${name%/*}" || return 2; fi
    printf '%q ' "$@" > "$out/$name.command"
    stamp > "$out/$name.start"
    "$@" > "$out/$name" 2> "$out/$name.stderr"; last_rc=$?
    [ "$last_rc" -eq 0 ] || operation_failed=1
    printf '%s\n' "$last_rc" > "$out/$name.rc"
    stamp > "$out/$name.end"
    # Explicit ENOENT evidence: never treat EACCES or arbitrary rc=1 as exit.
    if [ "$last_rc" -ne 0 ] && [ "$1" = cat ]; then
        local error=''; IFS= read -r error < "$out/$name.stderr" || true
        case "$error" in
            *"No such file or directory"*) printf 'ENOENT\n' > "$out/$name.errno" ;;
            *"No such process"*) printf 'ESRCH\n' > "$out/$name.errno" ;;
        esac
    fi
    return 0
}
start=$(stamp); [ -n "$start" ] || exit 2
record boot_id cat /proc/sys/kernel/random/boot_id
record uptime cat /proc/uptime
record snapshot_id printf '%s\n' "$sid"
if [ "$mode" = probe ]; then
    record meminfo.txt cat /proc/meminfo
    record cpu.txt cat /proc/stat
elif [ "$mode" = snapshot ]; then
    record memps.txt memps -v
    record meminfo.txt cat /proc/meminfo
    record vmallocinfo.txt cat /proc/vmallocinfo
    # Enumerate using shell builtins: no transient cat/ps helper in this set.
    pids=(); excluded=(); declare -A parents omitted
    omitted[$$]=1
    for d in /proc/[0-9]*; do
        [ -d "$d" ] || continue
        pid=${d##*/}; pids+=("$pid")
        line=''; if IFS= read -r line < "$d/stat" 2>/dev/null; then
            rest=${line##*) }; read -r state parent rest <<< "$rest"; parents[$pid]=$parent
        fi
    done
    # Descendant closure, including children whose PID sorts before their parent.
    changed=1
    while [ "$changed" -eq 1 ]; do
        changed=0
        for pid in "${pids[@]}"; do
            parent=${parents[$pid]:-0}
            if [ -n "${omitted[$parent]:-}" ] && [ -z "${omitted[$pid]:-}" ]; then omitted[$pid]=1; changed=1; fi
        done
    done
    selected=()
    for pid in "${pids[@]}"; do
        if [ -n "${omitted[$pid]:-}" ]; then excluded+=("$pid"); else selected+=("$pid"); fi
    done
    record excluded_pids printf '%s\n' "${excluded[@]}"
    record pids printf '%s\n' "${selected[@]}"
    for pid in "${selected[@]}"; do
        record "proc/$pid/stat" cat "/proc/$pid/stat"
        [ "$last_rc" -eq 0 ] || continue
        # flags is field 9; remove the parenthesized comm before splitting.
        line=''; IFS= read -r line < "$out/proc/$pid/stat" || continue
        rest=${line##*) }; read -r -a fields <<< "$rest"
        flags=${fields[6]:-0}
        if (( flags & 0x00200000 )); then continue; fi
        record "proc/$pid/comm" cat "/proc/$pid/comm"
        record "proc/$pid/exe" readlink -f "/proc/$pid/exe"
        record "proc/$pid/cmdline" cat "/proc/$pid/cmdline"
        record "proc/$pid/status" cat "/proc/$pid/status"
        record "proc/$pid/cgroup" cat "/proc/$pid/cgroup"
        record "proc/$pid/smaps_rollup" cat "/proc/$pid/smaps_rollup"
        record "proc/$pid/stat_end" cat "/proc/$pid/stat"
    done
    devices=(); for d in /sys/block/zram*; do [ -d "$d" ] && devices+=("$d"); done
    if [ ${#devices[@]} -eq 0 ]; then record zram_devices printf ''; else record zram_devices printf '%s\n' "${devices[@]}"; fi
    for d in "${devices[@]}"; do record "zram/${d##*/}" cat "$d/mm_stat"; done
    record swaps.txt cat /proc/swaps
elif [ "$mode" = tools ]; then
    record nevra rpm -q --qf '%{NAME}-%{EPOCHNUM}:%{VERSION}-%{RELEASE}.%{ARCH}\n' memps
    record memps_path command -v memps
    binary=$(cat "$out/memps_path"); rc=$?
    if [ "$rc" -eq 0 ] && [ -n "$binary" ]; then record sha256 sha256sum "$binary"; else record sha256 false; fi
    record os-release cat /etc/os-release
elif [ "$mode" = ion ]; then
    record ion_write bash -c 'printf "1\n" > /sys/kernel/debug/ion/heaps/ion_heap_system_shrink'
    record ion_settle sleep 3
else
    echo 'unknown mode' >&2; exit 2
fi
record boot_id_end cat /proc/sys/kernel/random/boot_id
record uptime_end cat /proc/uptime
end=$(stamp); [ -n "$end" ] || exit 2
count=$(find "$out" -type f | wc -l); rc=$?; [ "$rc" -eq 0 ] && [ -n "$count" ] || exit 2
pack_start=$(stamp); [ -n "$pack_start" ] || exit 2
archive="$out.tar"
tar -cf "$archive" -C "$out" . > "$archive.stdout" 2> "$archive.stderr"; pack_rc=$?
printf '%s\n' "$pack_rc" > "$archive.rc"
[ "$pack_rc" -eq 0 ] || { cat "$archive.stderr" >&2; exit 2; }
pack_end=$(stamp); [ -n "$pack_end" ] || exit 2
checksum=$(sha256sum "$archive"); rc=$?; [ "$rc" -eq 0 ] && [ -n "$checksum" ] || exit 2
printf 'TPMS_ARCHIVE %s %s %s %s %s %s\n' "${checksum%% *}" "$start" "$end" "$pack_start" "$pack_end" "$count"
exit "$operation_failed"
