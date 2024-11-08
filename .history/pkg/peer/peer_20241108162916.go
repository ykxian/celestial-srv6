/*
* This file is part of Celestial (https://github.com/OpenFogStack/celestial).
* Copyright (c) 2024 Tobias Pfandzelter, The OpenFogStack Team.
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

package peer

import (
	"fmt"
	"net"
	"os"
	"os/exec"
	"strconv"
	"sync"
	"time"

	"github.com/go-ping/ping"
	"github.com/pkg/errors"
	log "github.com/sirupsen/logrus"
	"golang.zx2c4.com/wireguard/wgctrl/wgtypes"

	"github.com/OpenFogStack/celestial/pkg/orchestrator"
)

type HostInfo struct {
	Addr      string
	PublicKey string
}

type peer struct {
	directAddr  net.IP
	wgAddr      net.IP
	wgAddrV6    net.IP // 新增 IPv6 地址
	allowedNets []*net.IPNet
	sync.Mutex  // can't have two goroutines modifying this at the same time

	port      uint16
	publicKey string
	// microseconds
	latency uint64
}

// PeeringService uses Wireguard to connect to other machines and route traffic to them.
type PeeringService struct {
	wgAddr      net.IP
	wgAddrV6    net.IP // 新增 IPv6 地址
	id          orchestrator.Host
	mask        string
	wgInterface string
	keyPath     string
	port        uint16

	publicKey string

	peers map[orchestrator.Host]*peer
}

// New creates a new PeeringService.
func New(mask string, keypath string, wginterface string, port uint16) (*PeeringService, error) {
	// set up wireguard
	if _, err := exec.LookPath("wg"); err != nil {
		return nil, errors.Errorf("could not find wireguard on this machine: %s", err.Error())
	}

	// remove old stuff first
	// ip link del [WGINTERFACE]
	cmd := exec.Command("ip", "link", "del", wginterface)
	// errors are ok
	_ = cmd.Run()

	log.Debugf("Removed old wg interface")
	// wg genkey
	k, err := wgtypes.GeneratePrivateKey()

	if err != nil {
		return nil, errors.WithStack(err)
	}

	privatekey := k.String()

	privateKeyFile, err := os.Create(keypath)

	if err != nil {
		return nil, errors.WithStack(err)
	}

	defer func(privateKeyFile *os.File) {
		err := privateKeyFile.Close()
		if err != nil {
			log.Error(err.Error())
		}
	}(privateKeyFile)

	if _, err := privateKeyFile.WriteString(privatekey); err != nil {
		return nil, errors.WithStack(err)
	}

	p := k.PublicKey()
	pubkey := p.String()

	log.Debugf("Private key: %s Public key %s", privatekey, pubkey)

	return &PeeringService{
		mask:        mask,
		wgInterface: wginterface,
		keyPath:     keypath,
		port:        port,
		publicKey:   pubkey,
		peers:       make(map[orchestrator.Host]*peer),
	}, nil
}

func (p *PeeringService) Register(host orchestrator.Host) (publickey string, listenaddr string, err error) {
	wgaddr, err := getWGAddr(host, false) // IPv4 地址
	if err != nil {
		return "", "", errors.WithStack(err)
	}

	wgaddrV6, err := getWGAddr(host, true) // IPv6 地址
	if err != nil {
		return "", "", errors.WithStack(err)
	}

	p.wgAddr = wgaddr
	p.wgAddrV6 = wgaddrV6
	p.id = host

	// ip link add [WGINTERFACE] type wireguard
	cmd := exec.Command("ip", "link", "add", p.wgInterface, "type", "wireguard")
	if out, err := cmd.CombinedOutput(); err != nil {
		return "", "", errors.Wrapf(err, "%#v: output: %s", cmd.Args, out)
	}

	// ip addr add [OWN_WG_ADDRESS] dev [WGINTERFACE]
	cmd = exec.Command("ip", "addr", "add", p.wgAddr.String()+p.mask, "dev", p.wgInterface)
	if out, err := cmd.CombinedOutput(); err != nil {
		return "", "", errors.Wrapf(err, "%#v: output: %s", cmd.Args, out)
	}

	// 添加 IPv6 地址
	cmd = exec.Command("ip", "addr", "add", p.wgAddrV6.String()+"/64", "dev", p.wgInterface)
	if out, err := cmd.CombinedOutput(); err != nil {
		return "", "", errors.Wrapf(err, "%#v: output: %s", cmd.Args, out)
	}

	// wg set [WGINTERFACE] private-key [PRIVATE_KEY_FILE] listen-port [WG_PORT]
	cmd = exec.Command("wg", "set", p.wgInterface, "private-key", p.keyPath, "listen-port", strconv.Itoa(int(p.port)))
	if out, err := cmd.CombinedOutput(); err != nil {
		return "", "", errors.Wrapf(err, "%#v: output: %s", cmd.Args, out)
	}

	// ip link set [WGINTERFACE] up
	cmd = exec.Command("ip", "link", "set", p.wgInterface, "up")
	if out, err := cmd.CombinedOutput(); err != nil {
		return "", "", errors.Wrapf(err, "%#v: output: %s", cmd.Args, out)
	}

	return p.publicKey, fmt.Sprintf(":%d", p.port), nil
}

func (p *PeeringService) GetHostID() (uint8, error) {
	if p.wgAddr == nil {
		return 0, errors.Errorf("not registered yet")
	}

	return uint8(p.id), nil
}

func (p *PeeringService) Route(network net.IPNet, host orchestrator.Host) error {
	h, ok := p.peers[host]
	if !ok {
		return errors.Errorf("unknown host %d", host)
	}

	h.Lock()
	defer h.Unlock()
	h.allowedNets = append(h.allowedNets, &network)

	// 初始化 allowed-ips 列表，包括主 IPv4 和 IPv6 地址
	allowedCIDRs := h.wgAddr.String() + "/32"
	if h.wgAddrV6 != nil {
		allowedCIDRs += "," + h.wgAddrV6.String() + "/128"
	}

	// 遍历所有 allowedNets，添加 IPv4 和 IPv6 子网
	for _, n := range h.allowedNets {
		allowedCIDRs += "," + n.String() // IPv4 子网
		// 将 IPv4 子网转换为 IPv6 并添加到 allowedCIDRs
		ipv6Subnet, err := convertIPv4ToIPv6Subnet(*n)
		if err != nil {
			return errors.WithStack(err)
		}
		allowedCIDRs += "," + ipv6Subnet
	}

	// 配置 WireGuard allowed-ips
	cmd := exec.Command("wg", "set", p.wgInterface, "peer", h.publicKey, "allowed-ips", allowedCIDRs)
	if out, err := cmd.CombinedOutput(); err != nil {
		return errors.Wrapf(err, "%#v: output: %s", cmd.Args, out)
	}

	// 删除旧的 IPv4 路由
	cmd = exec.Command("ip", "route", "del", network.String())
	_, _ = cmd.CombinedOutput() // 忽略删除错误

	// 添加新的 IPv4 路由
	cmd = exec.Command("ip", "route", "add", network.String(), "via", h.wgAddr.String(), "dev", p.wgInterface)
	if out, err := cmd.CombinedOutput(); err != nil {
		return errors.Wrapf(err, "%#v: output: %s", cmd.Args, out)
	}

	// 将当前 IPv4 子网转换为 IPv6 子网
	ipv6Subnet, err := convertIPv4ToIPv6Subnet(network)
	if err != nil {
		return errors.WithStack(err)
	}

	// 删除旧的 IPv6 路由
	cmd = exec.Command("ip", "-6", "route", "del", ipv6Subnet)
	_, _ = cmd.CombinedOutput() // 忽略删除错误

	// 添加新的 IPv6 路由
	cmd = exec.Command("ip", "-6", "route", "add", ipv6Subnet, "via", h.wgAddrV6.String(), "dev", p.wgInterface)
	if out, err := cmd.CombinedOutput(); err != nil {
		return errors.Wrapf(err, "%#v: output: %s", cmd.Args, out)
	}

	return nil
}

func convertIPv4ToIPv6Subnet(ipv4Net net.IPNet) (string, error) {
	ipv4 := ipv4Net.IP.To4()
	if ipv4 == nil {
		return "", errors.New("invalid IPv4 address")
	}
	return fmt.Sprintf("fd00::%x:%x:%x:%x/126", ipv4[0], ipv4[1], ipv4[2], ipv4[3]), nil
}

func getWGAddr(host orchestrator.Host, ipv6 bool) (net.IP, error) {
	if host > 253 {
		return nil, errors.Errorf("index %d is larger than allowed 253", host)
	}
	if ipv6 {
		// 使用 fd00::c0:a8:32:XX 前缀并嵌入 host 相关字节
		return net.ParseIP(fmt.Sprintf("fd00::c0:a8:32:%x", 0x02+host)), nil
	}
	// 默认返回 IPv4 地址
	return net.IPv4(0xC0, 0xA8, 0x32, byte(0x02+host)), nil
}

func (p *PeeringService) InitPeering(remotes map[orchestrator.Host]HostInfo) error {
	for remote, info := range remotes {
		if remote == p.id {
			continue
		}

		remoteWgAddr, err := getWGAddr(remote, false) // IPv4 地址
		if err != nil {
			return errors.WithStack(err)
		}

		remoteWgAddrV6, err := getWGAddr(remote, true) // IPv6 地址
		if err != nil {
			return errors.WithStack(err)
		}

		addr, port, err := net.SplitHostPort(info.Addr)
		if err != nil {
			return errors.WithStack(err)
		}

		portNum, err := strconv.ParseUint(port, 10, 16)
		if err != nil {
			return errors.WithStack(err)
		}

		r := &peer{
			directAddr:  net.ParseIP(addr),
			wgAddr:      remoteWgAddr,
			wgAddrV6:    remoteWgAddrV6,
			allowedNets: []*net.IPNet{},
			port:        uint16(portNum),
			publicKey:   info.PublicKey,
		}

		// wg set [WGINTERFACE] peer [PEER_PUBLICKEY] allowed-ips [PEER_WG_ADDR]/32,[PEER_WG_ADDRV6]/128 endpoint [PEER_DIRECT_ADDR]:[WGPORT]
		cmd := exec.Command("wg", "set", p.wgInterface, "peer", r.publicKey, "allowed-ips", r.wgAddr.String()+"/32,"+r.wgAddrV6.String()+"/128", "endpoint", net.JoinHostPort(r.directAddr.String(), port))
		if out, err := cmd.CombinedOutput(); err != nil {
			return errors.Wrapf(err, "%#v: output: %s", cmd.Args, out)
		}

		// test latency to this peer
		pinger, err := ping.NewPinger(r.directAddr.String())
		if err != nil {
			return errors.WithStack(err)
		}

		pinger.SetPrivileged(true)
		pinger.Count = 5
		pinger.Timeout = 5 * time.Second

		err = pinger.Run() // Blocks until finished.
		if err != nil {
			return errors.WithStack(err)
		}

		stats := pinger.Statistics() // get send/receive/duplicate/rtt stats

		// AvgRtt in Nanoseconds / 1e3 -> yields average rtt in microseconds
		// average rtt / 2.0 -> yields one way latency
		r.latency = uint64((stats.AvgRtt.Nanoseconds() / 1e3) / 2.0)

		log.Debugf("Latency %dus", r.latency)
		log.Infof("Determined a latency of %dus to host %s", r.latency, r.directAddr)

		p.peers[remote] = r
	}

	return nil
}

func (p *PeeringService) Stop() error {
	// ip link del [WGINTERFACE]
	cmd := exec.Command("ip", "link", "del", p.wgInterface)
	if out, err := cmd.CombinedOutput(); err != nil {
		return errors.Wrapf(err, "%#v: output: %s", cmd.Args, out)
	}

	return nil
}
