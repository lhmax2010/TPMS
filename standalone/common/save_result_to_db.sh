#!/bin/bash
#
# save_result_to_db.sh - save a TPMS perfpublisher.xml into the TPMS DB.
#
# The build number is assigned automatically as max(existing build for the
# job)+1, so results can be archived without manual bookkeeping.
#
# Usage:
#   save_result_to_db.sh <full_profile> [xml_file]
#     full_profile: e.g. 10.0-tv-kantsu2e (used as DB job_name)
#     xml_file    : default <repo>/standalone/workspace/<full_profile>/now_testing/perfpublisher.xml
#
# Env:
#   TPMS_DB           - DB file path (default: <repo>/db/tpms.db)
#   TPMS_SKIP_DB_SAVE - set to 1 to no-op (useful for throwaway test runs)
#
# Exit code: 0 = saved or intentionally skipped, 1 = error

FULL_PROFILE=${1:-}
XML_FILE=${2:-}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STANDALONE_DIR="$(dirname "${SCRIPT_DIR}")"
REPO_DIR="$(dirname "${STANDALONE_DIR}")"

DB_FILE=${TPMS_DB:-${REPO_DIR}/db/tpms.db}
DB_SCRIPT=${REPO_DIR}/db/tpms_db.py

log() {
	echo "[save_db] $*"
}

if [ "${TPMS_SKIP_DB_SAVE:-0}" == "1" ]; then
	log "TPMS_SKIP_DB_SAVE=1, skip"
	exit 0
fi

if [ -z "${FULL_PROFILE}" ]; then
	log "usage: save_result_to_db.sh <full_profile> [xml_file]"
	exit 1
fi

if [ -z "${XML_FILE}" ]; then
	XML_FILE=${STANDALONE_DIR}/workspace/${FULL_PROFILE}/now_testing/perfpublisher.xml
fi

if [ ! -f "${XML_FILE}" ]; then
	log "no result file ${XML_FILE}, skip"
	exit 0
fi

if [ ! -f "${DB_FILE}" ]; then
	log "no DB ${DB_FILE}, skip"
	exit 0
fi

NEXT_BUILD=$(python3 -c "
import sqlite3, sys
con = sqlite3.connect(sys.argv[1])
print(con.execute('SELECT COALESCE(MAX(build_number), 0) + 1 FROM performance_data WHERE job_name = ?', (sys.argv[2],)).fetchone()[0])
con.close()
" "${DB_FILE}" "${FULL_PROFILE}" 2>/dev/null)

if [ -z "${NEXT_BUILD}" ]; then
	log "failed to compute next build number for ${FULL_PROFILE}"
	exit 1
fi

log "saving ${XML_FILE} -> job=${FULL_PROFILE} build=${NEXT_BUILD} db=${DB_FILE}"
python3 "${DB_SCRIPT}" --save "${XML_FILE}" --job "${FULL_PROFILE}" --build "${NEXT_BUILD}" --db "${DB_FILE}"
