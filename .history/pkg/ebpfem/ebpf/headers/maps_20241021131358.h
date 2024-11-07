/*
 * This file is part of Celestial (https://github.com/OpenFogStack/celestial).
 * Copyright (c) 2024 Soeren Becker, Nils Japke, Tobias Pfandzelter, The
 * OpenFogStack Team.
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, version 3.
 *
 * This program is distributed in the hope that it will be useful, but
 * WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
 * General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program. If not, see <http://www.gnu.org/licenses/>.
 **/

// Adapted from: https://github.com/srnbckr/ebpf-network-emulation/blob/main/cmd/headers/maps.h

// 定义一个union 支持IPv4和IPv6
union ip_address {
    __u32 ipv4;            // IPv4 地址 (32 位)
    struct in6_addr ipv6;  // IPv6 地址 (128 位)
};

struct handle_kbps_delay
{
    __u32 throttle_rate_kbps;
    __u32 delay_us;
} HANDLE_KBPS_DELAY;

struct
{
    __uint(type, BPF_MAP_TYPE_HASH);
    __type(key, union ip_address); //使用联合类型作为键 支持IPv4和IPv6
    __type(value, HANDLE_KBPS_DELAY);
    __uint(max_entries, 65535);
} IP_HANDLE_KBPS_DELAY SEC(".maps");
