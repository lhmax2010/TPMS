#!/bin/bash

profile=$1

#sdb devices | awk 'BEGIN{count= 0} {if($3=="TW1") {count += 1; serial=$1}} END {if(count==0) {printf "There is no TW1\n"; exit 0} else if (count > 1) {printf "There are two or more TW1\n"; exit 0} else { printf "%s\n", serial"} }'
#sdb devices | awk -v profile=$profile 'BEGIN{count=0;} {if($3==profile) {count += 1; serial=$1}} END {if(count > 1) {printf "There are two or more %s\n", profile; exit 0} else if(count==1) {printf "%s\n", serial} else {printf "There is no %s\n", profile; exit 0} }'

sdb start-server
sdb devices
sdb_serial=$(sdb devices | awk -v profile=$profile 'BEGIN{count=0;} {if($3==profile) {count += 1; serial=$1}} END {if(count > 1) {printf "-2"} else if(count==1) {printf "%s", serial} else {printf "-1"} }' )

#echo $serial

if [ $sdb_serial == -1 ]; then
	echo "========================================"
	echo "There is no $profile"
	echo "========================================"
	echo "Terminate Test" > ./Terminate_Test.txt
	exit 0
elif [ $sdb_serial == -2 ]; then
	echo "========================================"
	echo "There are two or more $profile"
	echo "========================================"
	echo "Terminate Test" > ./Terminate_Test.txt
	exit 0
fi

echo "========================================"
echo "   $profile : $sdb_serial"
echo "========================================"

echo $sdb_serial > ./SDB_serial.txt
