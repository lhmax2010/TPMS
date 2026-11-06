#!/bin/bash

echo -e '\033[34m' ' '

function test_exit {
	echo -e '\033[0m' ' '
	exit $1
}

file_name=${0##*/}
test_name=${file_name%%\.*}

function usage {
	echo "usage: $file_name  RESULT_FILE"
}

echo "start $test_name"

if [ $# -lt 1 ]; then
	usage
	echo "not enough argument" 1>&2
	test_exit -1
fi

result_file=$1
result_file_path=${result_file%\/*}/

if [ ! -d ${result_file_path} ]; then
	mkdir -p $result_file_path
fi

function run_test {
	echo "function: ${FUNCNAME[0]}"

	#Enable Wifi and access to AP
	/usr/bin/enable_wifi.sh artik-tizen artik-tizen | /usr/bin/wifi_test
	echo "Disable lockscreen"
	/usr/bin/disable_lockscreen.sh

	#Check vconf value
	/usr/bin/vconftool get db/setting/screen_lock_type
	/usr/bin/vconftool get db/setting/lcd_backlight_normal

	/usr/bin/autoinput /opt/usr/tpms/file/unlock_lockscreen

	#Launch browser
	su - owner -c 'app_launcher -s org.tizen.browser __APP_SVC_URI__ https://chromium.github.io/octane/'
	sleep 32

	/usr/bin/autoinput /opt/usr/tpms/file/octane_touch_to_run
	sleep 128

	echo "Capture screen"
	XDG_RUNTIME_DIR=/run screenshooter-efl-util-32bit-armv7l -p $result_file -w 720 -h 1280
	echo "Result file : $result_file"

	su - owner -c 'app_launcher -k org.tizen.browser'

	echo "Enable lockscreen"
	/usr/bin/enable_lockscreen.sh
}

run_test
echo "end $test_name"

test_exit 0
