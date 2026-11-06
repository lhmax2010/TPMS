#!/bin/bash

command=$1

sdb -s $SDB_SERIAL shell $command
