#!/bin/sh

sed -i 's/dl-cdn.alpinelinux.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apk/repositories
apk add git curl python3 py3-pip openssh iperf3 xauth

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
    -e "/^[# ]*PubkeyAuthentication .+$/d" \
    -e "/^[# ]*X11Forwarding .+$/d" \
    -e "/^[# ]*X11UseLocalhost .+$/d" \
    -e "/^[# ]*AllowTcpForwarding .+$/d"

echo "
PermitRootLogin yes
PermitEmptyPasswords yes
PubkeyAuthentication yes
X11Forwarding yes
X11UseLocalhost no
AllowTcpForwarding yes
" | tee -a /etc/ssh/sshd_config >/dev/null

cp id_ed25519.pub /root/.ssh/authorized_keys

python3 -m pip install httpx -i https://pypi.tuna.tsinghua.edu.cn/simple/

apk add bcc-tools py3-bcc ffmpeg mpv

wget https://githubfast.com/bluenviron/mediamtx/releases/download/v1.11.3/mediamtx_v1.11.3_linux_amd64.tar.gz #下载RTSP服务器

tar xzf mediamtx_v1.11.3_linux_amd64.tar.gz

rm mediamtx_v1.11.3_linux_amd64.tar.gz




