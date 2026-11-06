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
	echo "usage: $file_name MODE[install|run] PKG_LIST_FILE RESULT_PATH"
}

echo "start $test_name"

if [ $# -lt 3 ]; then
	usage
	echo "not enough argument" 1>&2
	test_exit -1
fi

mode=$1
pkg_list_file=$2
result_path=$3

if [[ $result_path != /* ]] || [[ $pkg_list_file != /* ]]; then
	echo "file path must be absolute path" 1>&2
	test_exit -1
fi

if [ ! -e ${pkg_list_file} ]; then
	usage
	echo "no package list file" 1>&2
	test_exit -1
fi

pkg_file_path=${pkg_list_file%\/*}/

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
	previous_result_file=${result_path}"dlog_"${pkg_name}".txt"
	if [ -e ${previous_result_file} ]; then
		rm $previous_result_file
	fi
done < $pkg_list_file

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
		pkg_privileges=$(echo $line | awk 'BEGIN { FS = "[ \t\n]+" } { print $4 }')
		echo name=$pkg_name
		echo file=$pkg_file

		pid=$(ps -ef | pgrep -f $pkg_name)
		echo "pid=$pid"
		if [ "$pid" != "" ]; then
			echo "$pkg_name is already running. kill this one"
			kill -9 $pid
		fi

		#install
		installed=$(su - owner -c "pkgcmd -l" | grep $pkg_name)
		if [ "$installed" != "" ]; then
			echo "$pkg_name is already installed"
		else
			su - owner -c "pkgcmd -i -t wgt -p $pkg_file_path$pkg_file"
			sync
		fi

		# Remove prifilege requests from applications
		if [ "$pkg_privileges" != "" ]; then
			echo Requred privileges : $pkg_privileges
			IFS=';' read -ra priv <<< "$pkg_privileges"
			for i in "${priv[@]}"; do
				echo Erasing policy $i
				/usr/sbin/cyad --erase="" -r=no -c User::Pkg::${pkg_name%.*} -u 5001 -p http://tizen.org/privilege/$i
			done

			echo Policy list for ${pkg_name%.*}
			/usr/sbin/cyad -l "" -c User::Pkg::${pkg_name%.*} -u "#" -p "#"
		fi
	done < $pkg_list_file

	#set up vconf to disable lockscreen & display timeout
	/usr/bin/vconftool set -t int db/setting/screen_lock_type 0 -rf
	/usr/bin/vconftool set -t int db/setting/lcd_backlight_normal "600" -f
	sleep 1
	sync

	#check vconf value
	/usr/bin/vconftool get db/setting/screen_lock_type
	/usr/bin/vconftool get db/setting/lcd_backlight_normal
}

function func_run {
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
		echo name=$pkg_name
		echo file=$pkg_file

		pid=$(ps -ef | pgrep -f $pkg_name)
		if [ "$pid" != "" ]; then
			echo "$pkg_name is already running. kill this one"
			kill -9 $pid
		else
			echo "$pkg_name is not running."
		fi

	# VD-image standard: capture logs via vlog (vlogutil), not dlog (dlogutil).
	# The vlog ring buffer cannot be cleared, and timespan filtering only
	# works in stream mode, so emulate "clear" by marking the current uptime
	# and "dump" by reading back only the elapsed window with `vlogutil -t`.
	# Fall back to dlogutil on images without vlogutil.
	if command -v vlogutil >/dev/null 2>&1; then
		LOG_CAPTURE=vlog
		LOG_TS0=$(cut -d' ' -f1 /proc/uptime)
		log_clear() { LOG_TS0=$(cut -d' ' -f1 /proc/uptime); }
		log_dump() {
			local now span
			now=$(cut -d' ' -f1 /proc/uptime)
			span=$(( ${now%.*} - ${LOG_TS0%.*} + 3 ))
			[ $span -lt 1 ] && span=1
			vlogutil -t "$span" 2>/dev/null
		}
		# vlog keeps D-level logs: the FULL mobile milestone chain exists
		# (main/create/reset/resume/Launching:done). reset:done fires ~0.4s
		# BEFORE resume/Launching:done — never wait on it, or the dump
		# would truncate the chain. Launching:done is the last milestone;
		# tvctx RESUMED is the fallback.
		WAIT_DONE_RE="Application:Launching:done|RESUMED"
	else
		LOG_CAPTURE=dlog
		log_clear() { dlogutil -c 2&> /dev/null; }
		log_dump() { dlogutil -v threadtime -d 2>/dev/null; }
		WAIT_DONE_RE="Application:(Launching|resume|reset):done|RESUMED"
	fi

	# Poll dlog until a launch-done milestone appears for $1, timeout ${2:-15}s.
	# TV: no Launching/resume/reset:done; RESUMED (tvctx-manager) is the LAST
	# observable milestone of a launch. Do NOT add main:done here: it fires
	# ~1s BEFORE RESUMED, and dumping that early truncates the chain.
	# NOTE: on TV the E20 render loop floods the 2MB ring buffer within a few
	# seconds, so the caller must dump IMMEDIATELY after this returns.
	function wait_launch_done {
		local pkg=$1
		local timeout=${2:-15}
		local elapsed=0

		while [ $elapsed -lt $timeout ]; do
			if log_dump | grep -E "$WAIT_DONE_RE" | grep -q "$pkg"; then
				echo "launch done keyword found for $pkg (${elapsed}s)"
				return 0
			fi
			sleep 1
			elapsed=$((elapsed + 1))
		done

		echo "launch done keyword NOT found for $pkg after ${timeout}s"
		return 1
	}

	run_count=2
		i=0

		while [ $i -lt $run_count ]; do
			echo "$ith running"
			#clear dlog
			log_clear

			# launch app
			su - owner -c "app_launcher -s $pkg_name"
			# Was: fixed "sleep 20" then dump once after BOTH rounds — on TV the
			# ring buffer only holds a few seconds, so the launch sequence was
			# always flushed away. Now: poll for the milestone, dump
			# IMMEDIATELY each round (last round wins), then kill.
			wait_launch_done "$pkg_name" 15
			log_dump > ${result_path}dlog_$pkg_name".txt"
			sync

			# kill process
			pid=$(ps -ef | pgrep -f $pkg_name)
			echo "pid=$pid"
			if [ "$pid" != "" ]; then
				echo "kill $pkg_name "
				kill -9 $pid
			fi

			sleep 10

			i+=1
		done

		# kill process
		pid=$(ps -ef | pgrep -f $pkg_name)
		echo "pid=$pid"
		if [ "$pid" != "" ]; then
			echo "kill $pkg_name "
			kill -9 $pid
		fi

	done < $pkg_list_file

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
	test_exit -1

fi

echo "end $test_name"

test_exit 0

