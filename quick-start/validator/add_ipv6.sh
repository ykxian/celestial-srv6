#!/bin/sh

# 获取 eth0 接口的 IPv4 地址
IPV4_ADDR=$(ip -4 addr show dev eth0 | grep -o 'inet [0-9]\+\(\.[0-9]\+\)\{3\}' | awk '{print $2}')

# 检查是否成功获取 IPv4 地址
if [ -z "$IPV4_ADDR" ]; then
    echo "Error: Could not retrieve IPv4 address for eth0."
    exit 1
fi

# 将 IPv4 地址的每一部分分开
IPV4_PART1=$(echo "$IPV4_ADDR" | cut -d '.' -f 1)
IPV4_PART2=$(echo "$IPV4_ADDR" | cut -d '.' -f 2)
IPV4_PART3=$(echo "$IPV4_ADDR" | cut -d '.' -f 3)
IPV4_PART4=$(echo "$IPV4_ADDR" | cut -d '.' -f 4)

# 将每个部分转换为16进制
IPV4_PART1_HEX=$(printf '%x' "$IPV4_PART1")
IPV4_PART2_HEX=$(printf '%x' "$IPV4_PART2")
IPV4_PART3_HEX=$(printf '%x' "$IPV4_PART3")
IPV4_PART4_HEX=$(printf '%x' "$IPV4_PART4")

# 生成全局 IPv6 地址，使用前缀 fd00:: 和 IPv4 的四个部分（16进制表示）嵌入到 IPv6 地址的后64位中
IPV6_ADDR="fd00::${IPV4_PART1_HEX}:${IPV4_PART2_HEX}:${IPV4_PART3_HEX}:${IPV4_PART4_HEX}"

# 添加 IPv6 地址到 eth0 接口
echo "Adding global IPv6 address $IPV6_ADDR/64 to interface eth0"
ip -6 addr add "$IPV6_ADDR/126" dev eth0

# 检查是否添加成功
if [ $? -eq 0 ]; then
    echo "Successfully added global IPv6 address to eth0"
else
    echo "Failed to add global IPv6 address to eth0"
    exit 1
fi

# 生成 IPv6 网关地址，假设最后一部分减 1
LAST_PART_HEX=$((IPV4_PART4 - 1))
IPV6_GATEWAY="fd00::${IPV4_PART1_HEX}:${IPV4_PART2_HEX}:${IPV4_PART3_HEX}:$(printf '%x' "$LAST_PART_HEX")"

# 添加默认 IPv6 路由到网关地址
echo "Adding default IPv6 route via $IPV6_GATEWAY"
ip -6 route add default via "$IPV6_GATEWAY" dev eth0

# 检查是否添加成功
if [ $? -eq 0 ]; then
    echo "Successfully added default IPv6 route via $IPV6_GATEWAY"
else
    echo "Failed to add default IPv6 route via $IPV6_GATEWAY"
    exit 1
fi

# 查看配置结果
ip -6 addr show dev eth0
ip -6 route show dev eth0

