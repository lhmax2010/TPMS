#!/bin/bash

echo "============ enter download mode ============"

${COMMON_DIR}/sdb_shell.sh "reboot -f"

./connect2.sh /dev/ttyUSB0 115200

sleep 5

echo " "

lsusb

sleep 1

echo "============ download image ============"

lthor $1

sleep 80

