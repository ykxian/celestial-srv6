#!/bin/sh

sh add_ipv6.sh

sysctl -w net.ipv6.conf.all.seg6_enabled=1 
sysctl -w net.ipv6.conf.default.seg6_enabled=1
sysctl -w net.ipv6.conf.eth0.seg6_enabled=1
sysctl -w net.ipv6.conf.all.forwarding=1

# while true; do
#     echo "$(date): gst server running!"
#     sleep 300
# done

echo "$(date): gst server running!"

python /srv6_route_manager.py
