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

# Our application script runs as soon as the microVM boots. Here, we mostly
# need to start our validator.py script. This script requires one input:
# the address of the HTTP info server. Using our builder, this is set as the
# hostname "info.celestial".

# Now we can start our validator script!

sh add_ipv6.sh

sysctl -w net.ipv6.conf.all.seg6_enabled=1 
sysctl -w net.ipv6.conf.default.seg6_enabled=1
sysctl -w net.ipv6.conf.eth0.seg6_enabled=1
sysctl -w net.ipv6.conf.all.forwarding=1

python3 validator.py info.celestial
