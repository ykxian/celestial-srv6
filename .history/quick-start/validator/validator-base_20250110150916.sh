#!/bin/sh

#
# This file is part of Celestial (https://github.com/OpenFogStack/celestial).
# Copyright (c) 2024 Tobias Pfandzelter, The OpenFogStack Team.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#

# Our base script installs all the necessary dependencies for the validation
# script. This is actually only Python 3 and a few Python 3 packages.

# Add git, curl, and python3 to the root filesystem.
# git and curl are needed for pip.
sed -i 's/dl-cdn.alpinelinux.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apk/repositories
apk add git curl python3 py3-pip openssh

ln -sf sshd                     /etc/init.d/sshd.eth0
ln -sf /etc/init.d/sshd.eth0    /etc/runlevels/default/sshd.eth0

mkdir -m 0600 -p /root/.ssh/

ssh-keygen -A

cat >> /etc/conf.d/sshd << EOF
sshd_disable_keygen="yes"
rc_need="net.eth0"
EOF

sed -E -i /etc/ssh/sshd_config \
	-e "/^[# ]*PermitRootLogin .+$/d" \
	-e "/^[# ]*PermitEmptyPasswords .+$/d" \
	-e "/^[# ]*PubkeyAuthentication .+$/d"

	echo "
PermitRootLogin yes
PermitEmptyPasswords yes
PubkeyAuthentication yes
" | tee -a /etc/ssh/sshd_config >/dev/null

cp id_ed25519.pub /root/.ssh/authorized_keys

# Add the python3 dependencies: request and ping3
python3 -m pip install ping3 requests -i https://pypi.tuna.tsinghua.edu.cn/simple/
