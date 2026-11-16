#!/bin/sh
set -eu
cd "$(dirname "$0")"
sh 'mod_image.sh'
sh ./inline.sh
