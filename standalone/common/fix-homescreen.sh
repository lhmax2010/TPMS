#!/bin/bash
#
# Tizen RPi Homescreen Crash Fix Script
#
# Problem: org.tizen.homescreen's libflutter_tizen_common.so references the old dali2 API
#          (Dali::Stage), causing a symbol lookup error crash with dali2 2.5.26.
# Solution: Replace libflutter_tizen_common.so with the latest flutter-tizen embedder release
#           (tag 0319ab5) where dali2 dependency has been completely removed.
#
# Usage: ./fix-homescreen.sh [--force]
#

set +e

# SDB_SERIAL이 설정된 경우 특정 디바이스 지정, 아니면 bare sdb
if [ -z "${SDB_SERIAL}" ]; then
    SDB_CMD="sdb"
else
    SDB_CMD="sdb -s ${SDB_SERIAL}"
fi

EMBEDDER_TAG="0319ab5"
EMBEDDER_URL="https://github.com/flutter-tizen/embedder/releases/download/${EMBEDDER_TAG}/tizen-6.0-arm.zip"
TARGET_LIB_PATH="/usr/apps/org.tizen.homescreen/lib/libflutter_tizen_common.so"
TMP_DIR="/tmp/fix-homescreen"

echo "============================================"
echo "  Tizen RPi Homescreen Crash Fix Script"
echo "============================================"
echo ""

# 1. Check sdb connection
echo "[1/6] Checking sdb connection..."
if ! ${SDB_CMD} devices 2>&1 | grep -q "device"; then
    echo "ERROR: No device connected to sdb."
    exit 1
fi
echo "  -> sdb connected"
echo ""

# 2. Check current status
echo "[2/6] Checking current homescreen status..."
BUILD_ID=$(${SDB_CMD} shell "cat /etc/tizen-release" 2>&1 | grep BUILD_ID | cut -d= -f2)
echo "  -> BUILD_ID: ${BUILD_ID}"

SYMBOL_ERROR=$(${SDB_CMD} shell "dlogutil -d 2>&1 | grep 'symbol lookup' | grep -v SDBD | tail -1" 2>&1 || true)
if echo "$SYMBOL_ERROR" | grep -q "symbol lookup error"; then
    echo "  -> Homescreen crash detected: symbol lookup error"
else
    RUNNER_COUNT=$(${SDB_CMD} shell "ps -ef | grep runner | grep -v grep | wc -l" 2>&1 | tr -d ' \r\n' || echo "0")
    if [ "${RUNNER_COUNT}" -gt 0 ] 2>/dev/null; then
        echo "  -> Homescreen is already running normally (${RUNNER_COUNT} runner process(es))"
        echo "  -> Use --force to reinstall anyway"
        if [ "$1" != "--force" ]; then
            exit 0
        fi
    fi
fi
echo ""

# 3. Download embedder
echo "[3/6] Downloading flutter-tizen embedder (tag: ${EMBEDDER_TAG})..."
mkdir -p "${TMP_DIR}"
if [ -f "${TMP_DIR}/libflutter_tizen_common.so" ]; then
    echo "  -> Using existing download: ${TMP_DIR}/libflutter_tizen_common.so"
else
    echo "  -> Downloading: ${EMBEDDER_URL}"
    curl -sL "${EMBEDDER_URL}" -o "${TMP_DIR}/tizen-6.0-arm.zip"
    unzip -o "${TMP_DIR}/tizen-6.0-arm.zip" libflutter_tizen_common.so -d "${TMP_DIR}" > /dev/null
    if [ ! -f "${TMP_DIR}/libflutter_tizen_common.so" ]; then
        echo "ERROR: Failed to download libflutter_tizen_common.so"
        exit 1
    fi
fi
echo "  -> Download complete: $(ls -la ${TMP_DIR}/libflutter_tizen_common.so | awk '{print $5}') bytes"
echo ""

# 4. Verify binary
echo "[4/6] Verifying binary (checking Dali::Stage symbol is absent)..."
if nm -D "${TMP_DIR}/libflutter_tizen_common.so" 2>/dev/null | grep -q "Stage"; then
    echo "  WARNING: Dali::Stage symbol found. The binary may be incorrect."
else
    echo "  -> Dali::Stage symbol absent (OK)"
fi
echo ""

# 5. Install to target
echo "[5/6] Installing libflutter_tizen_common.so to target..."
echo "  -> Pushing file..."
${SDB_CMD} push "${TMP_DIR}/libflutter_tizen_common.so" /tmp/libflutter_tizen_common.so 2>&1 | grep -v WARNING

echo "  -> Acquiring root access..."
${SDB_CMD} root on 2>&1 | grep -v "^$"

echo "  -> Remounting filesystem as read-write..."
${SDB_CMD} shell "mount -o remount,rw /" 2>&1 | grep -v "^$"

echo "  -> Backing up existing file..."
${SDB_CMD} shell "cp ${TARGET_LIB_PATH} ${TARGET_LIB_PATH}.bak 2>/dev/null || true" 2>&1 | grep -v "^$"

echo "  -> Installing new binary..."
${SDB_CMD} shell "cp /tmp/libflutter_tizen_common.so ${TARGET_LIB_PATH} && chmod 755 ${TARGET_LIB_PATH}" 2>&1 | grep -v "^$"

echo "  -> Installation complete"
echo ""

# 6. Restart homescreen
echo "[6/6] Restarting homescreen..."
${SDB_CMD} shell "killall -9 runner 2>/dev/null; killall -9 starter 2>/dev/null; sleep 2; /usr/bin/starter &" 2>&1 | grep -v "^$"

echo "  -> Waiting 5 seconds..."
sleep 5

# Verify result
echo ""
echo "============================================"
echo "  Verification"
echo "============================================"

RUNNER_PID=$(${SDB_CMD} shell "ps -ef | grep runner | grep -v grep" 2>&1 | head -1 | awk '{print $2}')
if [ -n "$RUNNER_PID" ]; then
    echo "  [OK] runner process running (PID: ${RUNNER_PID})"
else
    echo "  [FAIL] runner process is not running"
    echo "         Check log: ${SDB_CMD} shell \"dlogutil -d | grep 'symbol lookup'\""
    exit 1
fi

SYMBOL_CHECK=$(${SDB_CMD} shell "dlogutil -d 2>&1 | grep 'symbol lookup' | grep -v SDBD | tail -1" 2>&1 || true)
if echo "$SYMBOL_CHECK" | grep -q "symbol lookup error"; then
    echo "  [FAIL] symbol lookup error detected"
    echo "         Detail: ${SYMBOL_CHECK}"
    exit 1
else
    echo "  [OK] No symbol lookup error"
fi

echo ""
echo "============================================"
echo "  Homescreen crash fix complete!"
echo "============================================"
echo ""
echo "Note: The fix persists across reboots (stored on ext4 filesystem)."
echo "      However, re-flashing the Tizen image will restore the original binary,"
echo "      so you will need to run this script again."
