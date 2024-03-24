#!/bin/sh
exec python ./main.py -r ${1+"$@"}
