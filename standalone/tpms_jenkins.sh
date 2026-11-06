#!/bin/bash
#
# TPMS Jenkins Execute Shell Script
#
# Jenkins Execute Shell에 아래 내용을 직접 붙여넣어 사용합니다.
# PROFILE과 TIZEN_VERSION을 프로파일에 맞게 수정하세요.
#
set -e

# ── Profile 설정 (프로파일별로 수정) ────────────────────────
PROFILE=unified-rpi-toolchain-32bit
TIZEN_VERSION=11.0



# ── 경로 설정 ───────────────────────────────────────────────
ROOT_PATH="${TPMS_ROOT_PATH:-/var/lib/jenkins/work/github/TPMS-standalone}"
STANDALONE_DIR="${ROOT_PATH}/standalone"
DB_DIR="${ROOT_PATH}/db"
DB_PATH="${DB_DIR}/tpms.db"
FULL_PROFILE="${TIZEN_VERSION}-${PROFILE}"

# ── 에러 로그 기록 함수 ─────────────────────────────────────
# Jenkins Console Output에 명확한 에러 메시지를 출력하고
# ${WORKSPACE}/error.txt에 기록하여 Archiving artifacts로 보존
log_error() {
	local msg="$1"
	echo "========================================"
	echo "ERROR: ${msg}"
	echo "========================================"
	echo "ERROR: ${msg}" > ${WORKSPACE}/error.txt
}

# ── Step 0: 디스크 공간 사전 체크 ──────────────────────────
# 디스크 공간 부족은 perfpublisher.xml 생성 실패의 주요 원인 중 하나
MIN_DISK_SPACE_MB=2048  # 2GB
AVAILABLE_DISK_MB=$(df -m "${ROOT_PATH}" | awk 'NR==2 {print $4}')
echo "Available disk space: ${AVAILABLE_DISK_MB} MB (minimum required: ${MIN_DISK_SPACE_MB} MB)"
if [ "${AVAILABLE_DISK_MB}" -lt "${MIN_DISK_SPACE_MB}" ]; then
	log_error "Insufficient disk space: ${AVAILABLE_DISK_MB} MB available, ${MIN_DISK_SPACE_MB} MB required. Free up disk space and retry."
	exit 1
fi

# ── Step 0-1: 이전 결과 정리 ─────────────────────────────
rm -f ${WORKSPACE}/*.*

cd ${STANDALONE_DIR}
rm -f log.log

# ── Step 1: 성능 측정 ──────────────────────────────────────
./TPMS.sh ${PROFILE} ${TIZEN_VERSION} $TEST_ONLY $SNAPSHOT_ID

# ── Step 2: 에러 확인 ──────────────────────────────────────
if [ -f "${STANDALONE_DIR}/workspace/Terminate_Test.txt" ]; then
	cat ${STANDALONE_DIR}/workspace/Terminate_Test.txt
	log_error "Test was terminated. Check Terminate_Test.txt for details."
	exit 1
fi

# ── Step 3: 결과를 workspace로 복사 ────────────────────────
cp -R ${STANDALONE_DIR}/workspace/${FULL_PROFILE}/now_testing/* ${WORKSPACE}

# ── Step 3-1: perfpublisher.xml 존재 여부 체크 ─────────────
# perfpublisher.xml이 없으면 DB 저장 단계에서 FileNotFoundError 발생
# 미리 체크하여 명확한 에러 메시지 출력
if [ ! -f "${WORKSPACE}/perfpublisher.xml" ]; then
	log_error "perfpublisher.xml not found in ${WORKSPACE}. The performance test (TPMS.sh) may have failed to generate it. Check disk space and test logs."
	exit 1
fi

# ── Step 4: DB 저장 ────────────────────────────────────────
cd ${DB_DIR}
python3 tpms_db.py --save ${WORKSPACE}/perfpublisher.xml \
    --job ${FULL_PROFILE} \
    --build ${BUILD_NUMBER} \
    --replace --db ${DB_PATH}

# ── Step 5: 웹 리포트 생성 (web server redirect) ───────────
SERVER_IP=$(hostname -I | awk '{print $1}')
WEB_SERVER_URL="http://${SERVER_IP}:9090"
REPORT_URL="${WEB_SERVER_URL}/api/report/${FULL_PROFILE}/${BUILD_NUMBER}"
TREND_URL="${WEB_SERVER_URL}/trend/${FULL_PROFILE}"

# 단일 빌드 상세 리포트 (web server로 redirect)
cat > ${WORKSPACE}/report.html << EOF
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>TPMS Report - ${FULL_PROFILE} #${BUILD_NUMBER}</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
iframe { width: 100%; height: 800px; border: none; }
</style>
</head>
<body>
<iframe src="${REPORT_URL}" frameborder="0" scrolling="auto"></iframe>
</body>
</html>
EOF

# 트렌드 페이지 (web server로 redirect)
cat > ${WORKSPACE}/trend.html << EOF
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>TPMS Trend - ${FULL_PROFILE}</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
iframe { width: 100%; height: 800px; border: none; }
</style>
</head>
<body>
<iframe src="${TREND_URL}" frameborder="0" scrolling="auto"></iframe>
</body>
</html>
EOF

echo "========================================"
echo " TPMS pipeline complete"
echo "   Profile: ${FULL_PROFILE}"
echo "   Build:   ${BUILD_NUMBER}"
echo "   DB:      ${DB_PATH}"
echo "   Report:  ${REPORT_URL}"
echo "   Trend:   ${TREND_URL}"
echo "========================================"
