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
* MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
*
* You should have received a copy of the GNU General Public License
* along with this program. If not, see <http://www.gnu.org/licenses/>.
**/

package ebpfem

import (
	"fmt"
	"net"

	"github.com/pkg/errors"
	log "github.com/sirupsen/logrus"
	"github.com/vishvananda/netlink"

	"github.com/OpenFogStack/celestial/pkg/orchestrator"
)

//go:generate env BPF2GO_FLAGS="-O3" go run github.com/cilium/ebpf/cmd/bpf2go -target amd64 edt ebpf/net.c -- -I./ebpf/headers

func New() *EBPFem {
	return &EBPFem{
		vms: make(map[orchestrator.MachineID]*vm),
	}
}

func (e *EBPFem) Stop() error {
	e.Lock()
	defer e.Unlock()
	for _, v := range e.vms {
		err := v.objs.Close()
		if err != nil {
			return errors.WithStack(err)
		}
	}
	return nil
}

func (e *EBPFem) Register(id orchestrator.MachineID, netIf string) error {
	v := &vm{
		netIf: netIf,
		objs:  &edtObjects{},
		hbd:   make(map[string]*handleKbpsDelay),
	}

	v.Lock()
	defer v.Unlock()

	log.Tracef("loading ebpf objects for %s", id.String())
	if err := loadEdtObjects(v.objs, nil); err != nil {
		return errors.WithStack(err)
	}

	progFd := v.objs.edtPrograms.TcMain.FD()

	log.Tracef("getting interface %s", v.netIf)
	iface, err := getIface(v.netIf)
	if err != nil {
		log.Errorf("interface %s not found", v.netIf)
		return errors.WithStack(err)
	}

	// Create clsact qdisc
	log.Tracef("creating clsact qdisc for %s", v.netIf)
	_, err = createClsactQdisc(iface)
	if err != nil {
		log.Errorf("error creating clsact qdisc for %s", v.netIf)
		return errors.WithStack(err)
	}

	// Create fq qdisc
	log.Tracef("creating fq qdisc for %s", v.netIf)
	_, err = createFQdisc(iface)
	if err != nil {
		log.Tracef("error creating fq qdisc for %s", v.netIf)
		return errors.WithStack(err)
	}

	// Attach bpf program
	log.Tracef("attaching bpf program for %s", v.netIf)
	_, err = createTCBpfFilter(iface, progFd, netlink.HANDLE_MIN_EGRESS, "edt_bandwidth")
	if err != nil {
		log.Errorf("error attaching bpf program for %s", v.netIf)
		return errors.WithStack(err)
	}

	e.Lock()
	e.vms[id] = v
	e.Unlock()

	return nil
}

func (v *vm) getHBD(target net.IPNet) *handleKbpsDelay {
	hbd, ok := v.hbd[target.String()]
	if ok {
		return hbd
	}

	hbd = &handleKbpsDelay{
		throttleRateKbps: DEFAULT_BANDWIDTH_KBPS,
		delayUs:          DEFAULT_LATENCY_US,
	}

	v.hbd[target.String()] = hbd

	return hbd
}

// 生成 IPv6 地址
func generateIPv6(ipv4Addr string) (net.IPNet, error) {
	ip := net.ParseIP(ipv4Addr).To4()
	if ip == nil {
		return net.IPNet{}, errors.New("invalid IPv4 address")
	}

	ipv6 := fmt.Sprintf("fd00::%x:%x:%x:%x", ip[0], ip[1], ip[2], ip[3])
	return net.IPNet{IP: net.ParseIP(ipv6), Mask: net.CIDRMask(126, 128)}, nil
}

func (e *EBPFem) SetBandwidth(source orchestrator.MachineID, target net.IPNet, bandwidthKbits uint64) error {
	e.RLock()
	v, ok := e.vms[source]
	e.RUnlock()

	if !ok {
		return errors.Errorf("machine %d-%d does not exist", source.Group, source.Id)
	}

	v.Lock()
	defer v.Unlock()

	hbd := v.getHBD(target)
	hbd.throttleRateKbps = uint32(bandwidthKbits)

	ips, err := parseNetToLongs(target)
	if err != nil {
		return errors.WithStack(err)
	}

	for _, ip := range ips {
		log.Tracef("updating bandwidth for %d to %d", ip, bandwidthKbits)
		err = v.objs.IP_HANDLE_KBPS_DELAY.Put(ip, hbd)
		if err != nil {
			return errors.WithStack(err)
		}

		// 生成对应的 IPv6 地址并更新
		ipv4Addr := net.IPv4(byte(ip>>24), byte(ip>>16&0xFF), byte(ip>>8&0xFF), byte(ip&0xFF)).String()
		ipv6Net, err := generateIPv6(ipv4Addr)
		if err != nil {
			return errors.WithStack(err)
		}

		err = v.objs.IPV6_HANDLE_KBPS_DELAY.Put(ipv6Net.IP, hbd)
		if err != nil {
			return errors.WithStack(err)
		}
	}
	return nil
}

func (e *EBPFem) SetLatency(source orchestrator.MachineID, target net.IPNet, latency uint32) error {
	e.RLock()
	v, ok := e.vms[source]
	e.RUnlock()
	if !ok {
		return errors.Errorf("machine %d-%d does not exist", source.Group, source.Id)
	}

	v.Lock()
	defer v.Unlock()

	hbd := v.getHBD(target)
	hbd.delayUs = uint32(latency)

	ips, err := parseNetToLongs(target)
	if err != nil {
		return errors.WithStack(err)
	}

	for _, ip := range ips {
		log.Tracef("updating latency for %d to %d", ip, latency)
		err = v.objs.IP_HANDLE_KBPS_DELAY.Put(ip, hbd)
		if err != nil {
			return errors.WithStack(err)
		}

		// 生成对应的 IPv6 地址并更新
		ipv4Addr := net.IPv4(byte(ip>>24), byte(ip>>16&0xFF), byte(ip>>8&0xFF), byte(ip&0xFF)).String()
		ipv6Net, err := generateIPv6(ipv4Addr)
		if err != nil {
			return errors.WithStack(err)
		}

		err = v.objs.IPV6_HANDLE_KBPS_DELAY.Put(ipv6Net.IP, hbd)
		if err != nil {
			return errors.WithStack(err)
		}
	}
	return nil
}

// 省略 UnblockLink 和 BlockLink 的实现...
