#!/bin/bash

if [ $# -lt 1 ]
then
	echo "Please, give at least one option"
	echo "Usage) checktap.sh on 	/* turn on the checktap */"
	echo "Usage) checktap.sh off 	/* turn off the checktap */"
	exit -1
fi

python3 checktap_cli.py $1
