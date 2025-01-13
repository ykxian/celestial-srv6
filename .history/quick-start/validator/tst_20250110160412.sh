#!/bin/sh

sh add_ipv6.sh

sysctl -w net.ipv6.conf.all.seg6_enabled=1 
sysctl -w net.ipv6.conf.default.seg6_enabled=1
sysctl -w net.ipv6.conf.eth0.seg6_enabled=1
sysctl -w net.ipv6.conf.all.forwarding=1

python3 validator.py info.celestial
