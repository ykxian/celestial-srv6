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

#include <stdint.h>
#include <linux/bpf.h>
#include <linux/if_ether.h>
#include <linux/stddef.h>
#include <linux/in.h>
#include <linux/ip.h>
#include <linux/pkt_cls.h>
#include <linux/tcp.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_endian.h>
#include "helpers.h"
#include "maps.h"

/* 允许的最大延迟（超出范围则丢弃数据包） */
#define TIME_HORIZON_NS (2000 * 1000 * 1000)
#define NS_PER_SEC 1000000000
#define ECN_HORIZON_NS 999999000000
#define NS_PER_US 1000

/* flow_key => last_tstamp 时间戳 */
struct
{
    __uint(type, BPF_MAP_TYPE_HASH);
    __type(key, uint32_t);
    __type(value, uint64_t);
    __uint(max_entries, 65535);
} flow_map SEC(".maps");

/* 针对 IPv6 的时间戳映射 */
// struct
// {
//     __uint(type, BPF_MAP_TYPE_HASH);
//     __type(key, struct in6_addr);
//     __type(value, uint64_t);
//     __uint(max_entries, 65535);
// } flow_map_ipv6 SEC(".maps");

static inline int throttle_flow(struct __sk_buff *skb, void *address, uint32_t *throttle_rate_kbps, int is_ipv6)
{
    // 如果速率为 0，则丢弃数据包
    if (*throttle_rate_kbps == 0)
    {
        return TC_ACT_SHOT;
    }

    uint64_t *last_tstamp;
    uint64_t delay_ns = ((uint64_t)skb->len) * NS_PER_SEC / 1000 / *throttle_rate_kbps;
    uint64_t now = bpf_ktime_get_ns();
    uint64_t tstamp, next_tstamp = 0;

    // if (is_ipv6) {
    //     struct in6_addr *ipv6_address = (struct in6_addr *)address;
    //     last_tstamp = bpf_map_lookup_elem(&flow_map_ipv6, ipv6_address);
    //     if (last_tstamp) {
    //         next_tstamp = *last_tstamp + delay_ns;
    //     }
    // } else {
    //     uint32_t key = *(uint32_t *)address;
    //     last_tstamp = bpf_map_lookup_elem(&flow_map, &key);
    //     if (last_tstamp) {
    //         next_tstamp = *last_tstamp + delay_ns;
    //     }
    // }

    if (!is_ipv6)
    {
        uint32_t key = *(uint32_t *)address;
        last_tstamp = bpf_map_lookup_elem(&flow_map, &key);
        if (last_tstamp) {
            next_tstamp = *last_tstamp + delay_ns;
    }

    // 检查当前时间戳
    tstamp = skb->tstamp;
    if (tstamp < now) {
        tstamp = now;
    }

    // 如果可以发送数据包
    if (next_tstamp <= tstamp) {
        // if (is_ipv6) {
        //     struct in6_addr *ipv6_address = (struct in6_addr *)address;
        //     if (bpf_map_update_elem(&flow_map_ipv6, ipv6_address, &tstamp, BPF_ANY)) {
        //         return TC_ACT_SHOT;
        //     }
        // } else {
        //     uint32_t key = *(uint32_t *)address;
        //     if (bpf_map_update_elem(&flow_map, &key, &tstamp, BPF_ANY)) {
        //         return TC_ACT_SHOT;
        //     }
        // }

        if (!is_ipv6)
        {
            uint32_t key = *(uint32_t *)address;
            if (bpf_map_update_elem(&flow_map, &key, &tstamp, BPF_ANY)) {
                return TC_ACT_SHOT;
        }
        return TC_ACT_OK;
    }

    // 不允许排队超过 2 秒
    if (next_tstamp - now >= TIME_HORIZON_NS) {
        return TC_ACT_SHOT;
    }

    // 如果需要，设置 ECN 位
    if (next_tstamp - now >= ECN_HORIZON_NS) {
        bpf_skb_ecn_set_ce(skb);
    }

    // 更新映射中的时间戳
    if (is_ipv6) {
        struct in6_addr *ipv6_address = (struct in6_addr *)address;
        if (bpf_map_update_elem(&flow_map_ipv6, ipv6_address, &next_tstamp, BPF_EXIST)) {
            return TC_ACT_SHOT;
        }
    } else {
        uint32_t key = *(uint32_t *)address;
        if (bpf_map_update_elem(&flow_map, &key, &next_tstamp, BPF_EXIST)) {
            return TC_ACT_SHOT;
        }
    }

    // 设置数据包的延迟时间戳
    skb->tstamp = next_tstamp;
    return TC_ACT_OK;
}

static inline int inject_delay(struct __sk_buff *skb, uint32_t *delay_us)
{
    uint64_t delay_ns = (*delay_us) * NS_PER_US;

    // 检查 skb->tstamp 是否为 0
    if (skb->tstamp == 0)
    {
        skb->tstamp = bpf_ktime_get_ns() + delay_ns;
        return TC_ACT_OK;
    }

    uint64_t new_ts =((uint64_t)skb->tstamp) + delay_ns;
    skb->tstamp = new_ts;  // 添加延迟

    return TC_ACT_OK;
}

SEC("tc")
int tc_main(struct __sk_buff *skb)
{
    void *data_end = (void *)(unsigned long long)skb->data_end;
    void *data = (void *)(unsigned long long)skb->data;

    struct hdr_cursor nh;
    struct ethhdr *eth;
    struct iphdr *iphdr;
    struct ipv6hdr *ipv6hdr;

    int eth_type;

    nh.pos = data;

    // 解析以太网头
    eth_type = parse_ethhdr(&nh, data_end, &eth);
    if (eth_type == bpf_htons(ETH_P_IP))
    {
        // 处理 IPv4
        int ip_type = parse_iphdr(&nh, data_end, &iphdr);
        if (ip_type == IPPROTO_ICMP || ip_type == IPPROTO_TCP || ip_type == IPPROTO_UDP)
        {
            __u32 ip_address = iphdr->saddr;
            struct handle_kbps_delay *val_struct = bpf_map_lookup_elem(&IP_HANDLE_KBPS_DELAY, &ip_address);
            if (!val_struct) {
                return TC_ACT_OK;  // 没有找到对应条目
            }

            __u32 *throttle_rate_kbps = &val_struct->throttle_rate_kbps;
            int ret = throttle_flow(skb, &ip_address, throttle_rate_kbps, 0);
            if (ret != TC_ACT_OK) {
                return ret;
            }

            __u32 *delay_us = &val_struct->delay_us;
            return inject_delay(skb, delay_us);
        }
    }
    // else if (eth_type == bpf_htons(ETH_P_IPV6))
    // {
    //     // 处理 IPv6
    //     int ipv6_type = parse_ipv6hdr(&nh, data_end, &ipv6hdr);
    //     if (ipv6_type == IPPROTO_ICMPV6 || ipv6_type == IPPROTO_TCP || ipv6_type == IPPROTO_UDP)
    //     {
    //         struct in6_addr ipv6_address = ipv6hdr->saddr; // 获取源 IPv6 地址
    //         struct handle_kbps_delay *val_struct = bpf_map_lookup_elem(&IPV6_HANDLE_KBPS_DELAY, &ipv6_address);
    //         if (!val_struct) {
    //             return TC_ACT_OK;  // 没有找到对应条目
    //         }

    //         __u32 *throttle_rate_kbps = &val_struct->throttle_rate_kbps;
    //         int ret = throttle_flow(skb, &ipv6_address, throttle_rate_kbps, 1);
    //         if (ret != TC_ACT_OK) {
    //             return ret;  // 返回状态
    //         }

    //         __u32 *delay_us = &val_struct->delay_us;
    //         return inject_delay(skb, delay_us);
    //     }
    // }
    return TC_ACT_OK;
}

char _license[] SEC("license") = "GPL";
