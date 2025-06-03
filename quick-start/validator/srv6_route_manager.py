import sys
import json
import time
import socket
import threading
import subprocess
import ipaddress
import httpx
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass
from bcc import BPF

# --------------------------
# 配置参数
# --------------------------
CONFIG = {
    "api_base": "http://info.celestial",
    "interface": "eth0",      # 监听的网络接口
    "route_ttl": 15,          # 路由有效期（秒）
    "update_interval": 5,     # 路由更新间隔（秒）
    "seg6_mtu": 1500,        # 设置SRv6路由的mtu值
    "visual_api": "http://192.168.3.46:8080/api/route"  # 可视化系统API地址
}

# --------------------------
# 数据结构
# --------------------------
@dataclass
class NodeID:
    shell: int      # 地面站时shell为0
    id: int

# --------------------------
# 核心功能实现
# --------------------------
class SRv6DynamicRouter:
    def __init__(self):
        self.lock = threading.Lock()
        self.http = httpx.Client(base_url=CONFIG["api_base"], timeout=30)
        self.node_info = self._get_self_info()
        self.self_ipv6=ipaddress.IPv6Address(self._calculate_ip(self.node_info.shell,self.node_info.id))
        self.n_ipv6=self.self_ipv6-1
        self.active_routes: Dict[str, dict] = {}

        # 新增线程管理变量
        self.update_threads = {}  # 格式: { dest_ip: threading.Thread }
        self.thread_lock = threading.Lock()  # 线程操作专用锁
        
        # 初始化eBPF监控
        self.bpf = BPF(text=self._load_ebpf_program())
        fn = self.bpf.load_func("trace_ipv6_out", BPF.SOCKET_FILTER)
        self.bpf.attach_raw_socket(fn, CONFIG["interface"])
        self.bpf["route_events"].open_perf_buffer(self.handle_event)
        
        # 启动后台线程
        threading.Thread(target=self._event_loop, daemon=True).start()
        threading.Thread(target=self._cleanup_loop, daemon=True).start()
        
        # 检查可视化系统连接
        self._check_visual_system()
        
        print(f"✅ 路由器初始化完成，监控接口: {CONFIG['interface']}")
        
    def _check_visual_system(self):
        """检查可视化系统连接状态"""
        if "visual_api" in CONFIG and CONFIG["visual_api"]:
            try:
                # 发送测试请求到可视化系统
                resp = httpx.get(
                    CONFIG["visual_api"].rsplit('/', 1)[0] + "/status",  # 假设有状态检查接口
                    timeout=3
                )
                if resp.status_code == 200:
                    print(f"✅ 可视化系统连接成功: {CONFIG['visual_api']}")
                else:
                    print(f"⚠️ 可视化系统响应异常: {resp.status_code}")
            except Exception as e:
                print(f"⚠️ 可视化系统连接失败: {str(e)}，路由更新将不会发送到可视化系统")
        else:
            print("ℹ️ 未配置可视化系统，路由更新将不会发送到可视化系统")

    def _load_ebpf_program(self) -> str:
        """去除非必要调试函数后的安全版本"""
        return r"""
        #include <uapi/linux/ptrace.h>
        #include <net/sock.h>
        #include <bcc/proto.h>
        #include <linux/if_ether.h>
        #include <linux/ipv6.h>
        
        struct route_event {
            u8 daddr[16];
            u8 saddr[16];
        };
        
        BPF_PERF_OUTPUT(route_events);
        
        int trace_ipv6_out(struct __sk_buff *skb) {
            // 基础以太网头解析
            struct ethhdr eth = {};
            if (bpf_skb_load_bytes(skb, 0, &eth, sizeof(eth)) < 0) {
                return 0;
            }

            // 仅处理IPv6流量
            if (eth.h_proto != bpf_htons(ETH_P_IPV6)) {
                return 0;
            }
            
            // 计算IPv6头偏移量（无需处理VLAN）
            const u32 ip6_offset = sizeof(struct ethhdr);
            
            // 加载IPv6头
            struct ipv6hdr ip6 = {};
            if (bpf_skb_load_bytes(skb, ip6_offset, &ip6, sizeof(ip6)) < 0) {
                return 0;
            }
            
            // 精确匹配fd00::/16（前两个字节）
            if (ip6.daddr.in6_u.u6_addr8[0] != 0xfd || 
                ip6.daddr.in6_u.u6_addr8[1] != 0x00) {
                return 0;
            }
            
            // 提交事件
            struct route_event evt = {};
            __builtin_memcpy(evt.saddr, ip6.saddr.in6_u.u6_addr8, 16);  // 新增此行
            __builtin_memcpy(evt.daddr, ip6.daddr.in6_u.u6_addr8, 16);
            route_events.perf_submit(skb, &evt, sizeof(evt));
            return 0;
        }
        """

    def _get_self_info(self) -> NodeID:
        """获取本机节点信息（带重试机制）"""
        for _ in range(3):
            try:
                resp = self.http.get("/self")
                resp.raise_for_status()
                data = resp.json()
                
                return NodeID(
                    shell=data["identifier"]["shell"],
                    id=data["identifier"]["id"]
                )
            except Exception as e:
                print(f"⚠️ 获取节点信息失败: {str(e)}，1秒后重试...")
                time.sleep(1)
        raise RuntimeError("❌ 无法获取本机节点信息")

    def _build_path_url(self, dest_ip: str) -> str:
        """构造路径查询URL"""
        target = self._ip_to_node_id(dest_ip)
        
        # 构造源路径段
        src_part = f"{self.node_info.shell}/{self.node_info.id}"
        
        # 构造目标路径段
        dest_part =  f"{target.shell}/{target.id}"
        
        return f"/path/{src_part}/{dest_part}"

    def _ip_to_node_id(self, ipv6: str) -> NodeID:
        """将FD00开头的IPv6地址解析为节点信息"""
        try:
            parts = ipv6.split(":")[-4:]
            
            # 提取关键字段并转换为整数
            b = int(parts[1], 16)
            c = int(parts[2], 16)
            d = int(parts[3], 16)
        
            return NodeID(b,(c<<6)|((d-2)>>2))
        except Exception as e:
            print(f"解析错误: {str(e)}")
            return NodeID(-1, -1)
    
    def _process_path(self, json_data: dict) -> Tuple[Optional[str], List[str]]:
        """路径处理（严格过滤无效节点）"""
        try:
            segments = json_data.get("segments", [])
            if len(segments) < 1:
                raise ValueError("路径段为空")

            intermediate_nodes = []
            # 严格处理中间节点
            for seg in segments[:-1]:  # 排除最后一段
                target = seg.get("target", {})
                tgt_shell = target.get("shell", 0)
                tgt_id = target.get("id", 0)

                # 参数有效性验证
                if not (0 <= tgt_shell <= 255 and 0 <= tgt_id <= 0xFFFF):
                    raise ValueError(f"无效节点参数 shell={tgt_shell} id={tgt_id}")

                # 生成并验证IPv6地址
                ipv6 = self._calculate_ip(tgt_shell, tgt_id)
                try:
                    ipaddress.IPv6Address(ipv6)
                    intermediate_nodes.append(ipv6)
                except ipaddress.AddressValueError:
                    raise ValueError(f"生成无效中间节点地址: {ipv6}")
            print(f"🔄 生成中间节点列表: {intermediate_nodes}")
            return self._get_final_ip(segments[-1]), intermediate_nodes
        except Exception as e:
            print(f"❌ 路径处理失败: {str(e)}")
            return None, []

    def _get_final_ip(self, segment: dict) -> str:
        """处理最终目标节点"""
        target = segment.get("target", {})

        shell = target.get("shell", 0)
        node_id = target.get("id", 0)
    
        final_ip = self._calculate_ip(shell, node_id)
        try:
            ipaddress.IPv6Address(final_ip)
            return final_ip
        except ipaddress.AddressValueError:
            raise ValueError(f"最终目标地址无效: {final_ip}")

    @staticmethod
    def _calculate_ip(shell: int, node_id: int) -> str:
        """
        根据 shell_id 和 satellite_id 计算 IPv4 和 IPv6 地址。
        """
        byte1 = 10  # 固定为10
        byte2 = shell  # shell 标识符
        byte3 = (node_id >> 6) & 0xFF  # 卫星标识符，右移6位
        byte4 = (node_id << 2) & 0xFF  # 卫星标识符，左移2位

        # 计算 IPv6 地址
        ipv6_address = f"fd00::{byte1:x}:{byte2:x}:{byte3:x}:{(byte4 + 2):x}"

        return ipv6_address

    def _route_manager(self, dest_ip: str):
        """路由管理（新增空节点判断）"""
        with self.lock:
            try:
                path_url = self._build_path_url(dest_ip)
                print(f"🌐 正在请求API路径: {path_url}")

                resp = self.http.get(path_url, timeout=5)
                resp.raise_for_status()
                
                # 获取原始路径数据用于可视化
                path_data = resp.json()
                
                final_ip, segments = self._process_path(path_data)
                if not final_ip:
                    return

                # 关键修改：无中间节点时删除路由
                if not segments:
                    print(f"🔄 路径无中间节点，清理路由: {final_ip}")
                    if final_ip in self.active_routes:
                        self._remove_route(final_ip)
                        del self.active_routes[final_ip]
                    return

                # 路由安装/更新逻辑
                if final_ip in self.active_routes:
                    if segments != self.active_routes[final_ip]["segments"]:
                        self._install_route(final_ip, segments)
                        # 发送路由信息到可视化系统
                        self._send_route_to_visual(dest_ip, final_ip, segments, path_data)
                    else:
                        self.active_routes[final_ip]["last_used"] = time.time()
                else:
                    self._install_route(final_ip, segments)
                    # 发送路由信息到可视化系统
                    self._send_route_to_visual(dest_ip, final_ip, segments, path_data)
                
            except httpx.HTTPStatusError as e:
                print(f"❌ API错误: {e.response.status_code}")
            except Exception as e:
                print(f"❌ 路由管理失败: {str(e)}")

    def _install_route(self, dest_ip: str, segments: List[str]):
        """路由安装（严格单线程控制）"""
        if not segments:
            print(f"⏭️ 空节点列表，跳过路由安装: {dest_ip}")
            return
            
        try:
            # 构造动态参数命令
            cmd = [
                "ip", "-6", "route", "replace", dest_ip,
                "encap", "seg6", "mode", "encap",
                "segs", ",".join(segments),
                "dev", CONFIG["interface"], "mtu", str(CONFIG["seg6_mtu"])
            ]
        
            print(f"🛠️ 执行路由更新: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True)
        
            if result.returncode != 0:
                raise subprocess.CalledProcessError(
                    result.returncode, cmd,
                    output=result.stdout, stderr=result.stderr
                )
            
            print(f"✅ 路由更新成功: {dest_ip}")
            
            # 关键修改：在写入路由前判断是否为新路由
            is_new_route = dest_ip not in self.active_routes
            
            # 更新路由信息
            self.active_routes[dest_ip] = {
                "segments": segments,
                "next_hop": segments[0],
                "last_used": time.time(),
                "update_time": time.time()
            }

            if is_new_route:
                self._schedule_updater(dest_ip)
                
        except subprocess.CalledProcessError as e:
            print(f"❌ 命令执行失败: {e.stderr.strip()}")
        except Exception as e:
            print(f"❌ 路由安装异常: {str(e)}")

    def _schedule_updater(self, dest_ip: str):
        """路由更新调度（严格线程去重）"""
        with self.thread_lock:
            # 检查是否已有存活线程
            existing_thread = self.update_threads.get(dest_ip)
            if existing_thread and existing_thread.is_alive():
                print(f"⏩ 已有更新线程运行: {dest_ip}")
                return

        print(f"🕒 启动路由更新守护线程: {dest_ip}")
        
        def update_job():
            while True:
                # 检查路由是否仍然存在
                with self.lock:
                    if dest_ip not in self.active_routes:
                        break
                
                # 执行更新
                try:
                    time.sleep(CONFIG["update_interval"])
                    self._update_route(dest_ip)
                except Exception as e:
                    print(f"⚠️ 更新线程异常: {str(e)}")

            # 线程退出时清理
            with self.thread_lock:
                if dest_ip in self.update_threads:
                    del self.update_threads[dest_ip]
            print(f"⏹️ 更新线程退出: {dest_ip}")

        # 创建并记录线程
        thread = threading.Thread(target=update_job, daemon=True)
        thread.start()
        
        with self.thread_lock:
            self.update_threads[dest_ip] = thread

    def _send_route_to_visual(self, dest_ip: str, final_ip: str, segments: List[str], path_data: dict):
        """向可视化系统发送路由信息（完整版）
        发送完整的路径信息，包括中间节点和原始路径数据
        """
        # 检查是否配置了可视化系统API
        if "visual_api" not in CONFIG or not CONFIG["visual_api"]:
            return
            
        try:
            # 构建完整的数据，包含源节点、目标节点、中间节点和原始路径数据
            visual_data = {
                "source": str(self.self_ipv6),
                "destination": final_ip,
                "segments": segments,  # 包含中间节点列表
                "path_data": path_data,  # 包含原始路径数据
                "timestamp": time.time(),
                "node_info": {
                    "shell": self.node_info.shell,
                    "id": self.node_info.id
                }
            }
            
            # 发送数据到可视化系统
            try:
                resp = httpx.post(
                    CONFIG["visual_api"], 
                    json=visual_data,
                    timeout=3  # 短超时，避免影响主要功能
                )
                if resp.status_code == 200:
                    print(f"✅ 完整路由信息已发送到可视化系统: {dest_ip}")
                else:
                    print(f"⚠️ 可视化系统响应异常: {resp.status_code}")
            except Exception as e:
                print(f"⚠️ 发送路由信息到可视化系统失败: {str(e)}")
                
            # 打印路由信息，便于调试
            print(f"📊 路由详情: 源={self.self_ipv6}, 目标={final_ip}")
            print(f"📍 节点信息: shell={self.node_info.shell}, id={self.node_info.id}")
            print(f"🔄 中间节点数量: {len(segments)}")
        except Exception as e:
            print(f"⚠️ 准备路由可视化数据失败: {str(e)}")
            # 错误不影响主要功能
            
    def _update_route(self, dest_ip: str):
        """路由更新实现"""
        for _ in range(3):
            try:
                with self.lock:
                    if dest_ip not in self.active_routes:
                        return
                    
                    print(f"🔄 更新路由: {dest_ip}")
                    path_url = self._build_path_url(dest_ip)
                    resp = self.http.get(path_url, timeout=5)
                    resp.raise_for_status()
                    
                    # 获取原始路径数据
                    path_data = resp.json()
                    final_ip, new_segments = self._process_path(path_data)
                    
                    if new_segments != self.active_routes[dest_ip]["segments"]:
                        self._install_route(final_ip, new_segments)
                        # 路由变化时发送到可视化系统
                        self._send_route_to_visual(dest_ip, final_ip, new_segments, path_data)
                    else:
                        print("ℹ️ 路由无变化")
                    
                    self.active_routes[dest_ip]["update_time"] = time.time()
                break
            except Exception as e:
                print(f"⚠️ 路由更新失败: {str(e)}")
                time.sleep(1)

    def _cleanup_loop(self):
        """路由清理循环（增加线程清理）"""
        while True:
            time.sleep(CONFIG["route_ttl"] // 2)
            try:
                with self.lock:
                    # 清理过期路由
                    current_time = time.time()
                    expired = [
                        ip for ip, info in self.active_routes.items()
                        if current_time - info["last_used"] > CONFIG["route_ttl"]
                    ]
                    
                    for ip in expired:
                        self._remove_route(ip)
                        del self.active_routes[ip]

                # 清理无效线程记录
                with self.thread_lock:
                    active_routes = set(self.active_routes.keys())
                    dead_ips = [ip for ip in self.update_threads if ip not in active_routes]
                    for ip in dead_ips:
                        del self.update_threads[ip]
                        
            except Exception as e:
                print(f"⚠️ 清理异常: {str(e)}")

    def _remove_route(self, dest_ip: str):
        """路由删除实现"""
        try:
            subprocess.run(
                ["ip", "-6", "route", "del", dest_ip],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            print(f"🗑️ 路由删除成功: {dest_ip}")
        except subprocess.CalledProcessError as e:
            print(f"❌ 路由删除失败: {str(e)}")

    def _event_loop(self):
        """事件处理循环"""
        while True:
            try:
                self.bpf.perf_buffer_poll(timeout=100)
            except Exception as e:
                print(f"⚠️ 事件循环异常: {str(e)}")
                time.sleep(1)

    def handle_event(self, cpu, data, size):
        """事件处理回调（新增下一跳地址处理）"""
        try:
            event = self.bpf["route_events"].event(data)
            dest_ip = ipaddress.IPv6Address(bytes(event.daddr))
            dest_str = str(dest_ip)

            src_ip = ipaddress.IPv6Address(bytes(event.saddr))
            src_str = str(src_ip)
        
            # 过滤条件检查
            if dest_ip == self.self_ipv6:
                # print(f"🚫 过滤本机地址: {dest_str}")
                return
            if dest_ip == self.n_ipv6:
                # print(f"🚫 过滤相邻地址: {dest_str}")
                return
    
            if src_ip != self.self_ipv6:
                print(f"🚫 过滤非本机流量 源地址: {src_ip} -> 目标: {dest_ip}")
                return

            # print(f"🔍 捕获有效流量 -> 目标地址: {dest_str}")
        
            if dest_ip.is_private:
                with self.lock:
                    # 检查是否是已知路由的目标或下一跳
                    matched = False
                    for route_dest, info in self.active_routes.items():
                        if dest_str == route_dest or dest_str == info["next_hop"]:
                            info["last_used"] = time.time()
                            matched = True
                            # print(f"🔄 更新路由 {route_dest} 的last_used（下一跳: {info['next_hop']}）")
                            break
                    
                # 未匹配到现有路由时触发路由管理
                if not matched:
                    self._route_manager(dest_str)
        except Exception as e:
            print(f"⚠️ 事件处理异常: {str(e)}")

# --------------------------
# 主程序入口
# --------------------------
if __name__ == "__main__":
    # 命令行参数处理
    if len(sys.argv) > 1 and sys.argv[1] == "--help":
        print("SRv6动态路由管理器")
        print("用法: python srv6_route_manager.py [选项]")
        print("选项:")
        print("  --no-visual    禁用可视化系统集成")
        sys.exit(0)
        
    # 处理命令行参数
    if len(sys.argv) > 1 and sys.argv[1] == "--no-visual":
        print("ℹ️ 已禁用可视化系统集成")
        CONFIG["visual_api"] = ""
        
    try:
        router = SRv6DynamicRouter()
        print(f"ℹ️ 路由器已启动，可视化系统API: {CONFIG.get('visual_api', '未配置')}")
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("\n🛑 安全停止中...")
        if router:
            with router.lock:
                for ip in list(router.active_routes.keys()):
                    router._remove_route(ip)
        sys.exit(0)
    except Exception as e:
        print(f"💥 致命错误: {str(e)}")
        sys.exit(1)