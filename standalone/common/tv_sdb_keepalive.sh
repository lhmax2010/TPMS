#!/bin/bash
#
# tv_sdb_keepalive.sh - keep an sdb-over-TCP device from being dropped.
#
# The routed path to the TV board expires idle TCP sessions quickly
# (observed: the host sdb server drops the device after ~10 idle seconds),
# which kills long test windows that generate no sdb traffic (e.g. the
# memory_usage idle-settle countdown). This loop issues a trivial sdb
# command every few seconds so the connection stays up.
#
# Usage: tv_sdb_keepalive.sh <sdb_serial> [interval_sec]
# Runs forever; terminate by killing the process (TPMS.sh traps EXIT).

SDB_SERIAL=${1:-}
INTERVAL=${2:-5}

if [ -z "${SDB_SERIAL}" ]; then
	echo "[tv_keepalive] no sdb serial given, exit" >&2
	exit 1
fi

while true; do
	sdb -s "${SDB_SERIAL}" shell true > /dev/null 2>&1
	sleep "${INTERVAL}"
done
