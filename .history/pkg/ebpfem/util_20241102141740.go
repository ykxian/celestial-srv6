//go:build linux && amd64
// +build linux,amd64

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

package ebpfem

import (
	"bytes"
	"encoding/binary"
	"net"

	"github.com/pkg/errors"
	log "github.com/sirupsen/logrus"
	"github.com/vishvananda/netlink"
	"golang.org/x/sys/unix"
)

func incrementIP(ip net.IP) {
	for j := len(ip) - 1; j >= 0; j-- {
		ip[j]++
		if ip[j] > 0 {
			break
		}
	}
}

func parseIPToLong(ip net.IP) (interface{}, error) {
	if ip.To4() != nil {
		var l uint32
		err := binary.Read(bytes.NewBuffer(ip.To4()), binary.LittleEndian, &l)
		if err != nil {
			return nil, errors.Wrap(err, "cannot convert IPv4 to uint32")
		}
		return l, nil
	} else {
		// 对于 IPv6，返回原始字节
		return ip.To16(), nil
	}
}

// parseNetToLongs 解析 IP 地址，从 net.IP 解析到适当的格式（IPv4 为 uint32，IPv6 为 []byte）。
func parseNetToLongs(target net.IPNet) ([]interface{}, error) {
	var longs []interface{}

	if target.IP.To4() != nil {
		// IPv4 处理逻辑
		startIP := target.IP.Mask(target.Mask)
		endIP := make(net.IP, len(startIP))
		copy(endIP, startIP)
		for i := range endIP {
			endIP[i] |= ^target.Mask[i]
		}
		for ip := startIP; !ip.Equal(endIP); incrementIP(ip) {
			l, err := parseIPToLong(ip)
			if err != nil {
				return nil, errors.Wrap(err, "cannot convert IP to uint32")
			}
			longs = append(longs, l)
		}
		l, err := parseIPToLong(endIP)
		if err != nil {
			return nil, errors.Wrap(err, "cannot convert end IP to uint32")
		}
		longs = append(longs, l)
	} else {
		// IPv6 处理逻辑
		startIP := target.IP.Mask(target.Mask)
		endIP := make(net.IP, len(startIP))
		copy(endIP, startIP)
		for i := range endIP {
			endIP[i] |= ^target.Mask[i]
		}
		for ip := startIP; !ip.Equal(endIP); incrementIP(ip) {
			l, err := parseIPToLong(ip)
			if err != nil {
				return nil, errors.Wrap(err, "cannot convert IPv6 IP to bytes")
			}
			longs = append(longs, l)
		}
		l, err := parseIPToLong(endIP)
		if err != nil {
			return nil, errors.Wrap(err, "cannot convert end IPv6 IP to bytes")
		}
		longs = append(longs, l)
	}

	return longs, nil
}

func getIface(name string) (netlink.Link, error) {
	iface, err := netlink.LinkByName(name)
	if err != nil {
		return nil, errors.Wrapf(err, "cannot find %s", name)
	}
	return iface, nil
}

// CreateClsactQdisc 创建 clsact qdisc。
func createClsactQdisc(iface netlink.Link) (*netlink.GenericQdisc, error) {
	attrs := netlink.QdiscAttrs{
		LinkIndex: iface.Attrs().Index,
		Handle:    netlink.MakeHandle(0xffff, 0),
		Parent:    netlink.HANDLE_CLSACT,
	}

	qdisc := &netlink.GenericQdisc{
		QdiscAttrs: attrs,
		QdiscType:  "clsact",
	}

	if err := netlink.QdiscAdd(qdisc); err != nil {
		return nil, errors.Wrap(err, "Cannot add clsact qdisc")
	}
	log.Tracef("Added clsact qdisc %v", qdisc)
	return qdisc, nil
}

// CreateFQdisc 创建 fq qdisc。
func createFQdisc(iface netlink.Link) (*netlink.Fq, error) {
	attrs := netlink.QdiscAttrs{
		LinkIndex: iface.Attrs().Index,
		Handle:    netlink.MakeHandle(0x123, 0),
		Parent:    netlink.HANDLE_ROOT,
	}

	fq := &netlink.Fq{
		QdiscAttrs: attrs,
		Pacing:     0,
	}

	if err := netlink.QdiscAdd(fq); err != nil {
		return nil, errors.Wrap(err, "Cannot add fq qdisc")
	}
	log.Tracef("Added fq qdisc %v", fq)
	return fq, nil
}

// CreateTCBpfFilter 创建 BPF 过滤器并将其附加到指定的接口。
func createTCBpfFilter(iface netlink.Link, progFd int, parent uint32, name string) (*netlink.BpfFilter, error) {
	filterAttrs := netlink.FilterAttrs{
		LinkIndex: iface.Attrs().Index,
		Parent:    parent,
		Handle:    netlink.MakeHandle(0, 1),
		Protocol:  unix.ETH_P_ALL,
		Priority:  1,
	}

	filter := &netlink.BpfFilter{
		FilterAttrs:  filterAttrs,
		Fd:           progFd,
		Name:         name,
		DirectAction: true,
	}

	if err := netlink.FilterAdd(filter); err != nil {
		return nil, errors.Wrap(err, "Cannot attach bpf object to filter")
	}

	log.Tracef("Created bpf filter: %v", filter)
	return filter, nil
}
