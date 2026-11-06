#!/bin/bash

SERIAL="$2"
if [ -z "$SERIAL" ]; then
	SERIAL="rpi4" 
fi

SCRIPT_HOME=$(dirname "$(readlink -f "$0")")
RESULT_DIR=$1
if [ -z "$RESULT_DIR" ]; then
	RESULT_DIR=$SCRIPT_HOME
fi
OUTFILE="${RESULT_DIR}/applaunch_memstress_result.txt"

echo $SCRIPT_HOME

TIMEOUT=180
SLEPT=0
while true; do
	conn=$(sdb devices | grep $SERIAL)
	if [ -n "$conn" ]; then
		sleep 5
		break
	fi
	sleep 1
	SLEPT=$(($SLEPT + 1))
	if [ $SLEPT -gt $TIMEOUT ]
	then
		echo "Connection failed (timed out)"
		exit -1
	fi
done

SERIAL=$(echo $conn | awk '{print $1}')

sdb -s $SERIAL shell /root/run.sh | tee ${OUTFILE}
sleep 5
