#!/bin/bash

echo -e '\033[34m' ' '

function test_exit {
	echo -e '\033[0m' ' '
	exit $1
}

file_name=${0##*/}
# UEP-safe invocation pipes this script via stdin, making $0="bash";
# allow the caller to pass the real test name explicitly.
test_name=${TPMS_TEST_NAME:-${file_name%%\.*}}

# VD-image standard: capture logs via vlog (vlogutil), not dlog (dlogutil).
# vlog has no clear command; mark uptime at start and dump the elapsed
# window back with `vlogutil -t`. Fall back to dlogutil when absent.
if command -v vlogutil >/dev/null 2>&1; then
	LOG_TS0=$(cut -d' ' -f1 /proc/uptime)
	log_dump() {
		local now span
		now=$(cut -d' ' -f1 /proc/uptime)
		span=$(( ${now%.*} - ${LOG_TS0%.*} + 3 ))
		[ $span -lt 1 ] && span=1
		vlogutil -t "$span" 2>/dev/null
	}
else
	log_dump() { dlogutil -v threadtime -d 2>/dev/null; }
fi


function usage {
	echo "usage: $file_name OUTPUT_FILE"
}

echo "start $test_name"

if [ $# -lt 1 ]; then
	usage
	echo "no destination of output" 1>&2
	test_exit -1
fi

dest=$1
if [[ $dest != /* ]]; then
	echo "output file must be absolute path" 1>&2
	test_exit -1
fi

dest_path=${dest%/*}/

if [ ! -d ${dest_path} ]; then
	mkdir -p $dest_path
fi

# remove previous result
if [ -e ${dest} ]; then
	rm $dest
	sync
fi

extra_result=${dest_path}"dlog_"${test_name}".txt"
if [ -e ${extra_result} ]; then
	rm $extra_result
	sync
fi

# check crash directory
if [ -e /opt/share/crash/dump ]; then
	set -x
	ls -l /opt/share/crash/dump
	set +x
fi

# run test
sleep 10
build_info_file="/etc/info.ini"
cp $build_info_file $dest
sync

# get dlog
log_dump > $extra_result
sync

echo "end $test_name"

test_exit 0
