#!/bin/bash

# 指定要删除的目标 IPv6 地址和网络接口
TARGET_IPV6="fd00::a:1:10:42"  # 替换为要删除的目标 IPv6 地址
INTERFACE="eth0"               # 替换为对应的网络接口

# 删除路由的命令
echo "Deleting IPv6 route for $TARGET_IPV6 on interface $INTERFACE..."
ip -6 route del "$TARGET_IPV6" dev "$INTERFACE"

# 检查命令是否成功
if [ $? -eq 0 ]; then
    echo "Route deletion successful."
else
    echo "Failed to delete route."
fi

