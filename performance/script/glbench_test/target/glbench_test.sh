#!/bin/bash

echo -e '\033[34m' ' '

function test_exit {
	echo -e '\033[0m' ' '
	exit $1
}

file_name=${0##*/}
test_name=${file_name%%\.*}

function usage {
	echo "usage: $file_name MODE[install|run] PKG_INFO_FILE TEST_INFO_FILE RESULT_PATH"
}

echo "start $test_name"

if [ $# -lt 3 ]; then
	usage
	echo "not enough argument" 1>&2
	test_exit -1
fi

mode=$1
pkg_info_file=$2
test_info_file=$3
result_path=$4

echo $pkg_info_file
echo $test_info_file
echo $result_path

if [[ $result_path != /* ]] || [[ $pkg_info_file != /* ]]; then
	echo "file path must be absolute path" 1>&2
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
	previous_result_file=${result_path}${pkg_name}"_*.txt"
	if [ -e ${previous_result_file} ]; then
		rm $previous_result_file
	fi
done < $pkg_info_file

function func_install {
	echo "function: ${FUNCNAME[0]}"

	# temporal
	ls -al /opt/var/log/journal
	rm -rf /opt/var/log/journal/*

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
		echo name=$pkg_name
		echo file=$pkg_file
		echo exe=$pkg_exe

		pid=$(ps -ef | pgrep -f $pkg_exe)
		echo "pid=$pid"
		if [ "$pid" != "" ]; then
			echo "$pkg_name is already running. kill this one"
			kill -9 $pid
		fi

		#install
		temp=${pkg_file%\_*}
		#installed_query=$(rpm -q $temp)
		installed_query=$(rpm -qa | grep GLB2)
		echo installed_query=$installed_query
		#echo temp=$temp
		if [ "$installed_query" == "$temp" ]; then
			echo "$pkg_name is already installed"
		else
			rpm -ivh $pkg_file_path$pkg_file --nodeps --force
			sync
		fi

		sleep 5
	done < $pkg_info_file

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
		pkg_exe=$(echo $line | awk 'BEGIN { FS = "[ \t\n]+" } { print $3 }')
		echo name=$pkg_name
		echo file=$pkg_file
		echo exe=$pkg_exe

		pid=$(ps -ef | pgrep -f $pkg_exe)
		if [ "$pid" != "" ]; then
			echo "$pkg_name is already running. kill this one"
			kill -9 $pid
		else
			echo "$pkg_name is not running."
		fi

		#clear dlog
		dlogutil -c 2&> /dev/null

		while read l; do
			# ignore comment
			if [[ ${l} == \#* ]]; then
				continue
			fi

			exe_root=$(echo $l | awk 'BEGIN { FS = "[ \t\n]+" } { print $1 }')
			xdg_runtime_dir=$(echo $l | awk 'BEGIN { FS = "[ \t\n]+" } { print $2 }')
			exe_cmd=$(echo $l | awk 'BEGIN { FS = "[ \t\n]+" } { print $3 }')
			arg_t=$(echo $l | awk 'BEGIN { FS = "[ \t\n]+" } { print $4 }')
			arg_w=$(echo $l | awk 'BEGIN { FS = "[ \t\n]+" } { print $5 }')
			arg_h=$(echo $l | awk 'BEGIN { FS = "[ \t\n]+" } { print $6 }')
			sub_test_name=$(echo $l | awk 'BEGIN { FS = "[ \t\n]+" } { print $7 }')
			echo exe_root=$exe_root
			echo xdg_runtime_dir=$xdg_runtime_dir
			echo exe_cmd=$exe_cmd
			echo args=$arg_t $arg_w $arg_h

			cd $exe_root
			result_file=${result_path}${pkg_name}_${sub_test_name}".txt"
			echo result_file=$result_file
			XDG_RUNTIME_DIR=$xdg_runtime_dir $exe_cmd -t $arg_t -w $arg_w -h $arg_h > ${result_file}
			sync
			sleep 5
		done < $test_info_file

		dlogutil -v threadtime -d > ${result_path}dlog_$pkg_name".txt"
		sync

		# kill process
		pid=$(ps -ef | pgrep -f $pkg_exe)
		echo "pid=$pid"
		if [ "$pid" != "" ]; then
			echo "kill $pkg_name "
			kill -9 $pid
		fi

		sleep 10

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
	test_exit -1
fi

echo "end $test_name"

test_exit 0
