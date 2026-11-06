#!/bin/bash

get_data_from_cfg() {
	local_cfg_path=$1
	local_full_profile=$2
	local_snapshot_id=$3
	if [ ! -f ${local_cfg_path} ]; then
		echo "There is no ${local_cfg_path}"
		exit 0
	fi

	if [ ${local_snapshot_id} == "latest" ]; then
		BASE_URL=$(sed -nr "/^\[${local_full_profile}\]/ { :l /^platform_url[ ]*=/ { s/.*=[ ]*//; p; q;}; n; b l;}" ${local_cfg_path})
		if [ ${#BASE_URL} = 0 ]; then
			echo "Fail! Can not get BASE_URL from ${local_cfg_path}"
			exit 0
		fi
		BOOT_URL=$(sed -nr "/^\[${local_full_profile}\]/ { :l /^boot_url[ ]*=/ { s/.*=[ ]*//; p; q;}; n; b l;}" ${local_cfg_path})
	else
		local_base_url=$(sed -nr "/^\[${local_full_profile}\]/ { :l /^platform_url2[ ]*=/ { s/.*=[ ]*//; p; q;}; n; b l;}" ${local_cfg_path})
		if [ ${#local_base_url} = 0 ]; then
			echo "Fail! Can not get BASE_URL from ${local_cfg_path}"
			exit 0
		fi
		BASE_URL=$(printf "${local_base_url}" ${local_snapshot_id})
		BOOT_URL=$(sed -nr "/^\[${local_full_profile}\]/ { :l /^boot_url[ ]*=/ { s/.*=[ ]*//; p; q;}; n; b l;}" ${local_cfg_path})
	fi

	snapshot_serverid=$(sed -nr "/^\[${local_full_profile}\]/ { :l /^snapshot_serverid[ ]*=/ { s/.*=[ ]*//; p; q;}; n; b l;}" ${local_cfg_path})
	snapshot_serverpasswd=$(sed -nr "/^\[${local_full_profile}\]/ { :l /^snapshot_serverpasswd[ ]*=/ { s/.*=[ ]*//; p; q;}; n; b l;}" ${local_cfg_path})
}

download_binary() {
	cd ${WORKSPACE_DIR}

	echo BASE_URL : ${BASE_URL}

	rm -f MD5SUMS

	http_proxy="http://10.112.1.184:8080" wget --no-cache --user=$snapshot_serverid --password=$snapshot_serverpasswd --no-verbose ${BASE_URL}/MD5SUMS

	if [ ! -f "MD5SUMS" ]; then
		echo "There is no MD5SUMS"
		exit 0
	fi

	filename=$(cat ./MD5SUMS | grep ".tar.gz" | awk '{print $2}')

	rm -f *.tar.gz
	rm -f *.tar

	rm -f ${filename}
	rm -f ${filename/%.gz/}

	echo ${filename}

	http_proxy="http://10.112.1.184:8080" wget --no-cache --user=$snapshot_serverid --password=$snapshot_serverpasswd --no-verbose ${BASE_URL}/${filename}

	if [ ! -f ${filename} ]; then
		echo "Error on downloading ${filename}"
		exit 0
	fi

}

download_boot() {
	cd ${WORKSPACE_DIR}

	echo BOOT_URL : ${BOOT_URL}

	rm -f MD5SUMS

	http_proxy="http://10.112.1.184:8080" wget --no-cache --user=$snapshot_serverid --password=$snapshot_serverpasswd --no-verbose ${BOOT_URL}/MD5SUMS

	if [ ! -f "MD5SUMS" ]; then
		echo "There is no MD5SUMS"
		exit 0
	fi

	bootname=$(cat ./MD5SUMS | grep ".tar.gz" | awk '{print $2}')

	rm -f ${bootname}
	rm -f ${bootname/%.gz/}

	echo ${bootname}

	http_proxy="http://10.112.1.184:8080" wget --no-cache --user=$snapshot_serverid --password=$snapshot_serverpasswd --no-verbose ${BOOT_URL}/${bootname}

	if [ ! -f ${bootname} ]; then
		echo "Error on downloading ${bootname}"
		exit 0
	fi

}
enter_downloadmode_and_download_img() {
	cd ${WORKSPACE_DIR}
	filename=$1
	bootname=$2

	${COMMON_DIR}/sdb_root_on.sh
	if [ -f "${WORKSPACE_DIR}/Terminate_Test.txt" ]; then
		echo "sdb_root_on failure"
		exit 0
	fi

	if [ ${TIZEN_PROFILE} == "common-artik" ]; then
		cd ${CURRENT_DIR}/Download_bin/download_artik

		./download_artik.sh ${WORKSPACE_DIR}/${filename}

	elif [ ${TIZEN_PROFILE} == "mobile-tm1" ]; then
		echo "not supported mobile download"
	elif [ ${TIZEN_PROFILE} == "mobile-tm2" ]; then

		${COMMON_DIR}/sdb_shell.sh "reboot download"

		sleep 100

		lsusb

		lthor ${filename}

		sleep 40
	elif [ ${TIZEN_PROFILE} == "wearable-tw1" ];  then
		gunzip ${filename}

		${COMMON_DIR}/sdb_shell.sh "reboot download"

		sleep 100

		lsusb

		../Download_bin/odin4 -a ${filename/%.gz/}

		sleep 40
	elif [ ${TIZEN_PROFILE} == "wearable-tw2" ];  then
		gunzip ${filename}

		${COMMON_DIR}/sdb_shell.sh "reboot download"

		sleep 100

		lsusb

		../Download_bin/odin4 -a ${filename/%.gz/}

		sleep 40
	elif [ ${TIZEN_PROFILE} == "wearable-tw3" ];  then
		gunzip ${filename}

		${COMMON_DIR}/sdb_shell.sh "reboot download"

		sleep 100

		lsusb

		../Download_bin/odin4 -a ${filename/%.gz/}

		sleep 40
	elif [ ${TIZEN_PROFILE} == "mcd-solis" ];  then
		gunzip -k ${filename}

		${COMMON_DIR}/sdb_shell.sh "reboot download"

		sleep 100

		lsusb

		../Download_bin/odin4 -a ${filename/%.gz/}

		sleep 100
	elif [ ${TIZEN_PROFILE} == "mcd-galileo" ];  then
		gunzip -k ${filename}

		${COMMON_DIR}/sdb_shell.sh "reboot download"

		sleep 100

		lsusb

		../Download_bin/odin4 -a ${filename/%.gz/}

		sleep 100
	elif [ ${TIZEN_PROFILE} == "iot-rpi" ]; then

		${COMMON_DIR}/sdb_shell.sh "reboot download"

		sleep 100

		lsusb

		lthor $filename $bootname

		sleep 200
	elif [[ ${TIZEN_PROFILE} == "unified-rpi"* ]]; then
		${COMMON_DIR}/sdb_shell.sh "reboot download"

		sleep 100

		lsusb

		lthor $filename $bootname

		sleep 200

		# Trigger udev to rescan USB devices after image flashing
		# The board reboots with new image and USB device node may not be
		# automatically recognized by udev
		sudo -n udevadm trigger
		sleep 5
	fi


}



if [ $# -eq 0 ]; then
	echo "Usage : ./download_bin.sh [profile] [tizen version] [snapshot id] [cfg path] [workspace dir]"
	echo "        profile       : common-artik, mobile-tm1, wearable-tw1"
	echo "        tizen version : 3.0 4.0"
	echo "        snapshot id   : latest or 20160901.3"
	echo "        cfg path      : ../testprofiles.cfg"
	echo "        workspace_dir : ../workspace"
	exit 0
fi

TIZEN_PROFILE=$1
TIZEN_VERSION=$2
SNAPSHOT_ID=$3
CFG_PATH=$4
WORKSPACE_DIR=$5

rm -f ${WORKSPACE_DIR}/download_complete.txt

FULL_PROFILE=$(echo ${TIZEN_VERSION}-${TIZEN_PROFILE})

get_data_from_cfg $CFG_PATH $FULL_PROFILE $SNAPSHOT_ID

download_binary
download_boot
echo Filename : $filename
echo Bootname : $bootname
enter_downloadmode_and_download_img $filename $bootname

echo "complete" > ${WORKSPACE_DIR}/download_complete.txt
