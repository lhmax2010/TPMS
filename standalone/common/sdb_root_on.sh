#!/bin/bash

rm -f ${WORKSPACE_DIR}/Terminate_Test.txt

sdb start-server
#sdb devices

#exist_device=$(sdb devices | grep $sdb_serial | wc -l)
exist_device=$(sdb devices | awk -v sdb_serial=$SDB_SERIAL 'BEGIN{count=0} {if($1==sdb_serial) {count += 1} } END {printf "%d", count}')

#sdb_serial=$(sdb devices | awk -v profile=$profile 'BEGIN{count=0;} {if($3==profile) {count += 1; serial=$1}} END {if(count > 1) {printf "-2"} else if(count==1) {printf "%s", serial} else {printf "-1"} }' )

#echo exist_device : $exist_device

if [ $exist_device == 0 ]; then
	echo "================================================="
	echo "There is no device : $SDB_SERIAL"
	echo "================================================="
	echo "sdb_root_on.sh : There is no device : $SDB_SERIAL" > ${WORKSPACE_DIR}/Terminate_Test.txt
	exit 0
elif [ $exist_device -gt 1 ]; then
	echo "================================================="
	echo "There are two or more device : $SDB_SERIAL"
	echo "================================================="
	echo "sdb_root_on.sh : There are two or more device : $SDB_SERIAL" > ${WORKSPACE_DIR}/Terminate_Test.txt
	exit 0
fi

#echo "sdb -s $SDB_SERIAL root on"

sdb -s $SDB_SERIAL root on

# temp
sdb -s $SDB_SERIAL shell mount -o remount, rw /
