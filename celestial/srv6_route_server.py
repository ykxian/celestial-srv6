#
# This file is part of Celestial (https://github.com/OpenFogStack/celestial).
# Copyright (c) 2024 Ben S. Kempton, Tobias Pfandzelter, The OpenFogStack Team.
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

"""SRv6路由可视化服务器，接收路由管理器发送的路由信息并转发给动画系统"""

import threading
import logging
import json
import time
import ipaddress
from typing import Dict, List, Optional, Any
from http.server import HTTPServer, BaseHTTPRequestHandler
from multiprocessing.connection import Connection as MultiprocessingConnection

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("SRv6RouteServer")

class SRv6RouteData:
    """SRv6路由数据结构"""
    def __init__(self, data: Dict[str, Any]):
        self.source_ip = data.get("source", "")
        self.destination_ip = data.get("destination", "")
        self.segments = data.get("segments", [])  # 可能为空，表示简化的路由数据
        self.timestamp = data.get("timestamp", time.time())
        self.path_data = data.get("path_data", {})
        self.node_info = data.get("node_info", {})
        
    def get_source_node_info(self) -> tuple:
        """获取源节点的shell和id信息"""
        if self.node_info and "shell" in self.node_info and "id" in self.node_info:
            return self.node_info["shell"], self.node_info["id"]
        return self._parse_ipv6_to_node_info(self.source_ip)
    
    def get_destination_node_info(self) -> tuple:
        """获取目标节点的shell和id信息"""
        return self._parse_ipv6_to_node_info(self.destination_ip)
    
    def get_segment_node_infos(self) -> List[tuple]:
        """获取所有中间节点的shell和id信息
        如果没有segments（简化的路由数据），则返回空列表
        """
        if not self.segments:
            # 处理简化的路由数据情况，返回空列表
            return []
        return [self._parse_ipv6_to_node_info(segment) for segment in self.segments]
    
    def _parse_ipv6_to_node_info(self, ipv6_str: str) -> tuple:
        """将IPv6地址解析为节点信息(shell, id)"""
        try:
            # 确保是有效的IPv6地址
            ipv6 = ipaddress.IPv6Address(ipv6_str)
            
            # 只处理fd00::/16地址
            if not str(ipv6).startswith("fd00:"):
                return 0, 0
                
            # 解析地址格式: fd00::a:b:c:d
            parts = str(ipv6).split(":")[-4:]
            if len(parts) < 4:
                return 0, 0
                
            # 提取关键字段并转换为整数
            try:
                b = int(parts[1], 16) if parts[1] else 0
                c = int(parts[2], 16) if parts[2] else 0
                d = int(parts[3], 16) if parts[3] else 0
                
                # 计算节点ID
                node_id = (c << 6) | ((d - 2) >> 2)
                return b, node_id
            except (ValueError, IndexError):
                return 0, 0
        except Exception as e:
            logger.error(f"解析IPv6地址出错: {e}")
            return 0, 0

class SRv6RouteHandler(BaseHTTPRequestHandler):
    """处理SRv6路由请求的HTTP处理器"""
    
    # 类变量，存储最近的路由数据
    recent_routes: Dict[str, SRv6RouteData] = {}
    
    def get_animation_conn(self):
        """获取动画连接，直接从SRv6RouteServer获取"""
        # 直接从服务器类变量获取，简化连接对象管理
        if hasattr(SRv6RouteServer, 'animation_conn_instance') and SRv6RouteServer.animation_conn_instance is not None:
            # 确保返回的是visualized_celestial.py中创建的parent_conn
            return SRv6RouteServer.animation_conn_instance
        # 没有可用连接则返回None
        logger.warning("没有可用的animation_conn连接")
        return None
    
    def do_GET(self):
        """处理GET请求"""
        if self.path == "/api/status":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            status = {
                "status": "running",
                "routes_count": len(self.recent_routes),
                "timestamp": time.time()
            }
            self.wfile.write(json.dumps(status).encode())
        else:
            self.send_response(404)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Not Found")
    
    def do_POST(self):
        """处理POST请求，接收路由信息"""
        if self.path == "/api/route":
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            
            try:
                route_data = json.loads(post_data.decode('utf-8'))
                logger.info(f"接收到路由数据: {route_data['source']} -> {route_data['destination']}")
                
                # 解析路由数据
                srv6_route = SRv6RouteData(route_data)
                
                # 存储路由数据
                route_key = f"{srv6_route.source_ip}->{srv6_route.destination_ip}"
                self.recent_routes[route_key] = srv6_route
                
                # 获取动画连接，使用新的get_animation_conn方法
                animation_conn = self.get_animation_conn()
                
                # 如果有动画连接，发送路由数据
                if animation_conn:
                    try:
                        # 获取源节点和目标节点信息
                        source_shell, source_id = srv6_route.get_source_node_info()
                        target_shell, target_id = srv6_route.get_destination_node_info()
                        
                        # 获取中间节点信息
                        segment_nodes = srv6_route.get_segment_node_infos()
                        
                        # 构建路由消息
                        route_msg = {
                            "type": "srv6_route",
                            "source": {
                                "shell": source_shell,
                                "id": source_id
                            },
                            "target": {
                                "shell": target_shell,
                                "id": target_id
                            },
                            "segments": [
                                {"shell": shell, "id": node_id} 
                                for shell, node_id in segment_nodes
                            ],
                            "timestamp": srv6_route.timestamp
                        }
                        
                        # 发送到动画进程前记录详细信息
                        logger.info(f"准备发送路由数据到动画进程，详细信息: {json.dumps(route_msg)}")
                        try:
                            
                            # 直接使用获取到的连接对象发送消息
                            animation_conn.send(route_msg)
                            
                            logger.info(f"已成功发送路由数据到动画进程: {source_shell}/{source_id} -> {target_shell}/{target_id}")
                            # 发送后等待一小段时间，确保消息被处理
                            time.sleep(0.1)
                        except Exception as e:
                            logger.error(f"发送路由数据到动画进程失败: {e}")
                            import traceback
                            logger.error(traceback.format_exc())
                    except Exception as e:
                        logger.error(f"发送路由数据到动画进程时出错: {e}")
                else:
                    logger.warning("没有动画连接，无法发送路由数据到动画进程")
                
                # 返回成功响应
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                response = {"status": "success", "message": "Route data received"}
                self.wfile.write(json.dumps(response).encode())
            except json.JSONDecodeError as e:
                logger.error(f"解析JSON数据出错: {e}")
                self.send_response(400)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                error = {"status": "error", "message": "Invalid JSON data"}
                self.wfile.write(json.dumps(error).encode())
            except Exception as e:
                logger.error(f"处理路由数据时出错: {e}")
                self.send_response(500)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                error = {"status": "error", "message": str(e)}
                self.wfile.write(json.dumps(error).encode())
        else:
            self.send_response(404)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Not Found")

class SRv6RouteServer:
    """SRv6路由服务器，接收路由管理器发送的路由信息"""
    
    # 添加类变量存储animation_conn，确保所有处理器实例都能访问
    animation_conn_instance = None
    
    def __init__(self, host="0.0.0.0", port=8080, animation_conn=None):
        """初始化服务器
        
        :param host: 服务器主机地址
        :param port: 服务器端口
        :param animation_conn: 与动画进程的连接
        """
        self.host = host
        self.port = port
        self.server = None
        self.server_thread = None
        self.running = False
        
        if animation_conn is None:
            logger.warning("警告: 动画连接为None，路由数据将不会发送到动画系统")
        
        # 确保animation_conn是有效的连接对象
        if animation_conn is not None and hasattr(animation_conn, 'send'):
            # 直接使用传入的animation_conn作为类变量
            # 这是visualied_celestial.py中创建的parent_conn
            SRv6RouteServer.animation_conn_instance = animation_conn
                        
            # 测试连接
            try:
                logger.info("开始测试连接...")
                
                # 第一次测试消息
                test_msg = {"type": "srv6_route_test", "message": "测试SRv6路由服务器连接", "timestamp": time.time()}
                logger.info(f"发送第一次测试消息: {test_msg}")
                animation_conn.send(test_msg)
                logger.info("成功发送第一次测试消息到动画进程")
                
                # 等待响应处理
                time.sleep(0.5)  # 等待时间
                
                # 第二次测试消息
                test_msg = {"type": "srv6_route_test", "message": "测试SRv6路由服务器连接 - 确认", "timestamp": time.time()}
                logger.info(f"发送第二次测试消息: {test_msg}")
                animation_conn.send(test_msg)
                logger.info("成功发送第二次测试消息到动画进程")
                
                # 再次等待响应处理
                time.sleep(0.5)  # 等待时间
                
            except Exception as e:
                logger.error(f"测试发送消息到动画进程失败: {e}")
                import traceback
                logger.error(traceback.format_exc())
        else:
            logger.error(f"提供的animation_conn对象无效，类型: {type(animation_conn)}")
            SRv6RouteServer.animation_conn_instance = None
    
    def start(self):
        """启动服务器"""
        if self.running:
            logger.warning("服务器已经在运行")
            return
        
        try:
            self.server = HTTPServer((self.host, self.port), SRv6RouteHandler)
            self.server_thread = threading.Thread(target=self.server.serve_forever)
            self.server_thread.daemon = True
            self.server_thread.start()
            self.running = True
            logger.info(f"SRv6路由服务器已启动: http://{self.host}:{self.port}")
        except Exception as e:
            logger.error(f"启动服务器时出错: {e}")
    
    def stop(self):
        """停止服务器"""
        if not self.running:
            logger.warning("服务器未运行")
            return
        
        try:
            # 清除animation_conn_instance引用
            SRv6RouteServer.animation_conn_instance = None
            
            # 关闭HTTP服务器
            self.server.shutdown()
            self.server.server_close()
            self.running = False
            logger.info("SRv6路由服务器已停止")
        except Exception as e:
            logger.error(f"停止服务器时出错: {e}")
            import traceback
            logger.error(traceback.format_exc())

    # 不再需要消息转发方法，直接使用visualized_celestial.py中创建的parent_conn

# 测试代码
if __name__ == "__main__":
    server = SRv6RouteServer(port=8080)
    server.start()
    
    try:
        # 保持主线程运行
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.stop()
        print("服务器已停止")