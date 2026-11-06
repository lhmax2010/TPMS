#!/bin/bash

#Boot idle memory test part
BOOT_IDLE=100
APP_LAUNCH_DELAY=1

#echo "Now waiting ${BOOT_IDLE}secs for system being stablized."
sleep $BOOT_IDLE

#BOOT_IDLE_FREEMEM=$(memps -a 2> /dev/null | grep "Used (Mem)" | awk '{print $3 }')

#App Launch test part

APP_NUM=0
while read APP_ID_LINE; do
	APP_ID=$(echo $APP_ID_LINE | awk '{print $1}')

	# Kill App. if it is already running #
	PID=$(app_launcher -S | grep "(^|\s)\K$APP_ID(?=\s|$)" | awk -F '(' '{print $2}' | awk -F ')' '{print $1}')
	if [ -n "$PID" ]; then
		app_launcher -k "$APP_ID" > /dev/null
	fi

	PREV_PID[$APP_NUM]=0

	COLD_LAUNCH[$APP_NUM]=0
	ELAPSED_LAUNCH[$APP_NUM]=0
	RESUME[$APP_NUM]=0
	ELAPSED_RESUME[$APP_NUM]=0

	APP_ID_LIST[$APP_NUM]=$APP_ID

	APP_NUM=$((APP_NUM + 1))
done < app_list.txt
TOTAL_APPS=$APP_NUM

sleep 10

#echo "TIME	APPID				AVAIL	FREE	CMAFREE	LKSM-sharing	LKSM-shared	ZRAM-original	ZRAM-used	LMK-Killed	LMK-Reclaimed	OOM-Killed	MEMPS-pss	MEMPS-rss"
START_TIME=$(date +%s)
LMK_TOTAL=0
OOM_TOTAL=0
LMK_REC_TOTAL=0
while read CURID; do	
	ITER=$((ITER + 1))
	APP_ID=${APP_ID_LIST[$CURID]}
	TIME_REAL=`(time (app_launcher -s "$APP_ID" > /dev/null) 2>&1) | awk 'NR == 2 {print $2}'`
	LAUNCH_SUCCESS=$(app_launcher -S | grep -P "(^|\s)\K$APP_ID(?=\s|$)")
	if [ -z "$LAUNCH_SUCCESS" ]; then
		echo "ERROR: failed to app_launcher, iter=$ITER, app: $APP_ID" > /dev/null
		continue
	fi

	PID=$(app_launcher -S | grep -P "(^|\s)\K$APP_ID(?=\s|$)" | tail -n1 | awk -F '(' '{print $2}' | awk -F ')' '{print $1}')

	if [ -z "$PID" ]; then
		echo "ERROR: failed to get pid, iter=$ITER, app: $APP_ID" > /dev/null
		continue
	fi

	sleep $APP_LAUNCH_DELAY

	TIME_RAW=$(echo $TIME_REAL | awk -F 'm' '{print $2}')
	TIME_SEC=$(echo $TIME_RAW | awk -F 's' '{print $1}')

	if [ $PID -ne ${PREV_PID[$CURID]} ]; then
		T1=${COLD_LAUNCH[$CURID]}
		COLD_LAUNCH[$CURID]=$((T1 + 1))
		PREV_PID[$CURID]=$PID

		T1=${ELAPSED_LAUNCH[$CURID]}
		T2=$(echo $T1 $TIME_SEC | awk '{print $1 + $2}')
		ELAPSED_LAUNCH[$CURID]=$T2

		MODE="Cold"
		CTIME=$TIME_SEC
		RTIME=0
	else
		T1=${RESUME[$CURID]}
		RESUME[$CURID]=$((T1 + 1))

		T1=${ELAPSED_RESUME[$CURID]}
		T2=$(echo $T1 $TIME_SEC | awk '{print $1 + $2}')
		ELAPSED_RESUME[$CURID]=$T2

		MODE="Resume"
		CTIME=0
		RTIME=$TIME_SEC
	fi
	
	CUR_TIME=$(date +%s)
	ELAPSED=$(($CUR_TIME - $START_TIME))

	MEM_INFO=$(cat /proc/meminfo)
	MEM_AVAIL=$(echo "$MEM_INFO" | grep MemAvailable | awk '{print $2}')
	MEM_FREE=$(echo "$MEM_INFO" | grep MemFree | awk '{print $2}')
	MEM_CMAFREE=$(echo "$MEM_INFO" | grep CmaFree | awk '{print $2}')
	
	if [ -d "/sys/kernel/mm/ksm/" ]; then
		LKSM_SHARED=$(cat /sys/kernel/mm/ksm/pages_shared)
		LKSM_SHARING=$(cat /sys/kernel/mm/ksm/pages_sharing)
	else
		LKSM_SHARED=0
		LKSM_SHARING=0
	fi

	ZRAM_STAT=$(cat /sys/block/zram0/mm_stat)
	ZRAM_ORIGINAL=$(echo $ZRAM_STAT | awk '{print $1}')
	ZRAM_USED=$(echo $ZRAM_STAT | awk '{print $3}')

	OOM_STAT=$(dmesg -c | grep "Memory cgroup out of memory:" | awk -F "memory:" '{ print $2}')

	if [ -n "$OOM_STAT" ]; then
		OOM_KILLED=$(echo "$OOM_STAT" | wc -l)

		OOM_TOTAL=$((${OOM_TOTAL} + ${OOM_KILLED}))
	else
		OOM_KILLED=0
	fi

	LMK_STAT=$(dlogutil RESOURCED -d | grep "Done" | awk -F '> ' '{ print $2 }')
	if [ -n "$LMK_STAT" ]; then
		LMK_CURS=$(echo "$LMK_STAT" | wc -l)
		LMK_KILLED=0
		LMK_RECLAIM=0 
		for i in $(seq 1 $LMK_CURS); do
			LMK_LINE=$(echo "$LMK_STAT" | head -n${i} | tail -1)
			
			LMK_KILLED_LINE=$(echo "$LMK_LINE" | awk '{print $4}')
			LMK_RECLAIM_LINE=$(echo "$LMK_LINE" | awk '{print $6}' | awk -F"=" '{print$2}' | awk -F"M" '{print $1}')

			LMK_KILLED=$((${LMK_KILLED} + ${LMK_KILLED_LINE}))
			LMK_RECLAIM=$((${LMK_RECLAIM} + ${LMK_RECLAIM_LINE}))
		done

		LMK_TOTAL=$((${LMK_TOTAL} + ${LMK_KILLED}))
		LMK_REC_TOTAL=$((${LMK_REC_TOTAL} + ${LMK_RECLAIM}))
		dlogutil -c
	else
		LMK_KILLED=0
		LMK_RECLAIM=0
	fi

	#MEMPS_STAT=$(memps -a 2> /dev/null)
	#STAT_LINE=$(echo "$MEMPS_STAT" | grep "TOTAL:" -n -m 1 | awk -F ":" '{print $1 + 1}')
	#STAT_RAW=$(echo "$MEMPS_STAT" | tail -n+${STAT_LINE} | head -n1)
	#MEMPS_RSS=$(echo "$STAT_RAW" | awk '{print $3}')
	#MEMPS_PSS=$(echo "$STAT_RAW" | awk '{print $4}')

	#echo "$ELAPSED	$APP_ID	$MEM_AVAIL	$MEM_FREE	$MEM_CMAFREE	$LKSM_SHARING	$LKSM_SHARED	$ZRAM_ORIGINAL	$ZRAM_USED	$LMK_KILLED	$LMK_RECLAIM	$OOM_KILLED	$MEMPS_PSS	$MEMPS_RSS"

	sleep $APP_LAUNCH_DELAY

done < scenario.txt

APP_NUM=0
TOTAL_AVG_SUM=0
TOTAL_COLD_SUM=0
TOTAL_RESUME_SUM=0
while read APP_ID_LINE; do
	APP_ID=$(echo $APP_ID_LINE | awk '{print $1}')

	LAUNCHED=$((${COLD_LAUNCH[$APP_NUM]} + ${RESUME[$APP_NUM]}))
	if [ $LAUNCHED -eq 0 ]; then
		TOTAL_AVG=0	
	else
		TOTAL_AVG=$(echo ${ELAPSED_LAUNCH[$APP_NUM]} ${ELAPSED_RESUME[$APP_NUM]} ${COLD_LAUNCH[$APP_NUM]} ${RESUME[$APP_NUM]} | awk '{print ($1 + $2) / ($3 + $4)}')
	fi
	
	#LAUNCH_AVG=$(echo ${ELAPSED_LAUNCH[$APP_NUM]} ${COLD_LAUNCH[$APP_NUM]} | awk '{print $1 / $2}')
	#if [ ${RESUME[$APP_NUM]} -ne 0 ]; then
	#	RESUME_AVG=$(echo ${ELAPSED_RESUME[$APP_NUM]} ${RESUME[$APP_NUM]} | awk '{print $1 / $2}')
	#else
	#	RESUME_AVG=0
	#fi
	
	TOTAL_AVG_SUM=$(echo ${TOTAL_AVG_SUM} ${TOTAL_AVG} | awk '{print $1 + $2}')
	TOTAL_COLD_SUM=$((${TOTAL_COLD_SUM} + ${COLD_LAUNCH[$APP_NUM]}))
	TOTAL_RESUME_SUM=$((${TOTAL_RESUME_SUM} + ${RESUME[$APP_NUM]}))

	#echo "$APP_NUM	$APP_ID			${COLD_LAUNCH[$APP_NUM]}	${RESUME[$APP_NUM]}	$TOTAL_AVG	$LAUNCH_AVG	$RESUME_AVG"
	APP_NUM=$((APP_NUM + 1))
done < app_list.txt

#echo "${BOOT_IDLE_FREEMEM}"
echo "${LMK_TOTAL},${OOM_TOTAL},${LMK_REC_TOTAL},${TOTAL_AVG_SUM},${TOTAL_COLD_SUM},${TOTAL_RESUME_SUM}"

