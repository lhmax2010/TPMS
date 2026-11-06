#!/bin/bash

wifi_ap_ssid=$1
wifi_ap_passwd=$2

function usage {
	echo "usage: $file_name  WIFI_AP_SSID WIFI_AP_PASSWD"
}

function test_exit {
	echo -e '\033[0m' ' '
	exit $1
}

if [ $# -lt 2 ]; then
	usage
	echo "not enough argument" 1>&2
	test_exit -1
fi

echo -e
sleep 2
echo -e 1
sleep 2
echo -e 3
sleep 3
echo -e 9
sleep 10
echo -e b
sleep 10
echo -e c
sleep 5
echo $wifi_ap_ssid
sleep 5
echo $wifi_ap_passwd
sleep 10
echo b
sleep 2
echo 0
