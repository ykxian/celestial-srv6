// Code generated by bpf2go; DO NOT EDIT.
//go:build 386 || amd64

package ebpfem

import (
	"bytes"
	_ "embed"
	"fmt"
	"io"

	"github.com/cilium/ebpf"
)

type edtHandleKbpsDelay struct {
	ThrottleRateKbps uint32
	DelayUs          uint32
}

type edtIn6Addr struct{ In6U struct{ U6Addr8 [16]uint8 } }

// loadEdt returns the embedded CollectionSpec for edt.
func loadEdt() (*ebpf.CollectionSpec, error) {
	reader := bytes.NewReader(_EdtBytes)
	spec, err := ebpf.LoadCollectionSpecFromReader(reader)
	if err != nil {
		return nil, fmt.Errorf("can't load edt: %w", err)
	}

	return spec, err
}

// loadEdtObjects loads edt and converts it into a struct.
//
// The following types are suitable as obj argument:
//
//	*edtObjects
//	*edtPrograms
//	*edtMaps
//
// See ebpf.CollectionSpec.LoadAndAssign documentation for details.
func loadEdtObjects(obj interface{}, opts *ebpf.CollectionOptions) error {
	spec, err := loadEdt()
	if err != nil {
		return err
	}

	return spec.LoadAndAssign(obj, opts)
}

// edtSpecs contains maps and programs before they are loaded into the kernel.
//
// It can be passed ebpf.CollectionSpec.Assign.
type edtSpecs struct {
	edtProgramSpecs
	edtMapSpecs
}

// edtSpecs contains programs before they are loaded into the kernel.
//
// It can be passed ebpf.CollectionSpec.Assign.
type edtProgramSpecs struct {
	TcMain *ebpf.ProgramSpec `ebpf:"tc_main"`
}

// edtMapSpecs contains maps before they are loaded into the kernel.
//
// It can be passed ebpf.CollectionSpec.Assign.
type edtMapSpecs struct {
	IPV6_HANDLE_KBPS_DELAY *ebpf.MapSpec `ebpf:"IPV6_HANDLE_KBPS_DELAY"`
	IP_HANDLE_KBPS_DELAY  *ebpf.MapSpec `ebpf:"IP_HANDLE_KBPS_DELAY"`
	FlowMap               *ebpf.MapSpec `ebpf:"flow_map"`
	FlowMapIpv6           *ebpf.MapSpec `ebpf:"flow_map_ipv6"`
}

// edtObjects contains all objects after they have been loaded into the kernel.
//
// It can be passed to loadEdtObjects or ebpf.CollectionSpec.LoadAndAssign.
type edtObjects struct {
	edtPrograms
	edtMaps
}

func (o *edtObjects) Close() error {
	return _EdtClose(
		&o.edtPrograms,
		&o.edtMaps,
	)
}

// edtMaps contains all maps after they have been loaded into the kernel.
//
// It can be passed to loadEdtObjects or ebpf.CollectionSpec.LoadAndAssign.
type edtMaps struct {
	IPV6_HANDLE_KBPS_DELAY *ebpf.Map `ebpf:"IPV6_HANDLE_KBPS_DELAY"`
	IP_HANDLE_KBPS_DELAY  *ebpf.Map `ebpf:"IP_HANDLE_KBPS_DELAY"`
	FlowMap               *ebpf.Map `ebpf:"flow_map"`
	FlowMapIpv6           *ebpf.Map `ebpf:"flow_map_ipv6"`
}

func (m *edtMaps) Close() error {
	return _EdtClose(
		m.IPV6HANDLE_KBPS_DELAY,
		m.IP_HANDLE_KBPS_DELAY,
		m.FlowMap,
		m.FlowMapIpv6,
	)
}

// edtPrograms contains all programs after they have been loaded into the kernel.
//
// It can be passed to loadEdtObjects or ebpf.CollectionSpec.LoadAndAssign.
type edtPrograms struct {
	TcMain *ebpf.Program `ebpf:"tc_main"`
}

func (p *edtPrograms) Close() error {
	return _EdtClose(
		p.TcMain,
	)
}

func _EdtClose(closers ...io.Closer) error {
	for _, closer := range closers {
		if err := closer.Close(); err != nil {
			return err
		}
	}
	return nil
}

// Do not access this directly.
//
//go:embed edt_x86_bpfel.o
var _EdtBytes []byte
