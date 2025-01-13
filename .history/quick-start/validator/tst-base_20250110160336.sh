#!/bin/sh

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
