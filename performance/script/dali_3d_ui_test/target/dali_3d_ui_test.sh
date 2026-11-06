#!/bin/bash

echo -e '\033[34m' ' '

function test_exit {
	echo -e '\033[0m' ' '
	exit $1
}

file_name=${0##*/}
# UEP pipe-mode fallback: when executed via `cat x.sh | bash -s --`,
# $0 is "bash", so derive test_name from the injected env var instead.
test_name=${TPMS_TEST_NAME:-${file_name%%\.*}}

function usage {
	echo "usage: $file_name MODE[install|run] PKG_INFO_FILE RESULT_PATH"
}

echo "start $test_name"

if [ $# -lt 3 ]; then
	usage
	echo "not enough argument" 1>&2
	test_exit -1
fi

mode=$1
pkg_info_file=$2
result_path=$3

if [[ $result_path != /* ]] || [[ $pkg_info_file != /* ]]; then
	echo "file and path must be absolute path" 1>&2
	test_exit -1
fi

if [ ! -e ${pkg_info_file} ]; then
	usage
	echo "no package list file" 1>&2
	test_exit -1
fi

pkg_file_path=${pkg_info_file%\/*}/

if [[ $result_path != */ ]]; then
	result_path=$result_path/
fi

if [ ! -d ${result_path} ]; then
	mkdir -p $result_path
fi

#remove previous result
while read line; do
	# ignore comment
	if [[ ${line} == \#* ]]; then
		continue
	fi
	pkg_name=$(echo $line | awk -F' ' '{ print $1 }')
	previous_result_file=${result_path}"enlightenment_info_"${pkg_name}".txt"
	if [ -e ${previous_result_file} ]; then
		rm $previous_result_file
	fi
done < $pkg_info_file

ENLIGHTENMENT_INFO=enlightenment_info

function func_install {
	echo "function: ${FUNCNAME[0]}"

	#check vconf value
	/usr/bin/vconftool get db/setting/screen_lock_type
	/usr/bin/vconftool get db/setting/lcd_backlight_normal

	# run test
	while read line; do
		# ignore comment
		if [[ ${line} == \#* ]]; then
			continue
		fi

		pkg_name=$(echo $line | awk 'BEGIN { FS = "[ \t\n]+" } { print $1 }')
		pkg_file=$(echo $line | awk 'BEGIN { FS = "[ \t\n]+" } { print $2 }')
		pkg_exe=$(echo $line | awk 'BEGIN { FS = "[ \t\n]+" } { print $3 }')

		echo pkg_name=$pkg_name
		echo pkg_file=$pkg_file
		echo pkg_exe=$pkg_exe

		# TV: `tpk-backend --preload` hangs on kantsu2e (caused a 90s timeout
		# + forced reboot in the first run). The dali-demo package is already
		# installed via rpm by standalone.py, so skip the mobile-era preload
		# when the app is present.
		if pkgcmd -l 2>/dev/null | grep -q "$pkg_name"; then
			echo "$pkg_name already installed, skip tpk-backend preload"
		else
			chsmack -e "System::Privileged" /usr/bin/tpk-backend
			tpk-backend --preload -y $pkg_name
			chsmack -e "System" /usr/bin/tpk-backend
		fi

	done < $pkg_info_file

	#set up vconf to disable lockscreen & display timeout
	/usr/bin/vconftool set -t int db/setting/screen_lock_type 0 -rf
	#/usr/bin/vconftool set -t int db/setting/lcd_backlight_normal 600 -rf -s tizen::vconf::setting::admin -g 6514
	/usr/bin/vconftool set -t int db/setting/lcd_backlight_normal "600" -f
	sleep 1
	sync

	#check vconf value
	/usr/bin/vconftool get db/setting/screen_lock_type
	/usr/bin/vconftool get db/setting/lcd_backlight_normal
}

function func_run {
	echo "function: ${FUNCNAME[0]}"

	# VD-image standard: capture logs via vlog (vlogutil), not dlog (dlogutil).
	# The vlog ring buffer cannot be cleared, and timespan filtering only
	# works in stream mode, so emulate "clear" by marking the current uptime
	# and "dump" by reading back only the elapsed window with `vlogutil -t`.
	# Fall back to dlogutil on images without vlogutil.
	if command -v vlogutil >/dev/null 2>&1; then
		LOG_CAPTURE=vlog
		LOG_TS0=$(cut -d' ' -f1 /proc/uptime)
		log_dump() {
			local now span
			now=$(cut -d' ' -f1 /proc/uptime)
			span=$(( ${now%.*} - ${LOG_TS0%.*} + 3 ))
			[ $span -lt 1 ] && span=1
			vlogutil -t "$span" 2>/dev/null
		}
	else
		LOG_CAPTURE=dlog
		log_dump() { dlogutil -v threadtime -d 2>/dev/null; }
	fi

	#check vconf value
	/usr/bin/vconftool get db/setting/screen_lock_type
	/usr/bin/vconftool get db/setting/lcd_backlight_normal

	#We need to change process label of current shell to launch application
	echo System > /proc/self/attr/current

	# run test
	while read line; do
		# ignore comment
		if [[ ${line} == \#* ]]; then
			continue
		fi

		pkg_name=$(echo $line | awk 'BEGIN { FS = "[ \t\n]+" } { print $1 }')
		pkg_file=$(echo $line | awk 'BEGIN { FS = "[ \t\n]+" } { print $2 }')
		pkg_exe=$(echo $line | awk 'BEGIN { FS = "[ \t\n]+" } { print $3 }')

		echo pkg_name=$pkg_name
		echo pkg_file=$pkg_file
		echo pkg_exe=$pkg_exe

		# kill previous running process
		pid=$(ps -ef | pgrep -f $pkg_name)
		echo "pid=$pid"
		if [ "$pid" != "" ]; then
			echo "$pkg_name is already running. kill this one"
			kill -9 $pid
		fi

		pid=$(ps -ef | pgrep -f $ENLIGHTENMENT_INFO)
		echo "pid=$pid"
		if [ "$pid" != "" ]; then
			echo "$ENLIGHTENMENT_INFO is already running. kill this one"
			kill -9 $pid
		fi

		#logging
		result_file=${result_path}"enlightenment_info_${pkg_name}.txt"
		$ENLIGHTENMENT_INFO -fps > $result_file&

		# launch app
		su - owner -c "AUL_APPID=$pkg_name XDG_RUNTIME_DIR=/run DALI_THREADING_MODE=0 $pkg_exe --use-imageview -t30"

		# kill process
		pid=$(ps -ef | pgrep -f $pkg_name)
		echo "pid=$pid"
		if [ "$pid" != "" ]; then
			echo "kill $pkg_name"
			kill -9 $pid
		fi

		pid=$(ps -ef | pgrep -f $ENLIGHTENMENT_INFO)
		echo "pid=$pid"
		if [ "$pid" != "" ]; then
			echo "kill $ENLIGHTENMENT_INFO"
			kill $pid
		fi

		sleep 1
		sync

		extra_result=${result_path}"dlog_"$test_name"_"${pkg_name}".txt"
		if [ -e ${extra_result} ]; then
			rm $extra_result
			sync
		fi

		# get dlog (vlog on VD images)
		log_dump > $extra_result
		sync

	done < $pkg_info_file

	#set up vconf to enable lockscreen
	/usr/bin/vconftool set -t int db/setting/screen_lock_type 1 -rf
	sleep 1
	sync

	#recheck vconf value
	/usr/bin/vconftool get db/setting/screen_lock_type
	/usr/bin/vconftool get db/setting/lcd_backlight_normal
}

# check crash directory
if [ -e /opt/share/crash/dump ]; then
	set -x
	ls -l /opt/share/crash/dump
	set +x
fi

if [[ $mode == "install" ]]; then
	func_install
elif [[ $mode == "run" ]]; then
	func_run
else
	usage
	echo "invalid mode" 1>&2
	mest_exit -1

fi

echo "end $test_name"

test_exit 0
