#!/bin/bash

echo "============  sdb enable  ============"

./connect.sh /dev/ttyUSB0 115200

sleep 30

echo "============ check connect artik ============"

artik_count=$(sdb devices | grep artik | wc -l)

if [ $artik_count = "0" ]
then
    echo -e "\033[31mNot connected ARTIK device\033[0m"
    exit
elif [ $artik_count != "1" ]
then
    echo -e "\033[31mconnected duplicate ARTIK devices\033[0m"
    exit
else
    echo -e "\033[34mconnected one ARTIK device\033[0m"
fi

serial=$(sdb devices | grep artik | awk '{printf "%s", $1}')

echo $serial

sdb -s $serial root on

# temp
sdb -s $serial shell mount -o remount, rw /

sdb -s $serial push boot-animation.service /usr/lib/systemd/system

sdb -s $serial shell sync

#sdb -s $serial shell reboot -f
