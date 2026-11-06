#!/bin/bash

echo -e '\033[34m' ' '

function test_exit {
	echo -e '\033[0m' ' '
	exit $1
}

file_name=${0##*/}
test_name=${file_name%%\.*}

function usage {
	echo "usage : $file_name TARGET_DIR PKG_LIST_FILE RESULT_PATH"
}

echo "Start $test_name"

if [ $# -lt 3 ]; then
	usage
	echo "Not enough argument" 1>&2
	test_exit -1
fi

target_dir=$1
pkg_list_file=$2
result_path=$3

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
	mkdir -p $result_path/$target_dir
fi

#remove previous result
rm $result_path*.csv

#install package
rpm -ivh --force $pkg_list_file/dep-info*.rpm
if [ $target_dir == "/usr/bin" ]; then
	filelist=$(find /usr/bin/* -type f -not -path "*.sh")
elif [ $target_dir == "/usr/lib" ]; then
	filelist=$(find /usr/lib/ -name "*.so*" -type f)
fi

is_sprd=$(cat /proc/cpuinfo|grep -c Z3)

# CPU Boost start
if [ $is_sprd -eq 1 ]; then
	echo performance > /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor
fi

multi_count=0
multi_max=4

filecount=0
totalcount=0

outputfile=${result_path}/_dep_info_report.txt

depth=5

for line in ${filelist[@]}; do
	echo "Get dependency info : "$line

	lddcount=$(ldd $line | wc -l)
	if [ $target_dir == "/usr/bin" ]; then
		filepath=$line
	elif [ $target_dir == "/usr/lib" ]; then
		filepath=$(echo $line | awk '{split($0,a,"[.][s][o]"); printf("%s.so", a[1])}')
	fi

	if [ ! -d $result_path$filepath ]; then
		mkdir -p $(dirname $result_path$filepath)
	fi

	multi_count=$((multi_count+1))
	if [ $multi_count -eq $multi_max ]
	then
		/usr/bin/get_syms -d $depth -o $result_path/$filepath.txt $line > /dev/null 2>&1
		multi_count=0
	else
		/usr/bin/get_syms -d $depth -o $result_path/$filepath.txt $line > /dev/null 2>&1 &
	fi
	echo "[dep_info] $filepath,$lddcount,links" >> $outputfile
	totalcount=$((totalcount+lddcount))
	filecount=$((filecount+1))
done

getsyms_working=1
max_loop=60

while [ $getsyms_working -ne 0 ]; do
	getsyms_working=$(pgrep get_syms|wc -l)
	max_loop=$(($max_loop-1))
	if [ $max_loop -eq 0 ]; then
		break
	fi
	sleep 1
done

# CPU Boost end
if [ $is_sprd -eq 1 ]; then
	echo  sprdemand > /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor
fi
