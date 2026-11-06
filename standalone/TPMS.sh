#!/bin/bash

init_workspace() {

	rm -rf ${WORKSPACE_DIR}
	mkdir ${WORKSPACE_DIR}
}

sdb_get_serial_rpi() {
	local max_retries=5
	local retry_interval=15

	for i in $(seq 1 $max_retries); do
		sdb kill-server
		sleep 3
		sudo -n udevadm trigger
		sleep 5
		sdb start-server

		sleep 13
		sdb devices
		sdb_serial=$(sdb devices | awk -v profile=rpi3 'BEGIN{count=0;} {if($3==profile) {count += 1; serial=$1}} END {if(count > 1) {printf "-2"} else if(count==1) {printf "%s", serial} else {printf "-1"} }' )

		if [ $sdb_serial == -1 ]; then
			#double check
			sdb_serial=$(sdb devices | awk -v profile=rpi4 'BEGIN{count=0;} {if($3==profile) {count += 1; serial=$1}} END {if(count > 1) {printf "-2"} else if(count==1) {printf "%s", serial} else {printf "-1"} }' )
		fi

		if [ $sdb_serial != -1 ] && [ $sdb_serial != -2 ]; then
			echo "========================================"
			echo "   ${TIZEN_PROFILE} : $sdb_serial (found on retry $i/$max_retries)"
			echo "========================================"
			return 0
		fi

		if [ $sdb_serial == -2 ]; then
			echo "========================================"
			echo "There are two or more ${TIZEN_PROFILE}"
			echo "========================================"
			echo "There are two or more ${TIZEN_PROFILE}" > ${WORKSPACE_DIR}/Terminate_Test.txt
			exit 0
		fi

		if [ $i -lt $max_retries ]; then
			echo "Retry $i/$max_retries: device not found, waiting ${retry_interval}s..."
			sleep $retry_interval
		fi
	done

	echo "========================================"
	echo "There is no ${TIZEN_PROFILE} (after $max_retries retries)"
	echo "========================================"
	echo "There is no ${TIZEN_PROFILE}" > ${WORKSPACE_DIR}/Terminate_Test.txt
	exit 0
}


sdb_get_serial_tv() {
	# TV target attached via sdb-over-TCP. Unlike USB devices, a TCP-attached
	# device disappears after "sdb kill-server" and never re-enumerates by
	# itself, so never kill the server here; (re)connect using dev_ip from
	# testprofiles.cfg instead. The TV image reports device name "0".
	local max_retries=5
	# DEV_IP (5th arg / TV_DEV_IP env) overrides dev_ip from testprofiles.cfg.
	local target_ip=${DEV_IP:-$(sed -nr "/^\[${TIZEN_VERSION}-${TIZEN_PROFILE}\]/ { :l /^dev_ip[ ]*=/ { s/.*=[ ]*//; p; q;}; n; b l;}" ${CURRENT_DIR}/testprofiles.cfg)}

	for i in $(seq 1 $max_retries); do
		sdb devices
		# Match the device by its ip:port serial prefix, not just device name
		# "0": with multiple TCP boards connected (or another board taking the
		# old IP), name-only matching can silently pick the wrong target.
		if [ ${#target_ip} -gt 0 ]; then
			sdb_serial=$(sdb devices | awk -v ip="${target_ip}:" 'BEGIN{count=0;} {if(index($1,ip)==1) {count += 1; serial=$1}} END {if(count > 1) {printf "-2"} else if(count==1) {printf "%s", serial} else {printf "-1"} }' )
		else
			sdb_serial=$(sdb devices | awk 'BEGIN{count=0;} {if($3=="0") {count += 1; serial=$1}} END {if(count > 1) {printf "-2"} else if(count==1) {printf "%s", serial} else {printf "-1"} }' )
		fi

		if [ $sdb_serial == -2 ]; then
			echo "========================================"
			echo "There are two or more ${TIZEN_PROFILE}"
			echo "========================================"
			echo "There are two or more ${TIZEN_PROFILE}" > ${WORKSPACE_DIR}/Terminate_Test.txt
			exit 0
		fi

		if [ $sdb_serial == -1 ]; then
			if [ ${#target_ip} = 0 ]; then
				echo "========================================"
				echo "There is no ${TIZEN_PROFILE} and dev_ip is empty in testprofiles.cfg"
				echo "========================================"
				echo "There is no ${TIZEN_PROFILE} (dev_ip empty)" > ${WORKSPACE_DIR}/Terminate_Test.txt
				exit 0
			fi
			echo "Retry $i/$max_retries: device not found, try: sdb connect ${target_ip}"
			sdb connect ${target_ip}
			sleep 10
			continue
		fi

		echo "========================================"
		echo "   ${TIZEN_PROFILE} : $sdb_serial (found on retry $i/$max_retries)"
		echo "========================================"
		return 0
	done

	echo "========================================"
	echo "There is no ${TIZEN_PROFILE} (after $max_retries retries)"
	echo "========================================"
	echo "There is no ${TIZEN_PROFILE}" > ${WORKSPACE_DIR}/Terminate_Test.txt
	exit 0
}

sdb_get_serial() {
	if [ ${TIZEN_PROFILE} == "common-artik" ]; then
		local_profile="artik"
		cd ${CURRENT_DIR}/Download_bin/download_artik
		./sdb-enable.sh
		sleep 40
	elif [ ${TIZEN_PROFILE} == "mobile-tm1" ]; then
		local_profile="TM1"
	elif [ ${TIZEN_PROFILE} == "mobile-tm2" ]; then
		local_profile="TM2"
	elif [ ${TIZEN_PROFILE} == "wearable-tw1" ]; then
		local_profile="TW1"
	elif [ ${TIZEN_PROFILE} == "wearable-tw2" ]; then
		local_profile="TW2"
	elif [ ${TIZEN_PROFILE} == "wearable-tw3" ]; then
		local_profile="TW3"
	elif [ ${TIZEN_PROFILE} == "mobile-z4" ]; then
		local_profile="SM-Z400F"
	elif [ ${TIZEN_PROFILE} == "mcd-solis" ]; then
		local_profile="SM-R765"
	elif [ ${TIZEN_PROFILE} == "mcd-galileo" ]; then
		local_profile="SM-R800P"
	elif [ ${TIZEN_PROFILE} == "iot-rpi" ] || [[ ${TIZEN_PROFILE} == "unified-rpi"* ]]
	then
		sdb_get_serial_rpi
		return 0
	elif [ ${TIZEN_PROFILE} == "tv-kantsu2e" ]; then
		sdb_get_serial_tv
		return 0
	else
		echo "not support profile : ${TIZEN_PROFILE}"
		exit 0
	fi

	sdb kill-server
	sleep 3
	sdb start-server
	sleep 13
	sdb devices
	sdb_serial=$(sdb devices | awk -v profile=$local_profile 'BEGIN{count=0;} {if($3==profile) {count += 1; serial=$1}} END {if(count > 1) {printf "-2"} else if(count==1) {printf "%s", serial} else {printf "-1"} }' )

	if [ $sdb_serial == -1 ]; then
		echo "========================================"
		echo "There is no ${TIZEN_PROFILE}"
		echo "========================================"
		echo "There is no ${TIZEN_PROFILE}" > ${WORKSPACE_DIR}/Terminate_Test.txt
		exit 0
	elif [ $sdb_serial == -2 ]; then
		echo "========================================"
		echo "There are two or more ${TIZEN_PROFILE}"
		echo "========================================"
		echo "There are two or more ${TIZEN_PROFILE}" > ${WORKSPACE_DIR}/Terminate_Test.txt
		exit 0
	fi

	echo "========================================"
	echo "   ${TIZEN_PROFILE} : $sdb_serial"
	echo "========================================"
}

DownloadBin() {

	if [ $TEST_ONLY = true ]; then
		echo -e "\033[31mExecute only Test Script\033[0m"
		return
	fi

	# TV (kantsu2e) platform images are flashed manually from the
	# TIZEN-*-KantSU2e tarballs; download_bin.sh has no TV support. Skip the
	# download/flash step and test the image already on the board.
	if [ ${TIZEN_PROFILE} == "tv-kantsu2e" ]; then
		echo -e "\033[33mtv-kantsu2e: auto download/flash is not supported, flash the TV image manually; skip download and test the current image\033[0m"
		return
	fi

	cd ${CURRENT_DIR}/Download_bin
	./download_bin.sh $TIZEN_PROFILE $TIZEN_VERSION $SNAPSHOT_ID ${CURRENT_DIR}/testprofiles.cfg $WORKSPACE_DIR

	if [ ! -f "${WORKSPACE_DIR}/download_complete.txt" ]; then
		echo -e "\033[31mDownload Fail\033[0m"
		echo "Download Fail" > ${WORKSPACE_DIR}/Terminate_Test.txt
		exit 0
	fi

	sdb_get_serial

	export SDB_SERIAL=$sdb_serial

	# unified-rpi: remount and resize after image flashing (moved to ResizeFilesystem)
}

ResizeFilesystem() {

	if [[ ${TIZEN_PROFILE} == "unified-rpi"* ]]; then
		echo -e "\033[34mPrepare unified-rpi: remount and resize\033[0m"
		${COMMON_DIR}/sdb_root_on.sh
		${COMMON_DIR}/sdb_shell.sh "mount -o rw,remount /"
		${COMMON_DIR}/sdb_shell.sh "mount -o rw,remount /hal"
		${COMMON_DIR}/sdb_shell.sh "osu --resize"
	fi
}

DisableDmVerity() {


	if [ $TEST_ONLY = true ]; then
		echo -e "\033[31mExecute only Test Script\033[0m"
		return
	fi

	if [ ${TIZEN_PROFILE} == "wearable-tw3" ]; then
		${COMMON_DIR}/sdb_root_on.sh
		${COMMON_DIR}/sdb_shell.sh "verityctl disable"
		${COMMON_DIR}/sdb_shell.sh "reboot"
		sdb wait-for-device
	fi
}

InstallPlugin() {
	if [ ${TIZEN_PROFILE} == "mcd-solis" ]; then
		echo -e "\033[31mSkip Installing Plugin\033[0m"
		echo -e "\033[31mSkip setup wizard skip\033[0m"
		${COMMON_DIR}/sdb_root_on.sh
		${COMMON_DIR}/sdb_shell.sh "vconftool set -t int db/setup_wizard/first_boot 0 -f"
		${COMMON_DIR}/sdb_shell.sh "vconftool get -t int db/setup_wizard/first_boot"
		return
	fi

	if [ ${TIZEN_PROFILE} == "mcd-galileo" ]; then
		echo -e "\033[31mSkip Installing Plugin\033[0m"
		echo -e "\033[31mSkip setup wizard skip\033[0m"
		${COMMON_DIR}/sdb_root_on.sh
		${COMMON_DIR}/sdb_shell.sh "verityctl disable"
		${COMMON_DIR}/sdb_shell.sh "vconftool set -t int db/setup_wizard/first_boot 0 -f"
		${COMMON_DIR}/sdb_shell.sh "vconftool get -t int db/setup_wizard/first_boot"
		return
	fi

	if [ $TEST_ONLY = true ]; then
		echo -e "\033[31mSkip Installing Plugin\033[0m"
		return
	fi

	plugin_path=$(sed -nr "/^\[common\]/ { :l /^plugin_path[ ]*=/ { s/.*=[ ]*//; p; q;}; n; b l;}" ${CURRENT_DIR}/testprofiles.cfg)
	if [ ${#plugin_path} = 0 ]; then
		echo "Fail! Can not get plugin_path from testprofiles.cfg"
		return
	fi

	if [ ! -d ${plugin_path} ]; then
		echo "Fail! There is no ${plugin_path}"
		return
	fi

	# temp
	${COMMON_DIR}/sdb_root_on.sh
	cd ${plugin_path}

	if [ -d ./artik5-plugin ]; then
		git checkout ./artik5-plugin/install.sh
	elif [ -d ./tm1-plugin ]; then
		git checkout ./tm1-plugin/install.sh
	elif [ -d ./tm2-plugin ]; then
		git checkout ./tm2-plugin/32bit/install.sh
		git checkout ./tm2-plugin/64bit/install.sh
		git checkout ./tm2-plugin/noarch/install.sh
		git checkout ./tm2-plugin/install.sh
	elif [ -d ./tw1-plugin ]; then
		git checkout ./tw1-plugin/install.sh
	elif [ -d ./tw2_plugin ]; then
		git checkout ./tw2_plugin/32bit/install.sh
		git checkout ./tw2_plugin/64bit/install.sh
		git checkout ./tw2_plugin/noarch/install.sh
		git checkout ./tw2_plugin/install.sh
    elif [ -d ./tw2-plugin ]; then
        git checkout ./tw2-plugin/install.sh
    elif [ -d ./tw3_plugin ]; then
		git checkout ./tw3_plugin/32bit/install.sh
		git checkout ./tw3_plugin/64bit/install.sh
		git checkout ./tw3_plugin/noarch/install.sh
		git checkout ./tw3_plugin/install.sh
    elif [ -d ./tw3-plugin ]; then
        git checkout ./tw3-plugin/install.sh
    elif [ -d ./rpi3-plugin ]; then
    	echo "rpi3-plugin is existed"
    else
    	echo "There is no plugin dir for " ${TIZEN_PROFILE}
    	return
	fi

	if [ ${TIZEN_PROFILE} == "common-artik" ]; then
		git checkout tizen_${TIZEN_VERSION}_ARTIK5
		cd artik5-plugin
	elif [ ${TIZEN_PROFILE} == "mobile-tm1" ]; then
		git checkout tizen_${TIZEN_VERSION}_tm1
		cd tm1-plugin
	elif [ ${TIZEN_PROFILE} == "mobile-tm2" ]; then
		git checkout tizen_${TIZEN_VERSION}_tm2
		cd tm2-plugin
	elif [ ${TIZEN_PROFILE} == "wearable-tw1" ]; then
		git checkout tizen_${TIZEN_VERSION}_tw1
		cd tw1-plugin
	elif [ ${TIZEN_PROFILE} == "wearable-tw2" ]; then
		git checkout tizen_${TIZEN_VERSION}_tw2
		cd tw2_plugin
    elif [ ${TIZEN_PROFILE} == "wearable-tw3" ]; then
        git checkout tizen_${TIZEN_VERSION}_tw3
        cd tw3_plugin
    elif [ ${TIZEN_PROFILE} == "iot-rpi" ]; then
    	cd rpi3-plugin
	elif [[ ${TIZEN_PROFILE} == "unified-rpi"* ]]; then
		if [ ${TIZEN_VERSION} == "10.0" ]; then
			git checkout tizen_10.0_RPI4
		elif [ ${TIZEN_VERSION} == "10.1" ]; then
			git checkout tizen_10.1_RPI4
		elif [ ${TIZEN_VERSION} == "11.0" ]; then
			git checkout tizen_11.0_RPI4
		else
			git checkout tizen_10.0_RPI4
		fi
		if [ $? -ne 0 ]; then
			echo -e "\033[31mFail! git checkout failed for plugin-prebuilt (TIZEN_VERSION: ${TIZEN_VERSION})\033[0m"
			return
		fi
		echo -e "\033[34mPlugin-prebuilt checkout success: $(git rev-parse --abbrev-ref HEAD) ($(git rev-parse --short HEAD))\033[0m"
		cd rpi3-plugin
	fi

	if [ ${SNAPSHOT_ID} == "latest" ]; then
		git pull
	fi

	if [ ${TIZEN_PROFILE} == "wearable-tw2" ]; then
		sed -i 's/sdb -d/sdb -s ${SDB_SERIAL} -d/g' ./32bit/install.sh
		sed -i 's/sdb -d/sdb -s ${SDB_SERIAL} -d/g' ./64bit/install.sh
		sed -i 's/sdb -d/sdb -s ${SDB_SERIAL} -d/g' ./noarch/install.sh
	elif [ ${TIZEN_PROFILE} == "mobile-tm2" ]; then
		sed -i 's/sdb -d/sdb -s ${SDB_SERIAL} -d/g' ./32bit/install.sh
		sed -i 's/sdb -d/sdb -s ${SDB_SERIAL} -d/g' ./64bit/install.sh
		sed -i 's/sdb -d/sdb -s ${SDB_SERIAL} -d/g' ./noarch/install.sh

	elif [ ${TIZEN_PROFILE} == "wearable-tw3" ]; then
		sed -i 's/sdb -d/sdb -s ${SDB_SERIAL} -d/g' ./32bit/install.sh
		sed -i 's/sdb -d/sdb -s ${SDB_SERIAL} -d/g' ./64bit/install.sh
		sed -i 's/sdb -d/sdb -s ${SDB_SERIAL} -d/g' ./noarch/install.sh
	fi

	sed -i 's/sdb -d/sdb -s ${SDB_SERIAL} -d/g' ./install.sh
	./install.sh ${SDB_SERIAL}

	sleep 80
}

get_version() {

	${COMMON_DIR}/sdb_root_on.sh
	if [ -f "${WORKSPACE_DIR}/Terminate_Test.txt" ]; then
		echo "sdb_root_on failure"
		exit 0
	fi

	${COMMON_DIR}/sdb_pull.sh "/etc/info.ini ${WORKSPACE_DIR}"
	local_version=$(${COMMON_DIR}/sdb_shell.sh "cat /etc/info.ini" | grep 'Build=' | cut -b7- | sed 's/;//g')
	local_profile=$(${COMMON_DIR}/sdb_shell.sh "cat /etc/os-release" | grep 'BUILD_ID' | awk -F'-' '{print $NF}')

	# sdb -s $sdb_serial pull /etc/info.ini ${WORKSPACE_DIR}
	# local_version=$(sdb -s $sdb_serial shell cat /etc/info.ini | grep 'Build=' | cut -b7- | sed 's/;//g')

	echo -e "\033[34mBuildVersionZZZ : ${local_version}\033[0m"

	#if [ ${TIZEN_PROFILE} == "mcd-solis" ]; then
	#	echo -e "\033[34mProfileZZZ : mcd-solis\033[0m"
	#else
		echo -e "\033[34mProfileZZZ : ${local_profile}\033[0m"
	#fi

	#echo "BuildVersion,${local_version}" >> ${WORKSPACE_DIR}/report.txt
}

remove_oobe() {

	if [ ${TIZEN_PROFILE} == "iot-rpi" ] || [[ ${TIZEN_PROFILE} == "unified-rpi"* ]]
	then

		if [ $TEST_ONLY = true ]
		then
			echo -e "\033[34mExecute only Test Script\033[0m"
			return
		fi

		echo -e "\-33[34mRemove org.tizen.oobe\033[0m"
		${COMMON_DIR}/sdb_root_on.sh
		${COMMON_DIR}/sdb_shell.sh "mount -o rw,remount /"
		${COMMON_DIR}/sdb_shell.sh "app_launcher -k org.tizen.oobe"
		${COMMON_DIR}/sdb_shell.sh "tpk-backend -d org.tizen.oobe --preload --force-remove"
	fi
}

fix_homescreen() {

	if [[ ${TIZEN_PROFILE} == "unified-rpi-toolchain"* ]]
	then

		if [ $TEST_ONLY = true ]
		then
			echo -e "\033[34mExecute only Test Script\033[0m"
			return
		fi

		echo -e "\033[34mFix homescreen for toolchain\033[0m"
		bash ${COMMON_DIR}/fix-homescreen.sh
	fi
}

RunStandAlone() {

	cd ${CURRENT_DIR}
	# Use testprofiles_temp.cfg if it exists (created by web UI for selective test runs)
	if [ -f "./testprofiles_temp.cfg" ]; then
		echo "Using testprofiles_temp.cfg for selective test execution"
		python3 ./standalone.py -p ${FULL_PROFILE} -c ./testprofiles_temp.cfg -o ${WORKSPACE_DIR}
	else
		python3 ./standalone.py -p ${FULL_PROFILE} -c ./testprofiles.cfg -o ${WORKSPACE_DIR}
	fi
}

# No-argument default: run the VD TV board (kantsu2e) suite directly, so
# "./TPMS.sh" alone is equivalent to "./TPMS.sh tv-kantsu2e 10.0 true latest".
if [ $# -eq 0 ]
then
	DEFAULT_PROFILE="tv-kantsu2e"
	DEFAULT_TIZEN_VERSION="10.0"
	DEFAULT_TEST_ONLY="true"
	DEFAULT_SNAPSHOT_ID="latest"
	echo "========================================"
	echo "No arguments given, use default VD target:"
	echo "  ./TPMS.sh ${DEFAULT_PROFILE} ${DEFAULT_TIZEN_VERSION} ${DEFAULT_TEST_ONLY} ${DEFAULT_SNAPSHOT_ID}"
	echo "========================================"
	set -- ${DEFAULT_PROFILE} ${DEFAULT_TIZEN_VERSION} ${DEFAULT_TEST_ONLY} ${DEFAULT_SNAPSHOT_ID}
fi

if [ $# -lt 4 ]
then
echo "Usage : ./TPMS.sh [profile] [tizen version] [test_only] [snapshot_id]"
echo "        (no arguments defaults to: tv-kantsu2e 10.0 true latest)"
echo "        profile       : common-artik, mobile-tm1, mobile-tm2, wearable-tw1, wearable-tw2"
echo "        tizen version : 3.0 4.0"
echo "        test_only     : true or false"
echo "        snapshot_id   : latest or 20160929.1"
echo "        dev_ip        : (optional, TV only) target IP override, or set TV_DEV_IP env"
exit 0
fi

# Resolve the script's own directory instead of the caller's cwd, so the
# script works when invoked from any path (e.g. ./standalone/TPMS.sh).
export CURRENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export WORKSPACE_DIR=${CURRENT_DIR}/workspace
export COMMON_DIR=${CURRENT_DIR}/common
export TIZEN_PROFILE=$1
export TIZEN_VERSION=$2
export TEST_ONLY=$3
export SNAPSHOT_ID=$4

# Optional target IP override for sdb-over-TCP boards (e.g. tv-kantsu2e):
# 5th argument or TV_DEV_IP env; falls back to dev_ip in testprofiles.cfg.
export DEV_IP=${5:-${TV_DEV_IP:-}}

init_workspace

# TV (sdb-over-TCP) boards require sdbd to be enabled board-side before the
# serial probe; run the idempotent bringup first. It is a near no-op when the
# board is already set up, and auto-repairs sdbd over SSH after a reflash.
if [ ${TIZEN_PROFILE} == "tv-kantsu2e" ]; then
	bash ${COMMON_DIR}/tv_board_bringup.sh ${DEV_IP}
	if [ $? -ne 0 ]; then
		echo "tv_board_bringup failed, abort test"
		exit 0
	fi
fi

sdb_get_serial

export SDB_SERIAL=$sdb_serial

# sdb-over-TCP to the TV board is dropped after ~10 idle seconds (routed
# path session expiry); keep it alive with a trivial sdb command every 5s
# for the whole test session, otherwise long no-traffic windows (e.g. the
# memory_usage idle-settle wait) lose the device mid-suite.
if [ ${TIZEN_PROFILE} == "tv-kantsu2e" ]; then
	nohup bash ${COMMON_DIR}/tv_sdb_keepalive.sh ${SDB_SERIAL} 5 > /dev/null 2>&1 &
	TV_KEEPALIVE_PID=$!
	trap 'kill ${TV_KEEPALIVE_PID} 2>/dev/null' EXIT
fi

export FULL_PROFILE=$(echo ${TIZEN_VERSION}-${TIZEN_PROFILE})

DownloadBin
ResizeFilesystem
DisableDmVerity
InstallPlugin
remove_oobe
fix_homescreen
get_version



echo "CURRENT_DIR   : ${CURRENT_DIR}   "
echo "WORKSPACE_DIR : ${WORKSPACE_DIR} "
echo "COMMON_DIR    : ${COMMON_DIR}    "
echo "TIZEN_PROFILE : ${TIZEN_PROFILE} "
echo "TIZEN_VERSION : ${TIZEN_VERSION} "
echo "TEST_ONLY     : ${TEST_ONLY}     "
echo "SNAPSHOT_ID   : ${SNAPSHOT_ID}   "
echo "SDB_SERIAL    : ${SDB_SERIAL}    "
echo "DEV_IP        : ${DEV_IP:-<testprofiles.cfg>} "
echo "FULL_PROFILE  : ${FULL_PROFILE}  "

RunStandAlone

# Auto-save the result into the TPMS DB (build number = max+1), so a plain
# "./TPMS.sh" run appears in the web dashboard without a manual save step.
# Skipped under Jenkins (tpms_jenkins.sh saves by itself); set
# TPMS_SKIP_DB_SAVE=1 for throwaway runs.
if [ -z "${JENKINS_HOME}" ] && [ -z "${BUILD_NUMBER}" ]; then
	bash ${COMMON_DIR}/save_result_to_db.sh ${FULL_PROFILE}
fi
