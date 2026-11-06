#!/bin/bash
#
# TPMS Trigger Script - 이미지 변경 감지 후 테스트 Job 트리거
#
# Jenkins Execute Shell에 아래 내용을 직접 붙여넣어 사용합니다.
# PROFILE과 TIZEN_VERSION을 프로파일에 맞게 수정하세요.
#
# [Jenkins 빌드 후 조치]
#   Projects to build         : <version>-<profile> (예: 10.0-unified-rpi-32bit)
#   Trigger when build is     : Stable
#   Trigger build without params : ✅
#   Parameters from properties file : trigger.param
#   Don't trigger if any files are missing : ✅
#
set -e

# ── Profile 설정 (프로파일별로 수정) ────────────────────────
PROFILE=unified-rpi-toolchain-32bit
TIZEN_VERSION=11.0



# ── 경로 설정 ───────────────────────────────────────────────
ROOT_PATH="${TPMS_ROOT_PATH:-/var/lib/jenkins/work/github/TPMS-standalone}"
TPMS_DATA_DIR="${TPMS_DATA_DIR:-/var/lib/jenkins/tpms-data}"
STANDALONE_DIR="${ROOT_PATH}/standalone"
CFG_PATH="${STANDALONE_DIR}/testprofiles.cfg"
FULL_PROFILE="${TIZEN_VERSION}-${PROFILE}"

MD5SUMS_DIR="${TPMS_DATA_DIR}/md5sums"
CURR_MD5SUMS="${MD5SUMS_DIR}/${FULL_PROFILE}.MD5SUMS"
TEMP_MD5SUMS="${MD5SUMS_DIR}/${FULL_PROFILE}.MD5SUMS_temp"

mkdir -p ${MD5SUMS_DIR}

# 이전 실행의 workspace 파일 삭제 (변경 시에만 trigger.param 새로 생성됨)
rm -f ${WORKSPACE}/*

# ── testprofiles.cfg에서 MD5SUMS URL 가져오기 ───────────────
MD5SUMS_URL=$(awk -v section="[${FULL_PROFILE}]" '
    $0==section {in_section=1; next}
    /^\[/ {in_section=0}
    in_section && /^buildxml_url[ ]*=/ {
        sub(/^buildxml_url[ ]*=[ ]*/, "")
        print
        exit
    }
' ${CFG_PATH})
if [ ${#MD5SUMS_URL} = 0 ]; then
    echo "Fail! Can not get buildxml_url from ${CFG_PATH}"
    exit 1
fi


echo "MD5SUMS URL: ${MD5SUMS_URL}"

# ── MD5SUMS를 임시 파일로 다운로드 ──────────────────────────
rm -f ${TEMP_MD5SUMS}

http_proxy="http://10.112.1.184:8080" wget --no-cache --no-verbose -O ${TEMP_MD5SUMS} ${MD5SUMS_URL}


if [ ! -f "${TEMP_MD5SUMS}" ]; then
    echo "MD5SUMS file does not exist"
    exit 1
fi

# "Object not found" 체크
exist_error=$(cat ${TEMP_MD5SUMS} | grep "Object not found" | wc -l)
if [ $exist_error -gt 0 ]; then
    echo "MD5SUMS file does not exist on server"
    rm -f ${TEMP_MD5SUMS}
    exit 1
fi

# ── 기존 MD5SUMS와 비교 ─────────────────────────────────────
if [ -f ${CURR_MD5SUMS} ]; then
    diff_result=$(diff ${TEMP_MD5SUMS} ${CURR_MD5SUMS} | wc -l)
    if [ $diff_result -gt 0 ]; then
        echo "Hash file has been changed. Triggering test job."
        mv -f ${TEMP_MD5SUMS} ${CURR_MD5SUMS}
        echo "SNAPSHOT_ID=latest" > ${WORKSPACE}/trigger.param
        echo "TEST_ONLY=false" >> ${WORKSPACE}/trigger.param
    else
        echo "Hash file not changed. Skip."
        rm -f ${TEMP_MD5SUMS}
        exit 0
    fi
else
    echo "First time. Triggering test job."
    mv -f ${TEMP_MD5SUMS} ${CURR_MD5SUMS}
    echo "SNAPSHOT_ID=latest" > ${WORKSPACE}/trigger.param
    echo "TEST_ONLY=false" >> ${WORKSPACE}/trigger.param
fi
