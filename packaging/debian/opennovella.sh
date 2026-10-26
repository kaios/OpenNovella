#!/bin/sh
# OpenNovella launcher installed by the Debian package.
export PYTHONPATH="/usr/lib/opennovella${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m opennovella "$@"
