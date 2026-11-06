#!/bin/bash

/usr/bin/vconftool set -t int db/setting/screen_lock_type 0 -rf
/usr/bin/vconftool set -t int db/setting/lcd_backlight_normal "600"

sync