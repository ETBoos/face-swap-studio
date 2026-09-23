#!/bin/sh
set -eu

# Railway volumes are mounted after the image is built and initially belong to
# root. Fix the mount ownership at startup, then drop privileges for the server.
mkdir -p /data
chown fss:fss /data
exec su -s /bin/sh fss -c 'exec python -m face_swap_studio.licensing.server'
