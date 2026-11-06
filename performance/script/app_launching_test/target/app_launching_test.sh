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
	previous_result_file=${result_path}"dlog_*_launch"${pkg_name}".txt"
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
		# ignore empty line
		if [[ -z "${line// }" ]]; then
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
			# Pick package type by extension: TV has no launchable native tpk
			# (mobile-era helloworld fails to mmap on TV libs), so the TV
			# pkg list carries a .wgt instead.
			pkg_type=tpk
			case "$pkg_file" in
				*.wgt) pkg_type=wgt ;;
			esac
			su - owner -c "pkgcmd -i -t $pkg_type -p $pkg_file_path$pkg_file"
			sync
			sleep 2
		fi

		# Remove prifilege requests from applications
		if [ "$pkg_privileges" != "" ]; then
			echo Requred privileges : $pkg_privileges
			IFS=';' read -ra priv <<< "$pkg_privileges"
			for i in "${priv[@]}"; do
				echo Erasing policy $i
				/usr/sbin/cyad --erase="" -r=no -c User::Pkg::$pkg_name -u 5001 -p http://tizen.org/privilege/$i
			done

			echo Policy list for $pkg_name
			/usr/sbin/cyad -l "" -c User::Pkg::$pkg_name -u "#" -p "#"
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

# VD-image standard: capture logs via vlog (vlogutil), not dlog (dlogutil).
# The vlog ring buffer cannot be cleared, and timespan filtering only works
# in stream mode, so emulate "clear" by marking the current uptime and
# "dump" by reading back only the elapsed window with `vlogutil -t`.
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
	# vlog keeps D-level logs, so the FULL mobile milestone chain exists
	# (main/create/reset/resume/Launching:done). reset:done fires ~0.4s
	# BEFORE resume/Launching:done — never wait on it, or the dump would
	# truncate the chain. Launching:done is the last milestone;
	# tvctx RESUMED is the fallback.
	WAIT_DONE_RE="Application:Launching:done|RESUMED"
else
	LOG_CAPTURE=dlog
	log_clear() { dlogutil -c 2&> /dev/null; }
	log_dump() { dlogutil -v threadtime -d 2>/dev/null; }
	WAIT_DONE_RE="Application:(Launching|resume|reset):done|RESUMED"
fi

# poll dlog until a launch-done keyword appears for $1 (pkg_name), timeout ${2:-15}s
# some platforms (e.g. RPi) never emit Launching:done/resume:done, so reset:done
# is also accepted as the end-of-launch signal
# returns 0 if found, 1 on timeout
function wait_launch_done {
	local pkg=$1
	local timeout=${2:-15}
	local elapsed=0

	while [ $elapsed -lt $timeout ]; do
		# TV milestone set: no Launching/resume/reset:done is emitted on
		# kantsu2e; RESUMED (tvctx-manager) is the LAST observable milestone
		# of a launch there. Do NOT add main:done here: it fires ~1s BEFORE
		# RESUMED, and dumping that early truncates the milestone chain.
		if log_dump | grep -E "$WAIT_DONE_RE" | grep -q "$pkg"; then
			echo "launch done keyword found for $pkg (${elapsed}s)"
			return 0
		fi
		sleep 1
		elapsed=$((elapsed + 1))
	done

	echo "WARNING: timeout ${timeout}s waiting launch-done keyword for $pkg" 1>&2
	return 1
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
		# ignore empty line
		if [[ -z "${line// }" ]]; then
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

		#clear dlog
		log_clear

		# launch app
		su - owner -c "app_launcher -s $pkg_name"

		# poll until launch-done keyword shows up in dlog (max 15s),
		# instead of a fixed sleep that may be too short on slow targets
		wait_launch_done "$pkg_name" 15

		# Dump IMMEDIATELY after the milestone is seen: on TV the E20 render
		# loop floods ~14k lines/min, so the 2MB ring buffer only holds a
		# few seconds — a "sleep 2" first would flush the launch sequence
		# out before the dump runs.
		log_dump > ${result_path}dlog_1st_launch_$pkg_name".txt"
		sync
		# small settle time to let trailing logs flush out
		sleep 2
		# TV ships vd_memps instead of memps; fall back to it, and skip the
		# file entirely when neither exists (host parser tolerates that).
		if command -v memps >/dev/null 2>&1; then
			memps -v > ${result_path}memps_${pkg_name}".txt"
		elif command -v vd_memps >/dev/null 2>&1; then
			vd_memps -v > ${result_path}memps_${pkg_name}".txt"
		else
			rm -f ${result_path}memps_${pkg_name}".txt"
		fi
		sync

		# Pause application by sending backkey event
		# Send keyevent twice to close IME in org.tizen.email
		# 64bit autoinput requires repeat count argument (2 = 1 run)
		if [ "$(uname -m)" = "aarch64" ]; then
			/opt/usr/tpms/bin/autoinput /opt/usr/tpms/file/backkey_script 2
			sleep 1
			/opt/usr/tpms/bin/autoinput /opt/usr/tpms/file/backkey_script 2
		else
			/opt/usr/tpms/bin/autoinput /opt/usr/tpms/file/backkey_script
			sleep 1
			/opt/usr/tpms/bin/autoinput /opt/usr/tpms/file/backkey_script
		fi



		aul_test pause ${pkg_name}

		#clear dlog again
		log_clear

		sleep 15

		# check whether the app is still alive (paused in background)
		# or already gone: this decides if 2nd launch is warm or cold.
		pid=$(ps -ef | pgrep -f $pkg_name)
		if [ "$pid" != "" ]; then
			echo "NOTE: $pkg_name still alive (pid=$pid) before 2nd launch - 2nd launch will be a WARM resume"
		else
			echo "NOTE: $pkg_name already terminated before 2nd launch - 2nd launch will be a COLD start"
		fi

		# TV: a WARM resume emits no loader exec / main:done milestones at
		# all (only a bare RESUMED line), which the parser cannot chain.
		# Force a cold start so the 2nd dump always contains a full
		# milestone sequence.
		if [ "$pid" != "" ]; then
			echo "TV workaround: killing $pkg_name to force cold 2nd launch"
			kill -9 $pid
			sleep 2
			log_clear
		fi

		# launch app (2nd)
		su - owner -c "app_launcher -s $pkg_name"

		wait_launch_done "$pkg_name" 15

		# Dump IMMEDIATELY (see t5l above): the tiny ring buffer would
		# otherwise lose the launch sequence during the settle sleep.
		log_dump > ${result_path}dlog_2nd_launch_$pkg_name".txt"
		sync
		# small settle time to let trailing logs flush out
		sleep 2

		# kill process
		pid=$(ps -ef | pgrep -f $pkg_name)
		echo "pid=$pid"
		if [ "$pid" != "" ]; then
			echo "kill $pkg_name "
			kill -9 $pid
		fi

		sleep 15

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

