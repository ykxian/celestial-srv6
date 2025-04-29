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

"""星座动画模型，负责更新卫星位置和处理路由请求"""

import typing
import requests
import json
from multiprocessing.connection import Connection as MultiprocessingConnection

import celestial.config
import celestial.types
import celestial.shell
from celestial.animation_constants import API_BASE_URL


class AnimationConstellation:
    """
    Animation constellation that advances shells and updates VTK animation
    """

    def __init__(
        self,
        config: celestial.config.Config,
        conn: MultiprocessingConnection,
    ):
        """
        Animation constellation initialization

        :param config: The configuration of the constellation.
        :param conn: The connection to the animation process.
        """
        self.conn = conn
        self.config = config

        self.current_time: celestial.types.timestamp_s = 0
        self.shells: typing.List[celestial.shell.Shell] = []

        for i, sc in enumerate(config.shells):
            s = celestial.shell.Shell(
                shell_identifier=i + 1,
                planes=sc.planes,
                sats=sc.sats,
                altitude_km=sc.altitude_km,
                inclination=sc.inclination,
                arc_of_ascending_nodes=sc.arc_of_ascending_nodes,
                eccentricity=sc.eccentricity,
                isl_bandwidth_kbits=sc.isl_bandwidth_kbits,
                bbox=config.bbox,
                ground_stations=config.ground_stations,
            )

            self.shells.append(s)

        for s in self.shells:
            s.step(self.current_time, calculate_diffs=False)

        self.conn.send(
            {
                "type": "init",
                "num_shells": len(self.shells),
                "total_sats": [s.total_sats for s in self.shells],
                "sat_positions": [s.get_sat_positions() for s in self.shells],
                "links": [s.get_links() for s in self.shells],
                "gst_positions": self.shells[0].get_gst_positions(),
                "gst_links": [s.get_gst_links() for s in self.shells],
                "gst_names": self.shells[0].gst_names,
            }
        )

    def step(self, t: celestial.types.timestamp_s) -> None:
        """
        Advance the constellation to the given time.

        :param t: The time to advance to.
        """
        self.current_time = t

        # 检查是否有来自Animation的控制消息
        if self.conn.poll():
            msg = self.conn.recv()
            if self.handle_control_message(msg):
                # 如果消息已处理，继续正常步进
                pass

        # 不再需要从serializer获取链路信息和更新路径矩阵
        # 现在使用HTTP API获取路由路径

        for s in self.shells:
            s.step(self.current_time)

        self.conn.send(
            {
                "type": "time",
                "time": self.current_time,
            }
        )

        for i in range(len(self.shells)):
            self.conn.send(
                {
                    "type": "shell",
                    "shell": i,
                    "sat_positions": self.shells[i].get_sat_positions(),
                    "links": self.shells[i].get_links(),
                    "gst_positions": self.shells[i].get_gst_positions(),
                    "gst_links": self.shells[i].get_gst_links(),
                }
            )

    def _setup_logger(self, name):
        """
        设置并返回一个日志记录器

        :param name: 日志记录器名称
        :return: 配置好的日志记录器
        """
        import logging
        # 避免重复配置日志系统
        if not logging.getLogger().handlers:
            logging.basicConfig(level=logging.DEBUG)
        return logging.getLogger(name)
        
    def _decode_response(self, content, logger):
        """
        解码HTTP响应内容
        
        :param content: 响应内容
        :param logger: 日志记录器
        :return: 解码后的字符串，失败返回None
        """
        try:
            # 尝试使用UTF-8解码
            return content.decode('utf-8')
        except UnicodeDecodeError:
            # 如果UTF-8解码失败，尝试使用latin-1
            logger.warning("UTF-8解码失败，尝试使用latin-1编码")
            try:
                return content.decode('latin-1')
            except Exception as e:
                logger.error(f"解码响应内容失败: {e}")
                return None

    def _get_node_info(self, node_index):
        """
        获取节点的shell和ID信息

        :param node_index: 节点全局索引
        :return: (shell, id) 元组
        """
        # 创建日志记录器用于调试
        logger = self._setup_logger("node_info")
        
        # 计算总卫星数
        total_sats = sum(s.total_sats for s in self.shells)
        logger.debug(f"计算节点信息: 全局索引={node_index}, 总卫星数={total_sats}")
        
        # 记录每个shell的卫星数量，用于调试
        shell_sizes = [s.total_sats for s in self.shells]
        logger.debug(f"各shell卫星数量: {shell_sizes}")
        
        if node_index < total_sats:  # 卫星
            # 计算累积卫星数，用于确定节点所在的shell
            accumulated_sats = 0
            for i, shell in enumerate(self.shells):
                shell_size = shell.total_sats
                logger.debug(f"检查shell {i+1}: 累积卫星数={accumulated_sats}, shell大小={shell_size}")
                
                # 如果节点索引小于当前累积卫星数加上当前shell的卫星数，则节点在当前shell中
                if node_index < accumulated_sats + shell_size:
                    # 计算节点在当前shell中的索引
                    shell_id = i + 1  # shell_identifier从1开始
                    node_id_in_shell = node_index - accumulated_sats
                    logger.debug(f"找到匹配: shell={shell_id}, id={node_id_in_shell}")
                    return shell_id, node_id_in_shell
                
                accumulated_sats += shell_size
            
            # 如果循环结束仍未找到，返回默认值
            logger.warning(f"未找到匹配的shell，使用默认值: shell=1, id={node_index}")
            return 1, node_index  # 默认为shell 1
        else:  # 地面站
            node_shell = 0  # 地面站的shell为0
            node_id = node_index - total_sats
            logger.debug(f"地面站节点: shell={node_shell}, id={node_id}")
            return node_shell, node_id

    def _create_fallback_response(self, source, target):
        """
        创建一个简单的直接连接响应

        :param source: 源节点索引
        :param target: 目标节点索引
        :return: 包含直接路径的响应字典
        """
        return {
            "type": "route",
            "source": int(source),
            "target": int(target),
            "path": [int(source), int(target)]
        }

    def get_route_path(self, source_index: int, target_index: int) -> typing.List[int]:
        """
        获取从source_index到target_index的路由路径，使用HTTP API获取路径信息

        :param source_index: 源节点全局索引
        :param target_index: 目标节点全局索引
        :return: 节点索引列表，表示从源到目标的路径
        """
        logger = self._setup_logger("route_path")
        logger.debug(f"计算从 {source_index} 到 {target_index} 的路径")
        
        # 创建默认的直接连接路径
        default_path = [int(source_index), int(target_index)]
        
        # 特殊处理：如果是源节点和目标节点相同
        if source_index == target_index:
            logger.info(f"源节点和目标节点相同: {source_index}，返回单节点路径")
            return [source_index]

        try:
            # 获取总卫星数
            total_sats = sum(s.total_sats for s in self.shells)

            # 获取源节点和目标节点的shell和ID
            source_shell, source_id = self._get_node_info(source_index)
            target_shell, target_id = self._get_node_info(target_index)

            logger.info(f"源节点: shell={source_shell}, id={source_id}")
            logger.info(f"目标节点: shell={target_shell}, id={target_id}")

            # 构建API URL
            url = f"{API_BASE_URL}/path/{source_shell}/{source_id}/{target_shell}/{target_id}"
            logger.info(f"请求路径API: {url}")

            # 发送HTTP请求
            try:
                response = requests.get(url, timeout=5)
                
                if response.status_code != 200:
                    logger.error(f"HTTP请求失败: 状态码 {response.status_code}")
                    return default_path

                # 获取响应内容并解码
                content_str = self._decode_response(response.content, logger)
                if not content_str:
                    return default_path
                
                # 解析JSON响应
                try:
                    path_data = json.loads(content_str)
                    logger.debug(f"API响应: {path_data}")
                except json.JSONDecodeError as json_err:
                    logger.error(f"JSON解析错误: {json_err}, 内容: {content_str[:100]}...")
                    return default_path
                

                # 提取路径段信息
                if "segments" not in path_data:
                    logger.warning("API响应中没有segments字段")
                    return default_path
                
                # 检查是否路径被阻塞
                if "blocked" in path_data and path_data["blocked"] == True:
                    logger.warning(f"路径被阻塞: {source_shell}/{source_id} -> {target_shell}/{target_id}")
                    return default_path
                
                # 检查segments是否为None
                if path_data["segments"] is None:
                    logger.warning(f"路径段为空(None): {source_shell}/{source_id} -> {target_shell}/{target_id}")
                    return default_path
                    
                # 处理路径段
                path = [source_index]  # 初始化路径，从源节点开始
                
                # 确保segments是可迭代的
                segments = path_data["segments"] if isinstance(path_data["segments"], list) else []
                
                for segment in segments:
                    if "source" in segment and "target" in segment:
                        # 获取目标节点信息
                        target_info = segment["target"]
                        segment_target_shell = target_info.get("shell", 0)
                        segment_target_id = target_info.get("id", 0)
                        
                        # 计算全局索引
                        if segment_target_shell > 0:  # 卫星
                            # 计算卫星的全局索引
                            global_target = segment_target_id
                            for s in range(segment_target_shell - 1):
                                global_target += self.shells[s].total_sats
                            path.append(global_target)
                        else:  # 地面站
                            path.append(total_sats + segment_target_id)
                
                # 确保路径至少包含源和目标
                if len(path) < 2:
                    logger.warning(f"路径节点数量不足，添加目标节点: {target_index}")
                    path.append(target_index)
                # 确保路径以目标结束
                elif path[-1] != target_index:
                    logger.warning(f"路径末尾不是目标节点，添加目标节点: {target_index}")
                    path.append(target_index)
                
                # 确保所有路径节点都是整数
                try:
                    path = [int(node) for node in path]
                except (ValueError, TypeError) as e:
                    logger.error(f"路径节点转换为整数失败: {e}")
                    return default_path
                
                logger.info(f"从API获取的路径: {path}")
                return path
                    
            except requests.RequestException as e:
                logger.error(f"HTTP请求异常: {e}")
            except Exception as e:
                logger.error(f"处理路径数据时出错: {e}")

        except Exception as e:
            logger.error(f"路由计算出错: {e}")
            
        return default_path  # 所有异常情况下返回默认路径

    def _send_route_response(self, response, source, target, logger):
        """
        发送路由响应
        
        :param response: 响应数据
        :param source: 源节点
        :param target: 目标节点
        :param logger: 日志记录器
        :return: 是否成功发送
        """
        # 确保数据可以被序列化
        try:
            response_copy = response.copy()
        except Exception as error:
            logger.error(f"响应无法复制: {error}")
            # 回退到最简单的响应
            response = self._create_fallback_response(source, target)

        try:
            self.conn.send(response)
            return True
        except Exception as send_error:
            logger.error(f"发送路由响应时出错: {send_error}")
            # 尝试发送最简化版本的响应
            try:
                self.conn.send(self._create_fallback_response(source, target))
                return True
            except Exception as retry_error:
                logger.error(f"发送简化路由响应时出错: {retry_error}")
                return False
                
    def handle_control_message(self, msg):
        """
        处理来自Animation的控制消息

        :param msg: 控制消息
        :return: 是否已处理消息
        """
        logger = self._setup_logger("control_message")
        
        # 基本消息验证
        if not isinstance(msg, dict):
            logger.warning(f"接收到非字典消息: {type(msg)}")
            return False

        if "type" not in msg:
            logger.warning(f"消息缺少类型字段: {msg}")
            return False

        msg_type = msg["type"]

        try:
            # 处理路由请求
            if msg_type == "get_route":
                if "source" not in msg or "target" not in msg:
                    logger.error("路由请求缺少源或目标")
                    return False

                try:
                    source = int(msg["source"])
                    target = int(msg["target"])
                except (ValueError, TypeError) as e:
                    logger.error(f"路由请求参数类型错误: {e}")
                    return False

                logger.debug(f"接收到路由请求: 源={source}, 目标={target}")

                # 计算路由路径
                path_nodes = self.get_route_path(source, target)

                # 确保路径至少包含源和目标
                if len(path_nodes) < 2:
                    logger.warning(f"路径节点数量不足，使用直接连接: {source} -> {target}")
                    path_nodes = [source, target]

                # 确保所有路径节点都是整数
                try:
                    path_nodes = [int(node) for node in path_nodes]
                except (ValueError, TypeError) as e:
                    logger.error(f"路径节点转换为整数失败: {e}")
                    path_nodes = [int(source), int(target)]

                # 打印路径详细信息以进行调试
                total_sats = sum(s.total_sats for s in self.shells)
                source_type = "地面站" if source >= total_sats else "卫星"
                target_type = "地面站" if target >= total_sats else "卫星"
                logger.debug(f"路由路径: {source_type} {source} 到 {target_type} {target}")
                logger.debug(f"路径节点: {path_nodes}")

                # 发送路由响应到动画进程
                response = {
                    "type": "route",
                    "source": int(source),
                    "target": int(target),
                    "path": path_nodes
                }

                # 尝试发送响应
                return self._send_route_response(response, source, target, logger)

            # 可以在这里添加其他消息类型的处理

        except Exception as e:
            logger.error(f"处理控制消息时出错: {e}")

        return False
