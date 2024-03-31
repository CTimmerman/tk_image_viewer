#!/bin/sh
exec python ./main.py ${1+"$@"} -r -vv
