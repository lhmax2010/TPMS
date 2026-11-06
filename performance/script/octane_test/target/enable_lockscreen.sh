#!/bin/bash

/usr/bin/vconftool set -t int db/setting/screen_lock_type 1 -rf
/usr/bin/vconftool set -t int db/setting/lcd_backlight_normal "30"

sync