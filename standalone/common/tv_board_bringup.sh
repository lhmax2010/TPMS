#!/bin/bash
#
# tv_board_bringup.sh - idempotent bringup for sdb-over-TCP TV boards (kantsu2e).
#
# Ensures, in order:
#   1. board is ping-reachable
#   2. sdbd is listening on TCP port 26101 (auto-repaired over SSH if not)
#   3. host sdb server is connected to the board (auto-repaired over SSH
#      when the port is open but the sdb handshake keeps failing)
#   4. sdb root access is enabled
#   5. eco-solution auto power off / energy saving is disabled (vconf keys,
#      persist across reboots; only written when a key is not 0 yet)
#   6. /usr/lib/tpms-syslibs/libsystemd-shared-244.so exists on the board
#      (pushed from target_installable when missing; warning only on failure)
#
# The script is a near no-op when the board is already set up, so it is safe
# to run before every test session. The SSH repair step is only needed after
# the TV image is (re)flashed.
#
# Usage:
#   tv_board_bringup.sh [dev_ip]
#
# Optional env:
#   TIZEN_PROFILE / TIZEN_VERSION - used to read dev_ip from testprofiles.cfg
#                                   when no argument is given
#                                   (default: tv-kantsu2e / 10.0)
#   TV_DEV_IP                     - target IP override (positional arg wins)
#   TV_BOARD_SSH_USER             - board SSH user (default: root)
#   TV_BOARD_SSH_PASSWORD         - board SSH password (default: tizen);
#                                   set to empty string to use ssh key auth
#   WORKSPACE_DIR                 - Terminate_Test.txt is written here on
#                                   fatal failure (TPMS.sh convention)
#
# Exit code: 0 = board ready, 1 = fatal failure (sdb cannot be used)

TIZEN_PROFILE=${TIZEN_PROFILE:-tv-kantsu2e}
TIZEN_VERSION=${TIZEN_VERSION:-10.0}
TV_BOARD_SSH_USER=${TV_BOARD_SSH_USER:-root}
TV_BOARD_SSH_PASSWORD=${TV_BOARD_SSH_PASSWORD:-tizen}

SDBD_PORT=26101
SSH_PORT=22
CONNECT_RETRIES=5
CONNECT_RETRY_INTERVAL=10
# Escalate to the SSH repair after this many failed "sdb connect" attempts
# (handles "port open but sdbd broken", which the port probe cannot see).
SSH_REPAIR_AFTER_FAILED_CONNECTS=2

SYSLIBS_DST=/usr/lib/tpms-syslibs/libsystemd-shared-244.so

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STANDALONE_DIR="$(dirname "${SCRIPT_DIR}")"
REPO_DIR="$(dirname "${STANDALONE_DIR}")"

log() {
	echo "[tv_bringup] $*"
}

fatal() {
	log "FATAL: $*"
	if [ -n "${WORKSPACE_DIR:-}" ] && [ -d "${WORKSPACE_DIR}" ]; then
		echo "tv_board_bringup: $*" > "${WORKSPACE_DIR}/Terminate_Test.txt"
	fi
	exit 1
}

port_open() {
	# $1 = port; returns 0 if the TCP port on ${DEV_IP} accepts connections
	timeout 3 bash -c "</dev/tcp/${DEV_IP}/$1" 2>/dev/null
}

ssh_exec() {
	# UserKnownHostsFile=/dev/null: reflashed boards come back with a NEW
	# ssh host key; OpenSSH refuses password auth on key change even with
	# StrictHostKeyChecking=no, which would break the auto-repair path.
	# Acceptable here: lab tool talking to a test board over a trusted net.
	if [ -n "${TV_BOARD_SSH_PASSWORD}" ]; then
		sshpass -p "${TV_BOARD_SSH_PASSWORD}" ssh \
			-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
			-o ConnectTimeout=5 "${TV_BOARD_SSH_USER}@${DEV_IP}" "$@"
	else
		ssh -o BatchMode=yes -o StrictHostKeyChecking=no \
			-o UserKnownHostsFile=/dev/null \
			-o ConnectTimeout=5 "${TV_BOARD_SSH_USER}@${DEV_IP}" "$@"
	fi
}

detect_host_ip() {
	ip route get "${DEV_IP}" 2>/dev/null | \
		awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}'
}

# ssh_repair_sdbd - repair board-side sdbd over SSH. Covers both failure
# modes: (a) port 26101 closed (socket not listening, e.g. after reflash)
# and (b) port open but the sdb handshake fails (socket accepts TCP yet
# sdbd.service keeps dying: develop mode off / unit files changed on disk
# without daemon-reload / systemd start-limit-hit). Returns 0 when the SSH
# repair commands all ran through.
ssh_repair_sdbd() {
	HOST_IP=$(detect_host_ip)
	if [ -z "${HOST_IP}" ]; then
		HOST_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
	fi
	if [ -z "${HOST_IP}" ]; then
		log "WARNING: cannot determine host IP for buxton db/sdk/develop/ip"
		return 1
	fi
	log "enabling sdbd on board over SSH (develop ip = ${HOST_IP})"

	# daemon-reload: unit files/drop-ins may have changed on disk (systemd
	# then fails socket activation with "protocol" errors). reset-failed on
	# BOTH units: a start-limit-hit on sdbd_tcp.socket keeps the port dead
	# even after the service itself is fixed. restart instead of
	# "enable --now": --now is a no-op when the socket is active-but-broken.
	ssh_exec "systemctl daemon-reload && \
		buxton2ctl set-int32 system db/sdk/develop/mode 1 && \
		buxton2ctl set-string system db/sdk/develop/ip ${HOST_IP} && \
		systemctl enable sdbd_tcp.socket && \
		systemctl reset-failed sdbd.service sdbd_tcp.socket && \
		systemctl restart sdbd_tcp.socket" || return 1

	sleep 2
}

# ---------------------------------------------------------------------------
# 0. Resolve target board IP (positional arg > TV_DEV_IP env > testprofiles.cfg)
# ---------------------------------------------------------------------------
DEV_IP=${1:-${TV_DEV_IP:-}}
if [ -z "${DEV_IP}" ]; then
	DEV_IP=$(sed -nr "/^\[${TIZEN_VERSION}-${TIZEN_PROFILE}\]/ { :l /^dev_ip[ ]*=/ { s/.*=[ ]*//; p; q;}; n; b l;}" \
		"${STANDALONE_DIR}/testprofiles.cfg" | tr -d '[:space:]')
fi
if [ -z "${DEV_IP}" ]; then
	fatal "no dev_ip argument and no dev_ip found for [${TIZEN_VERSION}-${TIZEN_PROFILE}] in testprofiles.cfg"
fi

log "target board: ${DEV_IP} (profile ${TIZEN_VERSION}-${TIZEN_PROFILE})"

# ---------------------------------------------------------------------------
# 1. Board must be reachable on the network
# ---------------------------------------------------------------------------
if ! ping -c 2 -W 2 "${DEV_IP}" > /dev/null 2>&1; then
	fatal "board ${DEV_IP} does not respond to ping; check board power/network"
fi
log "ping ok"

# ---------------------------------------------------------------------------
# 2. sdbd must listen on 26101; repair over SSH after a reflash
# ---------------------------------------------------------------------------
# Tracks whether the SSH repair already ran in this session so the connect
# loop below escalates to it at most once.
ssh_repair_done=0
if ! port_open ${SDBD_PORT}; then
	log "sdbd port ${SDBD_PORT} is closed; trying board-side repair over SSH"
	if ! port_open ${SSH_PORT}; then
		fatal "sdbd port ${SDBD_PORT} closed and SSH port ${SSH_PORT} also unreachable; cannot auto-repair, check board manually"
	fi
	if [ -n "${TV_BOARD_SSH_PASSWORD}" ] && ! command -v sshpass > /dev/null 2>&1; then
		fatal "sshpass not installed; install it or set TV_BOARD_SSH_PASSWORD='' to use ssh key auth"
	fi

	# Repair logic moved into ssh_repair_sdbd(); adds daemon-reload,
	# reset-failed for sdbd_tcp.socket and a real socket restart.
	ssh_repair_done=1
	if ! ssh_repair_sdbd; then
		fatal "SSH repair failed on ${DEV_IP} (user ${TV_BOARD_SSH_USER})"
	fi

	sleep 3
	if ! port_open ${SDBD_PORT}; then
		fatal "sdbd port ${SDBD_PORT} still closed after SSH repair"
	fi
	log "sdbd port ${SDBD_PORT} is now open"
else
	log "sdbd port ${SDBD_PORT} already open"
fi

# ---------------------------------------------------------------------------
# 3. Connect host sdb server to the board
# ---------------------------------------------------------------------------
SDB_SERIAL="${DEV_IP}:${SDBD_PORT}"
connected=0
for i in $(seq 1 ${CONNECT_RETRIES}); do
	if sdb devices 2>/dev/null | awk -v s="${SDB_SERIAL}" '$1==s && $2=="device" {found=1} END{exit !found}'; then
		connected=1
		break
	fi
	# Port open but the sdb handshake keeps failing: sdbd is broken on the
	# board (develop mode off / stale unit config / start-limit-hit), which
	# the port_open() probe cannot see. Escalate to the same SSH repair once
	# per session, then keep retrying the connect.
	if [ ${i} -gt ${SSH_REPAIR_AFTER_FAILED_CONNECTS} ] && [ ${ssh_repair_done} -eq 0 ]; then
		ssh_repair_done=1
		if port_open ${SSH_PORT}; then
			if ssh_repair_sdbd; then
				log "sdbd repaired over SSH; resuming sdb connect"
			else
				log "WARNING: SSH repair attempt failed; continuing sdb connect retries"
			fi
		else
			log "WARNING: SSH port ${SSH_PORT} unreachable; cannot auto-repair, continuing sdb connect retries"
		fi
	fi
	log "sdb connect ${DEV_IP} (retry ${i}/${CONNECT_RETRIES})"
	sdb connect "${DEV_IP}" > /dev/null 2>&1
	sleep ${CONNECT_RETRY_INTERVAL}
done
if [ ${connected} -ne 1 ]; then
	fatal "sdb cannot connect to ${SDB_SERIAL} after ${CONNECT_RETRIES} retries"
fi
log "sdb device connected: ${SDB_SERIAL}"

# ---------------------------------------------------------------------------
# 4. Root access
# ---------------------------------------------------------------------------
# Retry with warm-up: right after a fresh "sdb connect", the exec channel is
# not warm yet (sdbd is socket-activated) and the first "id -u" probe can
# return empty/"closed", which used to abort the run with a false FATAL.
root_ok=0
for i in $(seq 1 5); do
	sdb -s "${SDB_SERIAL}" root on > /dev/null 2>&1
	sleep 2
	if [ "$(sdb -s "${SDB_SERIAL}" shell id -u 2>/dev/null | tr -d '\r' | head -n1)" == "0" ]; then
		root_ok=1
		break
	fi
	log "sdb root on not effective yet (retry ${i}/5)"
done
if [ ${root_ok} -ne 1 ]; then
	fatal "sdb root on failed for ${SDB_SERIAL}"
fi
log "sdb root access ok"

# ---------------------------------------------------------------------------
# 5. Eco-solution: keep the TV awake during long test sessions
# ---------------------------------------------------------------------------
# --- AI-generated section starts --[20261027-105500-e5c8f2]-
# --- Code Writer: Cline SR
# Long TPMS runs fail when the TV auto-powers-off / enters energy saving.
# These vconf keys persist across reboots, so each key is only written when
# it is not 0 yet (one-time setup per board, near no-op afterwards). A key
# that cannot be read (absent on a different image) is skipped silently; a
# key that refuses to stay 0 only raises a warning, matching the syslibs
# policy below - anti-sleep is best-effort, not a hard bringup gate.
# --- AI-generated section End --[20261027-105500-e5c8f2]-
ECO_KEYS="auto_power_off energy_saving no_signal_power_off no_signal_power_off_external"
eco_failed=""
for eco_key in ${ECO_KEYS}; do
	eco_path="db/menu/system/eco_solution/${eco_key}"
	# vconftool get output: "<path>, value = 0 (Int32)"
	eco_val=$(sdb -s "${SDB_SERIAL}" shell "vconftool get -t int ${eco_path}" 2>/dev/null | \
		tr -d '\r' | sed -nr 's/.*value = (-?[0-9]+).*/\1/p' | head -n1)
	if [ -z "${eco_val}" ] || [ "${eco_val}" == "0" ]; then
		continue
	fi
	sdb -s "${SDB_SERIAL}" shell "vconftool set -f -t int ${eco_path} 0" > /dev/null 2>&1
	eco_val=$(sdb -s "${SDB_SERIAL}" shell "vconftool get -t int ${eco_path}" 2>/dev/null | \
		tr -d '\r' | sed -nr 's/.*value = (-?[0-9]+).*/\1/p' | head -n1)
	if [ "${eco_val}" != "0" ]; then
		eco_failed="${eco_failed} ${eco_key}"
	fi
done
if [ -n "${eco_failed}" ]; then
	log "WARNING: failed to disable eco-solution keys:${eco_failed}; board may auto-sleep during long tests"
else
	log "eco-solution auto power off / energy saving disabled"
fi

# ---------------------------------------------------------------------------
# 6. tpms syslibs shim (only required by booting_time's systemd-analyze)
# ---------------------------------------------------------------------------
SYSLIBS_SRC="${REPO_DIR}/performance/target_installable/${TIZEN_VERSION}-${TIZEN_PROFILE}/booting_time_test/file/syslibs/libsystemd-shared-244.so"
if sdb -s "${SDB_SERIAL}" shell "ls ${SYSLIBS_DST}" 2>/dev/null | tr -d '\r' | grep -qx "${SYSLIBS_DST}"; then
	log "tpms syslibs already present on board"
elif [ ! -f "${SYSLIBS_SRC}" ]; then
	log "WARNING: ${SYSLIBS_DST} missing on board and no local copy at ${SYSLIBS_SRC}; booting_time_test may fail"
else
	log "installing tpms syslibs shim on board"
	# fresh TV images may mount / read-only; remount rw BEFORE mkdir/push
	sdb -s "${SDB_SERIAL}" shell "mount -o rw,remount /" > /dev/null 2>&1
	sdb -s "${SDB_SERIAL}" shell "mkdir -p $(dirname "${SYSLIBS_DST}")" > /dev/null 2>&1
	sdb -s "${SDB_SERIAL}" push "${SYSLIBS_SRC}" "${SYSLIBS_DST}" > /dev/null 2>&1
	sdb -s "${SDB_SERIAL}" shell "chsmack -a System::Shared ${SYSLIBS_DST}" > /dev/null 2>&1
	if sdb -s "${SDB_SERIAL}" shell "ls ${SYSLIBS_DST}" 2>/dev/null | tr -d '\r' | grep -qx "${SYSLIBS_DST}"; then
		log "tpms syslibs installed"
	else
		log "WARNING: failed to install ${SYSLIBS_DST}; booting_time_test may fail"
	fi
fi

log "board ${DEV_IP} is ready"
exit 0

