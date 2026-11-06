#!/bin/bash

if [ -z "$SERIAL" ]; then
	SERIAL="rpi4" 
fi
	
SCRIPT_HOME=$(dirname "$(readlink -f "$0")")
BIN="$1"

while true; do
	conn=$(sdb devices | grep $SERIAL)
	if [ -n "$conn" ]; then
		sleep 5
		break
	fi
	sleep 1
done

SERIAL=$(echo $conn | awk '{print $1}')
BOOTLOADER="${SCRIPT_HOME}/bootloader/${BIN}"

if [ -f "$BOOTLOADER" ]; then
	sdb -s $SERIAL root on
	sdb -s $SERIAL shell reboot download
	sleep 60
	lthor ${BOOTLOADER}
fi

echo "SUCCESS"
