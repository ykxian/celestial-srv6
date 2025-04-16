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

"""Animation of the constellation"""

import vtk
import threading as td
import seaborn as sns
import numpy as np
from multiprocessing.connection import Connection as MultiprocessingConnection
import types
import typing
import time
import subprocess
import os
import math
import requests
import json
import pickle as _pickle

import celestial.config
import celestial.types
import celestial.shell

EARTH_RADIUS_M = 6371000  # radius of Earth in meters

# API相关常量
API_BASE_URL = "http://127.0.0.1"  # API基础URL

LANDMASS_OUTLINE_COLOR = (0.0, 0.0, 0.0)  # black, best contrast
EARTH_LAND_OPACITY = 1.0

EARTH_BASE_COLOR = (0.9, 0.9, 1.0)  # light blue, like water!
EARTH_OPACITY = 1.0

BACKGROUND_COLOR = (1.0, 1.0, 1.0)  # white

# SAT_COLOR = (1.0, 0.0, 0.0)  # red, color of satellites
SAT_OPACITY = 1.0
SAT_INACTIVE_OPACITY = 0.5

GST_COLOR = (0.0, 1.0, 0.0)  # green, color of groundstations
GST_OPACITY = 10.0

ISL_LINK_COLOR = (0.9, 0.5, 0.1)  # yellow-brown, satellite-satellite links
ISL_LINK_OPACITY = 1.0
ISL_LINE_WIDTH = 1  # how wide to draw line in pixels

GST_LINK_COLOR = (0.5, 0.9, 0.5)  # greenish? satellite-groundstation links
GST_LINK_OPACITY = 0.75
GST_LINE_WIDTH = 2  # how wide to draw line in pixels

PATH_LINK_COLOR = (0.8, 0.2, 0.8)  # purpleish? path links
PATH_LINK_OPACITY = 0.7
PATH_LINE_WIDTH = 13  # how wide to draw line in pixels

EARTH_SPHERE_POINTS = 5000  # higher = smoother earth model, slower to generate

SAT_POINT_SIZE = 8  # how big satellites are in (probably) screen pixels
GST_POINT_SIZE = 8  # how big ground points are in (probably) screen pixels

SECONDS_PER_DAY = 86400  # number of seconds per earth rotation (day)

# 文本显示相关常量
TEXT_COLOR = (0.0, 0.0, 0.0)  # Black text, better visibility
TEXT_SIZE = 16  # Text size
TEXT_OPACITY = 1.0  # Text opacity
TEXT_POSITION_X = 10  # Text X position on screen
TEXT_POSITION_Y = 10  # Text Y position on screen (top left corner)
TEXT_LINE_SPACING = 25  # Text line spacing
PROGRESS_BAR_WIDTH = 200  # Progress bar width
PROGRESS_BAR_HEIGHT = 15  # Progress bar height

# 点击信息面板相关常量
INFO_PANEL_BG_COLOR = (0.9, 0.9, 0.9)  # 浅灰色背景
INFO_PANEL_OPACITY = 0.9  # 面板透明度
INFO_PANEL_TEXT_COLOR = (0.0, 0.0, 0.0)  # 黑色文本
INFO_PANEL_TEXT_SIZE = 14  # 文本大小
INFO_PANEL_PADDING = 10  # 内边距
INFO_PANEL_WIDTH = 300  # 面板宽度
INFO_PANEL_LINE_HEIGHT = 20  # 行高
INFO_PANEL_CLOSE_BTN_SIZE = 20  # 关闭按钮大小
INFO_PANEL_CLOSE_BTN_COLOR = (0.7, 0.0, 0.0)  # 关闭按钮颜色（红色）

# 路由路径显示相关常量
ROUTE_PATH_COLOR = (1.0, 0.0, 0.0)  # 红色路径
ROUTE_PATH_OPACITY = 1.0  # 路径透明度
ROUTE_PATH_WIDTH = 4  # 路径线宽
ROUTE_PATH_ARROW_SIZE = 12  # 箭头大小

# 路由更新相关常量
ROUTE_MIN_UPDATE_INTERVAL = 2.0  # 路由最小更新间隔（秒）
ROUTE_RESET_DURATION = 3.0  # 路由重置状态持续时间（秒）

# SSH按钮相关常量
INFO_PANEL_SSH_BTN_WIDTH = 80  # SSH按钮宽度
INFO_PANEL_SSH_BTN_HEIGHT = 25  # SSH按钮高度
INFO_PANEL_SSH_BTN_COLOR = (0.2, 0.6, 0.8)  # SSH按钮颜色（蓝色）
INFO_PANEL_SSH_BTN_TEXT_COLOR = (1.0, 1.0, 1.0)  # SSH按钮文本颜色（白色）
SSH_KEY_PATH = "~/id_ed25519"  # SSH密钥路径


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

    def get_route_path(self, source_index: int, target_index: int) -> typing.List[int]:
        """
        获取从source_index到target_index的路由路径，使用HTTP API获取路径信息

        :param source_index: 源节点全局索引
        :param target_index: 目标节点全局索引
        :return: 节点索引列表，表示从源到目标的路径
        """
        import logging
        # 将日志级别设置为DEBUG，减少INFO级别的输出
        logging.basicConfig(level=logging.DEBUG)
        logger = logging.getLogger("route_path")
        logger.debug(f"计算从 {source_index} 到 {target_index} 的路径")

        try:
            # 特殊处理：如果是源节点和目标节点相同
            if source_index == target_index:
                logger.info(f"源节点和目标节点相同: {source_index}，返回单节点路径")
                return [source_index]

            # 确定源节点和目标节点类型（卫星还是地面站）
            total_sats = sum(s.total_sats for s in self.shells)

            # 确定源节点的shell和ID
            if source_index < total_sats:  # 卫星
                source_shell = 0
                source_id = source_index
                for i, shell in enumerate(self.shells):
                    if source_id >= shell.total_sats:
                        source_id -= shell.total_sats
                    else:
                        source_shell = i + 1  # shell_identifier从1开始
                        break
            else:  # 地面站
                source_shell = 0  # 地面站的shell为0
                source_id = source_index - total_sats

            # 确定目标节点的shell和ID
            if target_index < total_sats:  # 卫星
                target_shell = 0
                target_id = target_index
                for i, shell in enumerate(self.shells):
                    if target_id >= shell.total_sats:
                        target_id -= shell.total_sats
                    else:
                        target_shell = i + 1  # shell_identifier从1开始
                        break
            else:  # 地面站
                target_shell = 0  # 地面站的shell为0
                target_id = target_index - total_sats

            logger.info(f"源节点: shell={source_shell}, id={source_id}")
            logger.info(f"目标节点: shell={target_shell}, id={target_id}")

            # 构建API URL
            url = f"{API_BASE_URL}/path/{source_shell}/{source_id}/{target_shell}/{target_id}"
            logger.info(f"请求路径API: {url}")

            try:
                # 发送HTTP请求
                response = requests.get(url, timeout=5)

                # 检查响应状态码
                if response.status_code != 200:
                    logger.error(f"HTTP请求失败: 状态码 {response.status_code}")
                    return [source_index, target_index]  # 失败时使用直接连接

                # 获取响应内容并检查编码
                content = response.content
                try:
                    # 尝试使用UTF-8解码
                    content_str = content.decode('utf-8')
                except UnicodeDecodeError:
                    # 如果UTF-8解码失败，尝试使用latin-1（这个编码可以处理任何字节序列）
                    logger.warning("UTF-8解码失败，尝试使用latin-1编码")
                    content_str = content.decode('latin-1')
                
                # 解析JSON响应
                try:
                    path_data = json.loads(content_str)
                    logger.debug(f"API响应: {path_data}")
                except json.JSONDecodeError as json_err:
                    logger.error(f"JSON解析错误: {json_err}, 内容: {content_str[:100]}...")
                    return [source_index, target_index]  # 解析错误时使用直接连接

                # 提取路径段信息
                if "segments" in path_data:
                    segments = path_data["segments"]
                    
                    # 初始化路径，从源节点开始
                    path = [source_index]
                    
                    # 处理每个路径段，提取节点信息
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
                        path.append(target_index)
                    # 确保路径以目标结束
                    elif path[-1] != target_index:
                        path.append(target_index)
                    
                    logger.info(f"从API获取的路径: {path}")
                    return path
                else:
                    logger.warning("API响应中没有segments字段")
                    return [source_index, target_index]  # 使用直接连接
                    
            except requests.RequestException as e:
                logger.error(f"HTTP请求异常: {e}")
                return [source_index, target_index]  # 异常时使用直接连接
            except json.JSONDecodeError as e:
                logger.error(f"JSON解析错误: {e}")
                return [source_index, target_index]  # 解析错误时使用直接连接
            except Exception as e:
                logger.error(f"处理路径数据时出错: {e}")
                import traceback
                traceback.print_exc()
                return [source_index, target_index]  # 其他错误时使用直接连接

        except Exception as e:
            logger.error(f"路由计算出错: {e}")
            import traceback
            traceback.print_exc()
            return [source_index, target_index]

    def handle_control_message(self, msg):
        """
        处理来自Animation的控制消息

        :param msg: 控制消息
        :return: 是否已处理消息
        """
        import logging
        # 将日志级别设置为DEBUG，减少INFO级别的输出
        logging.basicConfig(level=logging.DEBUG)
        logger = logging.getLogger("control_message")
        
        try:
            if not isinstance(msg, dict):
                logger.warning(f"接收到非字典消息: {type(msg)}")
                return False

            if "type" not in msg:
                logger.warning(f"消息缺少类型字段: {msg}")
                return False

            msg_type = msg["type"]

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

                # 使用pickle序列化测试，确保数据可以被序列化
                try:
                    import pickle
                    pickle.dumps(response)
                except Exception as pickle_error:
                    logger.error(f"响应无法序列化: {pickle_error}")
                    # 回退到最简单的响应
                    response = {
                        "type": "route",
                        "source": int(source),
                        "target": int(target),
                        "path": [int(source), int(target)]
                    }

                try:
                    self.conn.send(response)
                    return True
                except Exception as send_error:
                    logger.error(f"发送路由响应时出错: {send_error}")
                    # 尝试发送最简化版本的响应
                    try:
                        # 创建一个最简单的响应，只包含基本数据类型
                        simple_response = {
                            "type": "route",
                            "source": int(source),
                            "target": int(target),
                            "path": [int(source), int(target)]
                        }
                        self.conn.send(simple_response)
                        return True
                    except Exception as retry_error:
                        logger.error(f"发送简化路由响应时出错: {retry_error}")
                        return False

            # 可以在这里添加其他消息类型的处理

        except Exception as e:
            logger.error(f"处理控制消息时出错: {e}")
            import traceback
            traceback.print_exc()

        return False

class Animation:
    """
    VTK animation of the constellation
    """

    def __init__(
        self,
        animation_conn: MultiprocessingConnection,
        draw_links: bool = True,
        frequency: int = 7,
    ):
        """
        Initialize the animation

        Like me, you might wonder what the numerous vkt calls are for.
        Answer: you need to manually configure a render pipeline for
        each object (vtk actor) in the scene.
        A typical VTK render pipeline:

        point data array   <-- set/update position data
            |
        poly data array
            |
        poly data mapper
            |
        object actor   <-- edit color/size/opacity, apply rotations/translations
            |
        vtk renderer
            |
        vkt render window
            |
        vkt render interactor   <-- trigger events, animate
            |
        Your computer screen

        :param animation_conn: The connection to the animation process.
        :param draw_links: Whether to draw links in the animation.
        :param frequency: The frequency of the animation.
        """
        self.initialized = False
        self.conn = animation_conn
        init = self.conn.recv()
        if init["type"] != "init":
            raise ValueError("Animation: did not receive init message first!")

        num_shells: int = init["num_shells"]
        total_sats: typing.List[int] = init["total_sats"]
        sat_positions: typing.List[
            typing.List[typing.Dict[str, typing.Union[float, bool]]]
        ] = init["sat_positions"]
        links: typing.List[
            typing.List[typing.Dict[str, typing.Union[float, int, bool]]]
        ] = init["links"]

        # print(f"Animation: initializing with links {links}")

        gst_positions: typing.List[typing.Dict[str, float]] = init["gst_positions"]
        gst_links: typing.List[
            typing.List[typing.Dict[str, typing.Union[float, int, bool]]]
        ] = init["gst_links"]
        
        # 初始化路由相关标志
        self.route_reset = False
        self.route_request_pending = False


        if "gst_names" in init:
            self.gst_names = init["gst_names"]
            print(f"Animation: received {len(self.gst_names)} ground station names: {self.gst_names}")
        else:
            self.gst_names = []
            print("Animation: no ground station names received")

        self.num_shells = num_shells

        # print(f"Animation: initializing with {num_shells} shells")

        self.shell_sats = total_sats
        self.sat_positions = sat_positions
        self.links = links

        self.gst_positions = gst_positions
        self.gst_links = gst_links

        self.current_simulation_time = 0
        self.last_animate = 0
        self.frequency = frequency
        self.frameCount = 0
        self.last_route_update = 0  # 初始化路由更新时间戳

        # 全局信息显示相关属性
        self.simulation_duration = 0  # 仿真总时长，将从消息中获取
        self.simulation_offset = 0    # 仿真时间偏移，将从消息中获取
        self.active_satellites = 0    # 活跃卫星数
        self.total_links_count = 0    # 总链路数
        self.text_actors = []         # 存储文本演员对象
        self.progress_bar_actor = None  # 进度条演员对象
        self.progress_bg_actor = None   # 进度条背景演员对象

        # 点击交互相关属性
        self.info_panel_actor = None     # 信息面板演员对象
        self.info_panel_text_actors = [] # 信息面板文本演员对象
        self.info_panel_close_btn = None # 信息面板关闭按钮
        self.selected_object = None      # 当前选中的对象（卫星或地面站）
        self.selected_shell = -1          # 当前选中的卫星所属的壳层
        self.selected_id = -1            # 当前选中的卫星或地面站ID

        # 路由路径显示相关属性
        self.route_source_type = None    # 路由起点对象类型
        self.route_source_shell = None   # 路由起点卫星所属壳层
        self.route_source_id = None      # 路由起点ID
        self.route_target_type = None    # 路由终点对象类型
        self.route_target_shell = None   # 路由终点卫星所属壳层
        self.route_target_id = None      # 路由终点ID
        self.route_path_actor = None     # 路由路径演员对象
        self.route_arrows_actor = None   # 路由路径箭头演员对象
        self.route_arrows_actors = []    # 路由路径箭头演员对象列表
        self.current_path_nodes = None   # 当前路径节点
        self.last_route_update = 0       # 上次路由更新的时间
        self.route_request_pending = False  # 路由请求挂起标志
        self.route_request_time = 0      # 路由请求发送时间，用于超时检测

        self.initialized = True  # 初始化完成标志

        self.makeEarthActor(EARTH_RADIUS_M)

        self.shell_actors = []
        self.shell_inactive_actors = []

        self.isl_actors = []

        for i in range(self.num_shells):
            self.shell_actors.append(types.SimpleNamespace())
            self.shell_inactive_actors.append(types.SimpleNamespace())
            self.isl_actors.append(types.SimpleNamespace())

        self.sat_colors = sns.color_palette(n_colors=self.num_shells)
        self.isl_colors = sns.color_palette(n_colors=self.num_shells, desat=0.5)

        self.draw_links = draw_links

        for shell in range(self.num_shells):
            self.makeSatsActor(shell, self.shell_sats[shell])
            self.makeInactiveSatsActor(shell, self.shell_sats[shell])
            if self.draw_links:
                self.makeLinkActors(shell, self.shell_sats[shell])

        self.gst_num = len(self.gst_positions)
        self.gst_actor = types.SimpleNamespace()
        self.gst_link_actor = types.SimpleNamespace()

        self.lock = td.Lock()

        # print(f"Animation: initializing with {self.gst_num} ground stations")

        self.makeGstActor(self.gst_num)
        if self.draw_links:
            self.makeGstLinkActors(self.gst_num)

        self.controlThread = td.Thread(target=self.controlThreadHandler)
        self.controlThread.start()

        self.makeRenderWindow()

    ###############################################################################
    #                           ANIMATION FUNCTIONS                               #
    ###############################################################################

    """

    """

    def _updateAnimation(self, obj: typing.Any, event: typing.Any) -> None:
        """
        This function is a wrapper to call the updateAnimation function with a lock.

        :param obj: The object that generated the event, probably vtk render window.
        :param event: The event that triggered this function.
        """
        with self.lock:
            self.updateAnimation(obj, event)

    def updateAnimation(self, obj: typing.Any, event: typing.Any) -> None:
        """
        This function takes in new position data and updates the render window

        :param obj: The object that generated the event, probably vtk render window.
        :param event: The event that triggered this function.
        """

        # rotate earth and land
        steps_to_animate = self.current_simulation_time - self.last_animate
        self.last_animate = self.current_simulation_time

        rotation_per_time_step = 360.0 / (SECONDS_PER_DAY) * steps_to_animate
        self.earthActor.RotateZ(rotation_per_time_step)
        self.sphereActor.RotateZ(rotation_per_time_step)

        # update sat points
        for s in range(self.num_shells):
            for i in range(self.shell_sats[s]):
                x = float(self.sat_positions[s][i]["x"])
                y = float(self.sat_positions[s][i]["y"])
                z = float(self.sat_positions[s][i]["z"])

                if self.sat_positions[s][i]["in_bbox"]:
                    self.shell_actors[s].satVtkPts.SetPoint(
                        self.shell_actors[s].satPointIDs[i], x, y, z
                    )
                    self.shell_inactive_actors[s].satVtkPts.SetPoint(
                        self.shell_actors[s].satPointIDs[i], 0, 0, 0
                    )
                else:
                    self.shell_actors[s].satVtkPts.SetPoint(
                        self.shell_actors[s].satPointIDs[i], 0, 0, 0
                    )
                    self.shell_inactive_actors[s].satVtkPts.SetPoint(
                        self.shell_actors[s].satPointIDs[i], x, y, z
                    )

            self.shell_actors[s].satPolyData.GetPoints().Modified()
            self.shell_inactive_actors[s].satPolyData.GetPoints().Modified()

            if self.draw_links:
                # grab the arrays of connections
                links = [x for x in self.links[s] if x["active"]]

                # build a vtkPoints object from array
                self.isl_actors[s].linkPoints = vtk.vtkPoints()
                self.isl_actors[s].linkPoints.SetNumberOfPoints(self.shell_sats[s])
                for i in range(self.shell_sats[s]):
                    x = self.sat_positions[s][i]["x"]
                    y = self.sat_positions[s][i]["y"]
                    z = self.sat_positions[s][i]["z"]
                    self.isl_actors[s].linkPoints.SetPoint(i, x, y, z)

                # make clean line arrays
                self.isl_actors[s].islLinkLines = vtk.vtkCellArray()

                # fill isl and gsl arrays
                for i in range(len(links)):
                    e1 = links[i]["node_1"]
                    e2 = links[i]["node_2"]
                    # must translate link endpoints to point names
                    self.isl_actors[s].islLinkLines.InsertNextCell(2)
                    self.isl_actors[s].islLinkLines.InsertCellPoint(e1)
                    self.isl_actors[s].islLinkLines.InsertCellPoint(e2)

                self.isl_actors[s].islPolyData.SetPoints(self.isl_actors[s].linkPoints)
                self.isl_actors[s].islPolyData.SetLines(self.isl_actors[s].islLinkLines)

        # 更新全局信息显示
        self.updateInfoText()

        # update gst points and links
        for i in range(len(self.gst_positions)):
            x = self.gst_positions[i]["x"]
            y = self.gst_positions[i]["y"]
            z = self.gst_positions[i]["z"]
            self.gst_actor.gstVtkPts.SetPoint(self.gst_actor.gstPointIDs[i], x, y, z)

        self.gst_actor.gstPolyData.GetPoints().Modified()

        if self.draw_links:
            # build a vtkPoints object from array
            self.gst_link_actor.gstLinkPoints = vtk.vtkPoints()
            self.gst_link_actor.gstLinkPoints.SetNumberOfPoints(
                self.gst_num + sum(self.shell_sats)
            )

            for i in range(self.gst_num):
                x = self.gst_positions[i]["x"]
                y = self.gst_positions[i]["y"]
                z = self.gst_positions[i]["z"]
                self.gst_link_actor.gstLinkPoints.SetPoint(i, x, y, z)

            num_points = self.gst_num

            for s in range(self.num_shells):
                for i in range(self.shell_sats[s]):
                    x = self.sat_positions[s][i]["x"]
                    y = self.sat_positions[s][i]["y"]
                    z = self.sat_positions[s][i]["z"]
                    self.gst_link_actor.gstLinkPoints.SetPoint(num_points, x, y, z)
                    num_points += 1

            # make clean line arrays
            self.gst_link_actor.gstLinkLines = vtk.vtkCellArray()

            # fill gsl arrays
            offset = self.gst_num

            for s in range(self.num_shells):
                for i in range(len(self.gst_links[s])):
                    e1 = self.gst_links[s][i]["gst"] * -1 - 1
                    e2 = self.gst_links[s][i]["sat"] + offset

                    # must translate link endpoints to point names
                    self.gst_link_actor.gstLinkLines.InsertNextCell(2)
                    self.gst_link_actor.gstLinkLines.InsertCellPoint(e1)
                    self.gst_link_actor.gstLinkLines.InsertCellPoint(e2)

                offset += self.shell_sats[s]


            self.gst_link_actor.gstLinkPolyData.SetPoints(
                self.gst_link_actor.gstLinkPoints
            )
            self.gst_link_actor.gstLinkPolyData.SetLines(
                self.gst_link_actor.gstLinkLines
            )
        # 如果存在路由路径，更新它
        # 确保只有当所有必要的路由变量都不为None时才更新路径
        if (self.route_source_type is not None and
            self.route_target_type is not None and
            hasattr(self, 'route_source_index') and self.route_source_index is not None and
            hasattr(self, 'route_target_index') and self.route_target_index is not None):
            # 使用updateRoutePath方法更新路径请求（只在拓扑变化时发送请求）
            self.updateRoutePath()
            
            # 如果有当前路径节点，重新显示路径（每帧都更新显示，但不重新请求路径）
            if hasattr(self, 'current_path_nodes') and self.current_path_nodes:
                self.displayRoutePath(self.current_path_nodes)
            # 如果没有路径节点，回退到重新计算路径
            elif self.route_path_actor is None:
                # 保存当前的演员
                old_actor = self.route_path_actor
                
                # 重新计算并显示路径
                self.showRoutePath(
                    self.route_source_type,
                    self.route_source_shell,
                    self.route_source_id,
                    self.route_target_type,
                    self.route_target_shell,
                    self.route_target_id
                )
                
                # 如果有旧的演员，移除它
                if old_actor:
                    self.renderer.RemoveActor(old_actor)

        # 更新计数器
        self.frameCount += 1

        obj.GetRenderWindow().Render()

    def updateRoutePath(self):
        """更新路由路径，确保路径随着卫星移动而更新"""
        
        try:
            # 首先检查是否处于重置状态，如果是则不发送新请求
            if hasattr(self, 'route_reset') and self.route_reset:
                # 重置状态下直接返回，不处理任何路由请求
                # 同时确保清除请求挂起标志，防止重置后的第一个step仍然发送请求
                self.route_request_pending = False
                # 清除当前路径显示，确保重置状态下不显示任何路径
                if hasattr(self, 'route_path_actor') and self.route_path_actor:
                    self.renderer.RemoveActor(self.route_path_actor)
                    self.route_path_actor = None
                # 清除当前路径节点，防止重置后仍然显示路径
                if hasattr(self, 'current_path_nodes'):
                    self.current_path_nodes = []
                # 确保last_route_update设置为一个足够大的值，防止在重置后立即发送请求
                self.last_route_update = float('inf')
                
                # 如果处于重置状态，检查是否已经过了足够的时间
                if hasattr(self, 'reset_timer_start') and self.reset_timer_start is not None:
                    if time.time() - self.reset_timer_start > ROUTE_RESET_DURATION:  # 使用常量
                        self.route_reset = False
                        self.reset_timer_start = None
                        print("系统已恢复，可以继续使用路由功能")
                        # 重置后立即更新last_route_update，防止立即发送新请求
                        self.last_route_update = self.current_simulation_time
                
                # 重置状态下直接返回，不处理任何路由请求
                return
                
            # 检查是否有请求正在处理中，如果是则不发送新请求
            if hasattr(self, 'route_request_pending') and self.route_request_pending:
                return
                
            # 检查是否有活动路径
            if (hasattr(self, 'route_source_type') and self.route_source_type is not None and
                hasattr(self, 'route_target_type') and self.route_target_type is not None):
                
                # 检查是否需要重新请求路径数据
                # 只有在以下情况才发送请求：
                # 1. 首次请求路径（last_route_update为None）
                # 2. 网络拓扑发生变化（通过last_animate与current_simulation_time比较）
                # 3. 距离上次更新已经过去了足够长的时间（防止频繁请求）
                current_time = time.time()
                
                # 确保在重置状态下不发送新请求，即使满足其他条件
                if (not self.route_reset and
                    hasattr(self, 'route_source_index') and self.route_source_index is not None and
                    hasattr(self, 'route_target_index') and self.route_target_index is not None and
                    (not hasattr(self, 'last_route_update') or 
                     self.last_route_update is None or 
                     # 检查是否有新的step事件（网络拓扑变化）且已经过了最小更新间隔
                     (self.last_route_update < self.last_animate and 
                      (not hasattr(self, 'last_route_request_time') or 
                       current_time - getattr(self, 'last_route_request_time', 0) > ROUTE_MIN_UPDATE_INTERVAL)))):
                    
                    # 更新上次路由更新的时间戳为当前模拟时间
                    self.last_route_update = self.current_simulation_time
                    # 记录请求时间
                    self.last_route_request_time = current_time
                    
                    try:
                        # 设置请求挂起标志
                        self.route_request_pending = True
                        
                        # 发送路由请求到AnimationConstellation进程
                        self.conn.send({
                            "type": "get_route",
                            "source": self.route_source_index,
                            "target": self.route_target_index
                        })
                        # 不等待响应，响应将在下一次animate循环中处理
                    except (BrokenPipeError, ConnectionError) as e:
                        print(f"发送路由请求时出错: {e}")
                        # 连接错误时不重试，等待下一次更新
                        self.route_request_pending = False
                    except Exception as e:
                        print(f"发送路由请求时出现未知错误: {e}")
                        import traceback
                        traceback.print_exc()
                        self.route_request_pending = False
                
                # 检查是否有更新的路由数据
                if hasattr(self, 'current_path_nodes') and self.current_path_nodes:
                    try:
                        # 移除当前路径显示
                        if hasattr(self, 'route_path_actor') and self.route_path_actor is not None:
                            self.renderer.RemoveActor(self.route_path_actor)
                            self.route_path_actor = None
                        
                        # 清除现有箭头
                        if hasattr(self, 'route_arrows_actors'):
                            for arrow_actor in self.route_arrows_actors:
                                if arrow_actor:
                                    self.renderer.RemoveActor(arrow_actor)
                            self.route_arrows_actors = []

                        # 使用现有路径节点重新绘制路径
                        self.displayRoutePath(self.current_path_nodes)
                    except Exception as e:
                        print(f"更新路径显示时出错: {e}")
                        import traceback
                        traceback.print_exc()
                        # 出错时清除路径显示，防止显示错误的路径
                        self.clearRoutePath()
            elif hasattr(self, 'route_path_actor') and self.route_path_actor is not None:
                # 如果没有活动路径但仍有路径显示，清除它
                self.clearRoutePath()
        except Exception as e:
            print(f"更新路由路径时出现未捕获的错误: {e}")
            import traceback
            traceback.print_exc()
            # 出现未捕获的错误时，尝试清除路径显示
            try:
                self.clearRoutePath()
            except:
                pass

    def updateInfoText(self) -> None:
        """
        更新信息文本显示
        """
        if not self.text_actors:
            return

        # 计算活跃卫星数
        active_sats = 0
        for s in range(self.num_shells):
            for i in range(self.shell_sats[s]):
                if self.sat_positions[s][i]["in_bbox"]:
                    active_sats += 1
        self.active_satellites = active_sats

        # 计算总链路数
        total_links = 0
        for s in range(self.num_shells):
            total_links += sum(1 for link in self.links[s] if link["active"])
        for s in range(self.num_shells):
            total_links += len(self.gst_links[s])
        self.total_links_count = total_links

        # 更新文本显示
        self.text_actors[0].SetInput(f"Simulation Time: {self.current_simulation_time:.2f} s")

        # 计算和显示进度
        if self.simulation_duration > 0:
            # 计算进度百分比
            progress = (self.current_simulation_time - self.simulation_offset) / self.simulation_duration
            progress = max(0.0, min(1.0, progress))  # 确保进度在0-1范围内
            progress_percent = progress * 100

            # 更新进度文本
            self.text_actors[1].SetInput(f"Progress: {progress_percent:.1f}%")

            # 更新进度条
            self.updateProgressBar(progress)
        else:
            self.text_actors[1].SetInput("Progress: Unknown")

        self.text_actors[3].SetInput(f"Active Satellites: {self.active_satellites}")
        self.text_actors[4].SetInput(f"Ground Stations: {self.gst_num}")
        self.text_actors[5].SetInput(f"Total Links: {self.total_links_count}")

        # 如果有选中的对象，更新信息面板
        if self.selected_object == "satellite" and self.selected_shell >= 0 and self.selected_id >= 0:
            self.updateSatelliteInfoPanel(self.selected_shell, self.selected_id)
        elif self.selected_object == "groundstation" and self.selected_id >= 0:
            self.updateGroundStationInfoPanel(self.selected_id)

    def makeInfoTextActors(self) -> None:
        """Create text actors for displaying global information"""
        # Clear existing text actors
        for actor in self.text_actors:
            self.renderer.RemoveActor(actor)
        self.text_actors = []

        # Create text actors
        for i in range(6):  # Pre-create 6 lines of text (removed average delay)
            text_actor = vtk.vtkTextActor()
            text_actor.GetTextProperty().SetFontSize(TEXT_SIZE)
            text_actor.GetTextProperty().SetColor(TEXT_COLOR)
            text_actor.GetTextProperty().SetOpacity(TEXT_OPACITY)
            text_actor.SetPosition(TEXT_POSITION_X, TEXT_POSITION_Y + i * TEXT_LINE_SPACING)
            self.text_actors.append(text_actor)
            self.renderer.AddActor(text_actor)

    def makeProgressBar(self) -> None:
        """
        创建进度条演员
        """
        # 进度条背景
        bg_points = vtk.vtkPoints()
        bg_points.InsertNextPoint(TEXT_POSITION_X, TEXT_POSITION_Y + 2 * TEXT_LINE_SPACING, 0)
        bg_points.InsertNextPoint(TEXT_POSITION_X + PROGRESS_BAR_WIDTH, TEXT_POSITION_Y + 2 * TEXT_LINE_SPACING, 0)
        bg_points.InsertNextPoint(TEXT_POSITION_X + PROGRESS_BAR_WIDTH, TEXT_POSITION_Y + 2 * TEXT_LINE_SPACING + PROGRESS_BAR_HEIGHT, 0)
        bg_points.InsertNextPoint(TEXT_POSITION_X, TEXT_POSITION_Y + 2 * TEXT_LINE_SPACING + PROGRESS_BAR_HEIGHT, 0)

        bg_cells = vtk.vtkCellArray()
        bg_cells.InsertNextCell(4)
        for i in range(4):
            bg_cells.InsertCellPoint(i)

        bg_poly_data = vtk.vtkPolyData()
        bg_poly_data.SetPoints(bg_points)
        bg_poly_data.SetPolys(bg_cells)

        bg_mapper = vtk.vtkPolyDataMapper2D()
        bg_mapper.SetInputData(bg_poly_data)

        self.progress_bg_actor = vtk.vtkActor2D()
        self.progress_bg_actor.SetMapper(bg_mapper)
        self.progress_bg_actor.GetProperty().SetColor(0.3, 0.3, 0.3)  # 深灰色背景
        self.progress_bg_actor.GetProperty().SetOpacity(0.7)
        self.renderer.AddActor(self.progress_bg_actor)

        # 进度条前景(初始宽度为0)
        fg_points = vtk.vtkPoints()
        fg_points.InsertNextPoint(TEXT_POSITION_X, TEXT_POSITION_Y + 2 * TEXT_LINE_SPACING, 0)
        fg_points.InsertNextPoint(TEXT_POSITION_X, TEXT_POSITION_Y + 2 * TEXT_LINE_SPACING, 0)  # 初始宽度为0
        fg_points.InsertNextPoint(TEXT_POSITION_X, TEXT_POSITION_Y + 2 * TEXT_LINE_SPACING + PROGRESS_BAR_HEIGHT, 0)
        fg_points.InsertNextPoint(TEXT_POSITION_X, TEXT_POSITION_Y + 2 * TEXT_LINE_SPACING + PROGRESS_BAR_HEIGHT, 0)

        fg_cells = vtk.vtkCellArray()
        fg_cells.InsertNextCell(4)
        for i in range(4):
            fg_cells.InsertCellPoint(i)

        fg_poly_data = vtk.vtkPolyData()
        fg_poly_data.SetPoints(fg_points)
        fg_poly_data.SetPolys(fg_cells)

        fg_mapper = vtk.vtkPolyDataMapper2D()
        fg_mapper.SetInputData(fg_poly_data)

        self.progress_bar_actor = vtk.vtkActor2D()
        self.progress_bar_actor.SetMapper(fg_mapper)
        self.progress_bar_actor.GetProperty().SetColor(0.0, 0.7, 0.0)  # 绿色进度条
        self.progress_bar_actor.GetProperty().SetOpacity(1.0)
        self.renderer.AddActor(self.progress_bar_actor)

    def updateProgressBar(self, progress: float) -> None:
        """
        更新进度条显示

        :param progress: 进度值，范围0.0-1.0
        """
        if not hasattr(self, 'progress_bar_actor') or not hasattr(self, 'progress_bg_actor'):
            return

        if self.progress_bar_actor is None or self.progress_bg_actor is None:
            return

        # 确保进度在有效范围内
        progress = max(0.0, min(1.0, progress))

        # 更新进度条宽度 - 创建新的点集合
        new_points = vtk.vtkPoints()

        # 左下角点
        new_points.InsertNextPoint(TEXT_POSITION_X, TEXT_POSITION_Y + 2 * TEXT_LINE_SPACING, 0)

        # 右下角点 - 根据进度调整宽度
        width = TEXT_POSITION_X + PROGRESS_BAR_WIDTH * progress
        new_points.InsertNextPoint(width, TEXT_POSITION_Y + 2 * TEXT_LINE_SPACING, 0)

        # 右上角点
        new_points.InsertNextPoint(width, TEXT_POSITION_Y + 2 * TEXT_LINE_SPACING + PROGRESS_BAR_HEIGHT, 0)

        # 左上角点
        new_points.InsertNextPoint(TEXT_POSITION_X, TEXT_POSITION_Y + 2 * TEXT_LINE_SPACING + PROGRESS_BAR_HEIGHT, 0)

        # 创建新的单元格数组
        new_cells = vtk.vtkCellArray()
        new_cells.InsertNextCell(4)
        for i in range(4):
            new_cells.InsertCellPoint(i)

        # 创建新的多边形数据
        new_poly_data = vtk.vtkPolyData()
        new_poly_data.SetPoints(new_points)
        new_poly_data.SetPolys(new_cells)

        # 更新映射器输入数据
        self.progress_bar_actor.GetMapper().SetInputData(new_poly_data)
        self.progress_bar_actor.GetMapper().Update()

    def makeInfoPanel(self) -> None:
        """创建信息面板（初始隐藏）"""
        # 创建面板背景
        panel_points = vtk.vtkPoints()
        panel_points.InsertNextPoint(0, 0, 0)  # 左上
        panel_points.InsertNextPoint(INFO_PANEL_WIDTH, 0, 0)  # 右上
        panel_points.InsertNextPoint(INFO_PANEL_WIDTH, -200, 0)  # 右下（高度动态调整）
        panel_points.InsertNextPoint(0, -200, 0)  # 左下

        panel_cells = vtk.vtkCellArray()
        panel_cells.InsertNextCell(4)
        panel_cells.InsertCellPoint(0)
        panel_cells.InsertCellPoint(1)
        panel_cells.InsertCellPoint(2)
        panel_cells.InsertCellPoint(3)

        panel_poly_data = vtk.vtkPolyData()
        panel_poly_data.SetPoints(panel_points)
        panel_poly_data.SetPolys(panel_cells)

        panel_mapper = vtk.vtkPolyDataMapper2D()
        panel_mapper.SetInputData(panel_poly_data)

        self.info_panel_actor = vtk.vtkActor2D()
        self.info_panel_actor.SetMapper(panel_mapper)
        self.info_panel_actor.GetProperty().SetColor(INFO_PANEL_BG_COLOR)
        self.info_panel_actor.GetProperty().SetOpacity(INFO_PANEL_OPACITY)
        self.info_panel_actor.SetPosition(100, 400)  # 初始位置
        self.info_panel_actor.VisibilityOff()  # 初始隐藏
        self.renderer.AddActor(self.info_panel_actor)

        # 创建关闭按钮
        close_btn_points = vtk.vtkPoints()
        close_btn_points.InsertNextPoint(0, 0, 0)  # 左上
        close_btn_points.InsertNextPoint(INFO_PANEL_CLOSE_BTN_SIZE, 0, 0)  # 右上
        close_btn_points.InsertNextPoint(INFO_PANEL_CLOSE_BTN_SIZE, -INFO_PANEL_CLOSE_BTN_SIZE, 0)  # 右下
        close_btn_points.InsertNextPoint(0, -INFO_PANEL_CLOSE_BTN_SIZE, 0)  # 左下

        close_btn_cells = vtk.vtkCellArray()
        close_btn_cells.InsertNextCell(4)
        close_btn_cells.InsertCellPoint(0)
        close_btn_cells.InsertCellPoint(1)
        close_btn_cells.InsertCellPoint(2)
        close_btn_cells.InsertCellPoint(3)

        close_btn_poly_data = vtk.vtkPolyData()
        close_btn_poly_data.SetPoints(close_btn_points)
        close_btn_poly_data.SetPolys(close_btn_cells)

        close_btn_mapper = vtk.vtkPolyDataMapper2D()
        close_btn_mapper.SetInputData(close_btn_poly_data)

        self.info_panel_close_btn = vtk.vtkActor2D()
        self.info_panel_close_btn.SetMapper(close_btn_mapper)
        self.info_panel_close_btn.GetProperty().SetColor(INFO_PANEL_CLOSE_BTN_COLOR)
        self.info_panel_close_btn.GetProperty().SetOpacity(1.0)
        self.info_panel_close_btn.SetPosition(100 + INFO_PANEL_WIDTH - INFO_PANEL_CLOSE_BTN_SIZE - INFO_PANEL_PADDING, 400)  # 右上角
        self.info_panel_close_btn.VisibilityOff()  # 初始隐藏
        self.renderer.AddActor(self.info_panel_close_btn)

        # 创建SSH按钮
        ssh_btn_points = vtk.vtkPoints()
        ssh_btn_points.InsertNextPoint(0, 0, 0)  # 左上
        ssh_btn_points.InsertNextPoint(INFO_PANEL_SSH_BTN_WIDTH, 0, 0)  # 右上
        ssh_btn_points.InsertNextPoint(INFO_PANEL_SSH_BTN_WIDTH, -INFO_PANEL_SSH_BTN_HEIGHT, 0)  # 右下
        ssh_btn_points.InsertNextPoint(0, -INFO_PANEL_SSH_BTN_HEIGHT, 0)  # 左下

        ssh_btn_cells = vtk.vtkCellArray()
        ssh_btn_cells.InsertNextCell(4)
        ssh_btn_cells.InsertCellPoint(0)
        ssh_btn_cells.InsertCellPoint(1)
        ssh_btn_cells.InsertCellPoint(2)
        ssh_btn_cells.InsertCellPoint(3)

        ssh_btn_poly_data = vtk.vtkPolyData()
        ssh_btn_poly_data.SetPoints(ssh_btn_points)
        ssh_btn_poly_data.SetPolys(ssh_btn_cells)

        ssh_btn_mapper = vtk.vtkPolyDataMapper2D()
        ssh_btn_mapper.SetInputData(ssh_btn_poly_data)

        self.info_panel_ssh_btn = vtk.vtkActor2D()
        self.info_panel_ssh_btn.SetMapper(ssh_btn_mapper)
        self.info_panel_ssh_btn.GetProperty().SetColor(INFO_PANEL_SSH_BTN_COLOR)
        self.info_panel_ssh_btn.GetProperty().SetOpacity(1.0)
        self.info_panel_ssh_btn.SetPosition(100 + INFO_PANEL_PADDING, 400 - 150)  # 初始位置，将在更新面板时调整
        self.info_panel_ssh_btn.VisibilityOff()  # 初始隐藏
        self.renderer.AddActor(self.info_panel_ssh_btn)

        # 创建SSH按钮文本
        self.ssh_btn_text = vtk.vtkTextActor()
        self.ssh_btn_text.SetInput("SSH")
        self.ssh_btn_text.GetTextProperty().SetFontSize(INFO_PANEL_TEXT_SIZE)
        self.ssh_btn_text.GetTextProperty().SetColor(INFO_PANEL_SSH_BTN_TEXT_COLOR)
        self.ssh_btn_text.GetTextProperty().SetJustificationToCentered()
        self.ssh_btn_text.GetTextProperty().SetVerticalJustificationToCentered()
        self.ssh_btn_text.SetPosition(100 + INFO_PANEL_PADDING + INFO_PANEL_SSH_BTN_WIDTH/2, 400 - 150 - INFO_PANEL_SSH_BTN_HEIGHT/2)
        self.ssh_btn_text.VisibilityOff()  # 初始隐藏
        self.renderer.AddActor(self.ssh_btn_text)

        # 创建面板文本
        for i in range(10):  # 预创建10行文本
            text_actor = vtk.vtkTextActor()
            text_actor.GetTextProperty().SetFontSize(INFO_PANEL_TEXT_SIZE)
            text_actor.GetTextProperty().SetColor(INFO_PANEL_TEXT_COLOR)
            text_actor.GetTextProperty().SetOpacity(TEXT_OPACITY)
            text_actor.SetPosition(100 + INFO_PANEL_PADDING, 400 - INFO_PANEL_PADDING - i * INFO_PANEL_LINE_HEIGHT)
            text_actor.VisibilityOff()  # 初始隐藏
            self.info_panel_text_actors.append(text_actor)
            self.renderer.AddActor(text_actor)

    def setupPicker(self) -> None:
        """设置点击拾取器"""
        # 创建点拾取器
        picker = vtk.vtkPointPicker()
        picker.SetTolerance(0.01)  # 增加容差，使点击更容易命中
        self.interactor.SetPicker(picker)

        # 添加点击事件回调
        self.interactor.AddObserver("LeftButtonPressEvent", self.handleClick)
        self.interactor.AddObserver("RightButtonPressEvent", self.handleRightClick)

        # 添加键盘事件回调
        self.interactor.AddObserver("KeyPressEvent", self.handleKeyPress)

    def handleKeyPress(self, obj: typing.Any, event: typing.Any) -> None:
        """处理键盘按键事件"""
        key = obj.GetKeySym()
        # 数字键1：重置路由路径选择
        if key == "1":
            # 完全清除路径显示和选择
            self.clearRoutePath()
            print("路由路径选择已重置")
            
    def clearRoutePath(self) -> None:
        """清除路由路径显示和选择"""
        # 删除路径显示器
        if hasattr(self, 'route_path_actor') and self.route_path_actor:
            self.renderer.RemoveActor(self.route_path_actor)
            self.route_path_actor = None
            
        # 清除箭头
        if hasattr(self, 'route_arrows_actors'):
            for arrow_actor in self.route_arrows_actors:
                if arrow_actor:
                    self.renderer.RemoveActor(arrow_actor)
            self.route_arrows_actors = []

        # 重置路由选择变量
        self.route_source_type = None
        self.route_source_shell = None
        self.route_source_id = None
        self.route_target_type = None
        self.route_target_shell = None
        self.route_target_id = None
        
        # 重置路由索引变量，防止继续请求路径
        if hasattr(self, 'route_source_index'):
            self.route_source_index = None
        if hasattr(self, 'route_target_index'):
            self.route_target_index = None
        
        # 取消任何挂起的路由请求
        if hasattr(self, 'route_request_pending'):
            self.route_request_pending = False
        
        # 添加一个重置标志，防止在重置后继续处理路由请求
        self.route_reset = True
            
        # 设置一个非常大的last_route_update值，确保不会在重置后继续发送请求
        # 使用一个足够大的值，比当前模拟时间大很多，这样可以防止在接下来的step中发送请求
        if hasattr(self, 'last_route_update'):
            self.last_route_update = float('inf')  # 使用无穷大，确保不会触发更新
        
        # 确保last_route_request_time也被重置，防止在重置后立即发送新请求
        if hasattr(self, 'last_route_request_time'):
            self.last_route_request_time = time.time() + ROUTE_RESET_DURATION  # 设置为未来时间
            
        # 设置一个定时器，在一段时间后自动重置route_reset标志
        self.reset_timer_start = time.time()

        # 清除当前路径节点
        self.current_path_nodes = None

        # 清空连接缓冲区，避免之前的请求响应被处理
        try:
            while self.conn.poll():
                _ = self.conn.recv()
        except Exception:
            pass

        # 更新渲染
        if hasattr(self, 'renderWindow'):
            self.renderWindow.Render()

        print("路由路径已清除，系统已进入重置状态")

    def handleRightClick(self, obj: typing.Any, event: typing.Any) -> None:
        """处理右键点击事件，用于选择路由路径的起点和终点"""
        # 如果已经有请求挂起，不处理新的点击
        if hasattr(self, 'route_request_pending') and self.route_request_pending:
            print("路由请求正在处理中，请稍候...")
            return
            
        # 如果处于重置状态，检查是否已经过了足够的时间
        if hasattr(self, 'route_reset') and self.route_reset:
            # 如果已经过了3秒，自动解除重置状态
            if hasattr(self, 'reset_timer_start') and self.reset_timer_start is not None:
                if time.time() - self.reset_timer_start > 3.0:  # 3秒后自动解除重置状态
                    self.route_reset = False
                    self.reset_timer_start = None
                    print("系统已恢复，可以继续使用路由功能")
                else:
                    print("系统刚刚重置，请稍候再试...")
                    return
            else:
                print("系统刚刚重置，请稍候再试...")
                return
            
        # 获取点击位置
        clickPos = self.interactor.GetEventPosition()

        # 使用拾取器检测点击的对象
        picker = self.interactor.GetPicker()

        # 首先尝试检测地面站
        for gst_id in range(self.gst_num):
            # 获取地面站的世界坐标
            gst_coords = self.gst_positions[gst_id]
            # 将世界坐标转换为屏幕坐标
            gst_world_pos = [gst_coords['x'], gst_coords['y'], gst_coords['z']]
            # 使用vtkCoordinate进行坐标转换
            coordinate = vtk.vtkCoordinate()
            coordinate.SetCoordinateSystemToWorld()
            coordinate.SetValue(gst_world_pos[0], gst_world_pos[1], gst_world_pos[2])
            gst_screen_pos = coordinate.GetComputedDisplayValue(self.renderer)

            # 如果点击位置在地面站点的一定范围内
            if (gst_screen_pos and
                abs(clickPos[0] - gst_screen_pos[0]) < 15 and
                abs(clickPos[1] - gst_screen_pos[1]) < 15):
                # 如果没有选择起点，则设置为起点
                if self.route_source_type is None:
                    self.route_source_type = "groundstation"
                    self.route_source_shell = -1  # 地面站的shell始终为-1
                    self.route_source_id = gst_id
                    print(f"Selected ground station {gst_id} as route source")
                    return
                # 如果已有起点，则计算并显示路径
                else:
                    self.route_target_type = "groundstation"
                    self.route_target_shell = -1
                    self.route_target_id = gst_id
                    self.showRoutePath(
                        self.route_source_type,
                        self.route_source_shell,
                        self.route_source_id,
                        self.route_target_type,
                        self.route_target_shell,
                        self.route_target_id
                    )
                    return

        # 如果没有点击地面站，再检查卫星
        picker.Pick(clickPos[0], clickPos[1], 0, self.renderer)

        # 获取拾取的演员和点ID
        actor = picker.GetActor()
        point_id = picker.GetPointId()

        if actor is None:
            return

        # 检查是否点击了卫星
        for s in range(self.num_shells):
            if ((actor == self.shell_actors[s].satsActor or
                  actor == self.shell_inactive_actors[s].inactiveSatsActor) and
                point_id >= 0 and point_id < self.shell_sats[s]):
                # 如果没有选择起点，则设置为起点
                if self.route_source_type is None:
                    self.route_source_type = "satellite"
                    self.route_source_shell = s
                    self.route_source_id = point_id
                    print(f"Selected satellite {s}-{point_id} as route source")
                    return
                # 如果已有起点，则计算并显示路径
                else:
                    self.route_target_type = "satellite"
                    self.route_target_shell = s
                    self.route_target_id = point_id
                    self.showRoutePath(
                        self.route_source_type,
                        self.route_source_shell,
                        self.route_source_id,
                        self.route_target_type,
                        self.route_target_shell,
                        self.route_target_id
                    )
                    return

        # 如果点击了其他对象，清除路由选择
        self.clearRoutePath()

    def showRoutePath(self, source_type: str, source_shell: int, source_id: int,
                     target_type: str, target_shell: int, target_id: int) -> None:
        """显示两个节点之间的路由路径，不考虑节点是否活跃"""
        # 清除现有路径
        if self.route_path_actor:
            self.renderer.RemoveActor(self.route_path_actor)
            self.route_path_actor = None

        # 清除现有箭头
        for arrow_actor in self.route_arrows_actors:
            if arrow_actor:
                self.renderer.RemoveActor(arrow_actor)
        self.route_arrows_actors = []
        
        # 重置标志设为False，允许发送新的请求
        self.route_reset = False
        # 清除重置定时器
        if hasattr(self, 'reset_timer_start'):
            self.reset_timer_start = None

        # 计算源节点和目标节点的全局索引
        source_index = -1
        target_index = -1

        # 计算源节点全局索引
        if source_type == "satellite":
            # 计算之前shell的卫星总数
            offset = 0
            for s in range(source_shell):
                offset += self.shell_sats[s]
            source_index = offset + source_id
        else:  # groundstation
            source_index = sum(self.shell_sats) + source_id

        # 计算目标节点全局索引
        if target_type == "satellite":
            # 计算之前shell的卫星总数
            offset = 0
            for s in range(target_shell):
                offset += self.shell_sats[s]
            target_index = offset + target_id
        else:  # groundstation
            target_index = sum(self.shell_sats) + target_id

        # 保存路由源和目标信息，用于后续更新
        self.route_source_index = source_index
        self.route_target_index = target_index
        
        # 设置路由请求标志，但不在这里等待响应
        # 这样可以避免在事件处理函数中阻塞UI线程
        self.route_request_pending = True
        
        # 发送路由请求到AnimationConstellation进程
        try:
            self.conn.send({
                "type": "get_route",
                "source": source_index,
                "target": target_index
            })
            
            # 设置请求时间，用于超时检测
            self.route_request_time = time.time()
            
            # 先显示一个直接连接的临时路径
            # 获取源节点和目标节点的位置
            source_pos = None
            target_pos = None

            # 获取源节点位置
            if source_type == "satellite":
                source_pos = self.sat_positions[source_shell][source_id]
            else:  # groundstation
                source_pos = self.gst_positions[source_id]

            # 获取目标节点位置
            if target_type == "satellite":
                target_pos = self.sat_positions[target_shell][target_id]
            else:  # groundstation
                target_pos = self.gst_positions[target_id]

            if not source_pos or not target_pos:
                print("无法获取节点位置")
                return

            # 创建一个简单的两点路径作为临时显示
            direct_path = [source_index, target_index]
            self.displayRoutePath(direct_path)
            
            # 保存路由信息
            if not hasattr(self, 'last_route_info') or self.last_route_info != (source_type, source_id, target_type, target_id):
                print(f"请求从 {source_type}-{source_id} 到 {target_type}-{target_id} 的路由路径")
                self.last_route_info = (source_type, source_id, target_type, target_id)
            
            # 更新渲染
            self.renderWindow.Render()
            
        except Exception as e:
            print(f"发送路由请求时出错: {e}")
            import traceback
            traceback.print_exc()
            self.route_request_pending = False

    def handleClick(self, obj: typing.Any, event: typing.Any) -> None:
        """处理点击事件"""
        # 获取点击位置
        clickPos = self.interactor.GetEventPosition()

        # 检查是否点击了关闭按钮
        if self.info_panel_close_btn and self.info_panel_close_btn.GetVisibility():
            btn_pos = self.info_panel_close_btn.GetPosition()
            if (clickPos[0] >= btn_pos[0] and
                clickPos[0] <= btn_pos[0] + INFO_PANEL_CLOSE_BTN_SIZE and
                clickPos[1] >= btn_pos[1] - INFO_PANEL_CLOSE_BTN_SIZE and
                clickPos[1] <= btn_pos[1]):
                self.hideInfoPanel()
                return

        # 检查是否点击了SSH按钮
        if self.info_panel_ssh_btn and self.info_panel_ssh_btn.GetVisibility():
            btn_pos = self.info_panel_ssh_btn.GetPosition()
            if (clickPos[0] >= btn_pos[0] and
                clickPos[0] <= btn_pos[0] + INFO_PANEL_SSH_BTN_WIDTH and
                clickPos[1] >= btn_pos[1] - INFO_PANEL_SSH_BTN_HEIGHT and
                clickPos[1] <= btn_pos[1]):
                self.executeSSHCommand()
                return

        # 使用拾取器检测点击的对象
        picker = self.interactor.GetPicker()

        # 首先尝试检测地面站（设置更高的优先级）
        # 遍历所有地面站点，检查点击位置是否在地面站附近
        for gst_id in range(self.gst_num):
            # 获取地面站的世界坐标
            gst_coords = self.gst_positions[gst_id]
            # 将世界坐标转换为屏幕坐标
            gst_world_pos = [gst_coords['x'], gst_coords['y'], gst_coords['z']]
            # 使用vtkCoordinate进行坐标转换，这是VTK推荐的方式
            coordinate = vtk.vtkCoordinate()
            coordinate.SetCoordinateSystemToWorld()
            coordinate.SetValue(gst_world_pos[0], gst_world_pos[1], gst_world_pos[2])
            gst_screen_pos = coordinate.GetComputedDisplayValue(self.renderer)

            # 如果点击位置在地面站点的一定范围内（增大点击区域）
            if (gst_screen_pos and
                 abs(clickPos[0] - gst_screen_pos[0]) < 15 and
                abs(clickPos[1] - gst_screen_pos[1]) < 15):
                self.selected_object = "groundstation"
                self.selected_shell = -1
                self.selected_id = gst_id
                self.updateGroundStationInfoPanel(gst_id)
                return

        # 如果没有点击地面站，再检查卫星和其他对象
        picker.Pick(clickPos[0], clickPos[1], 0, self.renderer)

        # 获取拾取的演员和点ID
        actor = picker.GetActor()
        point_id = picker.GetPointId()

        if actor is None:
            # 如果点击空白处，隐藏信息面板
            self.hideInfoPanel()
            return

        # 检查是否点击了卫星
        for s in range(self.num_shells):
            if ((actor == self.shell_actors[s].satsActor or
                  actor == self.shell_inactive_actors[s].inactiveSatsActor) and
                point_id >= 0 and point_id < self.shell_sats[s]):
                self.selected_object = "satellite"
                self.selected_shell = s
                self.selected_id = point_id
                self.updateSatelliteInfoPanel(s, point_id)
                return

        # 如果点击了其他对象，隐藏信息面板
        self.hideInfoPanel()

    def updateSatelliteInfoPanel(self, shell: int, sat_id: int) -> None:
        """更新卫星信息面板"""
        if shell < 0 or shell >= self.num_shells or sat_id < 0 or sat_id >= self.shell_sats[shell]:
            return

        # 获取卫星信息
        sat = self.sat_positions[shell][sat_id]

        # 计算卫星IP地址
        ipv6 = self.calculateIPv6(shell + 1, sat_id)  # shell_identifier从1开始
        ipv4 = self.calculateIPv4(shell + 1, sat_id)

        # 固定面板位置在屏幕右上角
        window_size = self.renderWindow.GetSize()
        panel_pos_x = window_size[0] - INFO_PANEL_WIDTH - 20  # 右边距20像素
        panel_pos_y = window_size[1] - 20  # 顶部边距20像素
        self.info_panel_actor.SetPosition(panel_pos_x, panel_pos_y)

        # 更新面板文本
        self.info_panel_text_actors[0].SetInput(f"Satellite Info")
        self.info_panel_text_actors[1].SetInput(f"SHELL-ID: {shell+1}-{sat_id}")
        self.info_panel_text_actors[2].SetInput(f"IPv6: {ipv6}")
        self.info_panel_text_actors[3].SetInput(f"IPv4: {ipv4}")
        self.info_panel_text_actors[4].SetInput(f"Position: ({sat['x']:.0f}, {sat['y']:.0f}, {sat['z']:.0f})")
        self.info_panel_text_actors[5].SetInput(f"Status: {'Active' if sat['in_bbox'] else 'Inactive'}")

        # 调整面板大小以容纳SSH按钮
        panel_height = 6 * INFO_PANEL_LINE_HEIGHT + INFO_PANEL_SSH_BTN_HEIGHT + 3 * INFO_PANEL_PADDING
        points = self.info_panel_actor.GetMapper().GetInput().GetPoints()
        points.SetPoint(2, INFO_PANEL_WIDTH, -panel_height, 0)
        points.SetPoint(3, 0, -panel_height, 0)
        points.Modified()

        # 更新文本位置
        for i in range(6):
            self.info_panel_text_actors[i].SetPosition(
                panel_pos_x + INFO_PANEL_PADDING,
                panel_pos_y - INFO_PANEL_PADDING - (i + 1) * INFO_PANEL_LINE_HEIGHT  # 向下调整一行的高度
            )
            self.info_panel_text_actors[i].VisibilityOn()

        # 隐藏未使用的文本
        for i in range(6, len(self.info_panel_text_actors)):
            self.info_panel_text_actors[i].VisibilityOff()

        # 更新关闭按钮位置
        self.info_panel_close_btn.SetPosition(
            panel_pos_x + INFO_PANEL_WIDTH - INFO_PANEL_CLOSE_BTN_SIZE - INFO_PANEL_PADDING,
            panel_pos_y
        )
        self.info_panel_close_btn.VisibilityOn()

        # 更新SSH按钮位置
        ssh_btn_y = panel_pos_y - 6 * INFO_PANEL_LINE_HEIGHT - 2 * INFO_PANEL_PADDING
        self.info_panel_ssh_btn.SetPosition(
            panel_pos_x + INFO_PANEL_WIDTH/2 - INFO_PANEL_SSH_BTN_WIDTH/2,
            ssh_btn_y
        )
        self.info_panel_ssh_btn.VisibilityOn()

        # 更新SSH按钮文本位置
        self.ssh_btn_text.SetPosition(
            panel_pos_x + INFO_PANEL_WIDTH/2,
            ssh_btn_y - INFO_PANEL_SSH_BTN_HEIGHT/2
        )
        self.ssh_btn_text.VisibilityOn()

        # 显示面板
        self.info_panel_actor.VisibilityOn()

    def updateGroundStationInfoPanel(self, gst_id: int) -> None:
        """更新地面站信息面板"""
        if gst_id < 0 or gst_id >= self.gst_num:
            return

        # 获取地面站信息
        gst = self.gst_positions[gst_id]

        # 计算地面站IP地址（地面站的shell为0）
        ipv6 = self.calculateIPv6(0, gst_id)
        ipv4 = self.calculateIPv4(0, gst_id)

        # 获取地面站名称（如果可用）
        name = "Unknown"
        # 简化名称获取逻辑，只要确保索引有效即可
        if hasattr(self, 'gst_names') and self.gst_names and gst_id < len(self.gst_names):
            name = self.gst_names[gst_id] or "Unknown"  # 使用or运算符简化逻辑

        # 固定面板位置在屏幕右上角
        window_size = self.renderWindow.GetSize()
        panel_pos_x = window_size[0] - INFO_PANEL_WIDTH - 20  # 右边距20像素
        panel_pos_y = window_size[1] - 20  # 顶部边距20像素
        self.info_panel_actor.SetPosition(panel_pos_x, panel_pos_y)

        # 更新面板文本
        self.info_panel_text_actors[0].SetInput(f"Ground Station Info")
        self.info_panel_text_actors[1].SetInput(f"Name: {name}")
        self.info_panel_text_actors[2].SetInput(f"ID: {gst_id}")
        self.info_panel_text_actors[3].SetInput(f"IPv6: {ipv6}")
        self.info_panel_text_actors[4].SetInput(f"IPv4: {ipv4}")
        self.info_panel_text_actors[5].SetInput(f"Position: ({gst['x']:.0f}, {gst['y']:.0f}, {gst['z']:.0f})")

        # 调整面板大小以容纳SSH按钮
        panel_height = 6 * INFO_PANEL_LINE_HEIGHT + INFO_PANEL_SSH_BTN_HEIGHT + 3 * INFO_PANEL_PADDING
        points = self.info_panel_actor.GetMapper().GetInput().GetPoints()
        points.SetPoint(2, INFO_PANEL_WIDTH, -panel_height, 0)
        points.SetPoint(3, 0, -panel_height, 0)
        points.Modified()

        # 更新文本位置
        for i in range(6):
            self.info_panel_text_actors[i].SetPosition(
                panel_pos_x + INFO_PANEL_PADDING,
                panel_pos_y - INFO_PANEL_PADDING - (i + 1) * INFO_PANEL_LINE_HEIGHT  # 向下调整一行的高度
            )
            self.info_panel_text_actors[i].VisibilityOn()

        # 隐藏未使用的文本
        for i in range(6, len(self.info_panel_text_actors)):
            self.info_panel_text_actors[i].VisibilityOff()

        # 更新关闭按钮位置
        self.info_panel_close_btn.SetPosition(
            panel_pos_x + INFO_PANEL_WIDTH - INFO_PANEL_CLOSE_BTN_SIZE - INFO_PANEL_PADDING,
            panel_pos_y
        )
        self.info_panel_close_btn.VisibilityOn()

        # 更新SSH按钮位置
        ssh_btn_y = panel_pos_y - 6 * INFO_PANEL_LINE_HEIGHT - 2 * INFO_PANEL_PADDING
        self.info_panel_ssh_btn.SetPosition(
            panel_pos_x + INFO_PANEL_WIDTH/2 - INFO_PANEL_SSH_BTN_WIDTH/2,
            ssh_btn_y
        )
        self.info_panel_ssh_btn.VisibilityOn()

        # 更新SSH按钮文本位置
        self.ssh_btn_text.SetPosition(
            panel_pos_x + INFO_PANEL_WIDTH/2,
            ssh_btn_y - INFO_PANEL_SSH_BTN_HEIGHT/2
        )
        self.ssh_btn_text.VisibilityOn()

        # 显示面板
        self.info_panel_actor.VisibilityOn()

    def hideInfoPanel(self) -> None:
        """隐藏信息面板"""
        self.info_panel_actor.VisibilityOff()
        self.info_panel_close_btn.VisibilityOff()
        self.info_panel_ssh_btn.VisibilityOff()
        self.ssh_btn_text.VisibilityOff()
        for actor in self.info_panel_text_actors:
            actor.VisibilityOff()
        self.selected_object = None
        self.selected_shell = -1
        self.selected_id = -1

    def calculateIPv6(self, shell: int, node_id: int) -> str:
        """根据shell和node_id计算IPv6地址"""
        byte1 = 10  # 固定为10
        byte2 = shell  # shell标识符
        byte3 = (node_id >> 6) & 0xFF  # 节点标识符，右移6位
        byte4 = (node_id << 2) & 0xFF  # 节点标识符，左移2位

        # 计算IPv6地址
        ipv6_address = f"fd00::{byte1:x}:{byte2:x}:{byte3:x}:{(byte4 + 2):x}"
        return ipv6_address

    def calculateIPv4(self, shell: int, node_id: int) -> str:
        """根据shell和node_id计算IPv4地址"""
        byte1 = 10  # 固定为10
        byte2 = shell  # shell标识符
        byte3 = (node_id >> 6) & 0xFF  # 节点标识符，右移6位
        byte4 = ((node_id << 2) & 0xFF) + 2  # 节点标识符，左移2位，加2

        # 计算IPv4地址
        ipv4_address = f"{byte1}.{byte2}.{byte3}.{byte4}"
        return ipv4_address

    def executeSSHCommand(self) -> None:
        """执行SSH命令，连接到选中的卫星或地面站"""
        if self.selected_object is None:
            print("No object selected for SSH connection")
            return

        # 获取IP地址
        ip_address = ""
        terminal_title = "Terminal"  # 默认终端标题

        if self.selected_object == "satellite" and self.selected_shell >= 0 and self.selected_id >= 0:
            # 使用IPv4地址连接卫星
            ip_address = self.calculateIPv4(self.selected_shell + 1, self.selected_id)
            # 设置终端标题为SHELL-ID格式
            terminal_title = f"SHELL{self.selected_shell + 1}-{self.selected_id}"
        elif self.selected_object == "groundstation" and self.selected_id >= 0:
            # 使用IPv4地址连接地面站
            ip_address = self.calculateIPv4(0, self.selected_id)
            # 设置终端标题为gst-NAME格式
            if self.selected_id < len(self.gst_names) and self.gst_names[self.selected_id]:
                terminal_title = f"gst-{self.gst_names[self.selected_id]}"
            else:
                terminal_title = f"gst-{self.selected_id}"

        if not ip_address:
            print("Failed to get IP address for SSH connection")
            return

        # 构建SSH命令
        ssh_key_path = os.path.expanduser(SSH_KEY_PATH)  # 展开波浪号为用户主目录
        ssh_command = f"ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i {ssh_key_path} root@{ip_address}"

        try:
            # 使用gnome-terminal或xterm启动新终端并执行SSH命令
            # 尝试使用gnome-terminal，添加--title参数设置窗口标题
            subprocess.Popen(["gnome-terminal", "--title", terminal_title, "--", "bash", "-c", ssh_command])
        except FileNotFoundError:
            try:
                # 如果gnome-terminal不可用，尝试使用xterm，添加-title参数设置窗口标题
                subprocess.Popen(["xterm", "-title", terminal_title, "-e", ssh_command])
            except FileNotFoundError:
                print("Failed to open terminal. Neither gnome-terminal nor xterm is available.")
        except Exception as e:
            print(f"Error executing SSH command: {e}")

    def makeRenderWindow(self) -> None:
        """
        Makes a render window object using vtk.

        This should not be called until all the actors are created.
        """

        # create a renderer object
        self.renderer = vtk.vtkRenderer()
        self.renderWindow = vtk.vtkRenderWindow()
        self.renderWindow.AddRenderer(self.renderer)

        # create an interactor object, to interact with the window... duh
        self.interactor = vtk.vtkRenderWindowInteractor()
        self.interactor.SetInteractorStyle(vtk.vtkInteractorStyleTrackballCamera())
        self.interactor.SetRenderWindow(self.renderWindow)

        # add the actor objects
        for actor in self.shell_actors:
            self.renderer.AddActor(actor.satsActor)

        for actor in self.shell_inactive_actors:
            self.renderer.AddActor(actor.inactiveSatsActor)

        self.renderer.AddActor(self.earthActor)
        self.renderer.AddActor(self.sphereActor)

        if self.draw_links:
            for actor in self.isl_actors:
                self.renderer.AddActor(actor.islActor)

        self.renderer.AddActor(self.gst_actor.gstsActor)

        if self.draw_links:
            self.renderer.AddActor(self.gst_link_actor.gstLinkActor)

        # 创建信息文本和进度条
        self.makeInfoTextActors()
        self.makeProgressBar()

        # 创建信息面板（初始隐藏）
        self.makeInfoPanel()

        # 设置点击交互
        self.setupPicker()

        # white background, makes it easier to
        # put screenshots of animation into papers/presentations
        self.renderer.SetBackground(BACKGROUND_COLOR)

        self.interactor.Initialize()
        # set up a timer to call the update function at a max rate
        # of every 7 ms (~144 hz)

        self.interactor.AddObserver("TimerEvent", self._updateAnimation)
        self.interactor.CreateRepeatingTimer(self.frequency)

        # start the model
        self.renderWindow.SetSize(2048, 2048)
        self.renderWindow.Render()

        # print("🖍  Animation: ready to return control...")
        # self.conn.send(True)

        self.initialized = True

        self.interactor.Start()

    def makeSatsActor(self, shell_no: int, shell_total_sats: int) -> None:
        """
        generate the point cloud to represent satellites

        :param shell_no: index of this shell
        :param shell_total_satellites: number of satellites in the shell
        """

        # declare a points & cell array to hold position data
        self.shell_actors[shell_no].satVtkPts = vtk.vtkPoints()
        self.shell_actors[shell_no].satVtkVerts = vtk.vtkCellArray()

        # init a array for IDs
        self.shell_actors[shell_no].satPointIDs = [None] * shell_total_sats

        # initialize all the positions
        for i in range(len(self.sat_positions[shell_no])):
            self.shell_actors[shell_no].satPointIDs[i] = self.shell_actors[
                shell_no
            ].satVtkPts.InsertNextPoint(
                self.sat_positions[shell_no][i]["x"],
                self.sat_positions[shell_no][i]["y"],
                self.sat_positions[shell_no][i]["z"],
            )

            self.shell_actors[shell_no].satVtkVerts.InsertNextCell(1)
            self.shell_actors[shell_no].satVtkVerts.InsertCellPoint(
                self.shell_actors[shell_no].satPointIDs[i]
            )

        # convert points into poly data
        # (because that's what they do in the vtk examples)
        self.shell_actors[shell_no].satPolyData = vtk.vtkPolyData()
        self.shell_actors[shell_no].satPolyData.SetPoints(
            self.shell_actors[shell_no].satVtkPts
        )
        self.shell_actors[shell_no].satPolyData.SetVerts(
            self.shell_actors[shell_no].satVtkVerts
        )

        # create mapper object and connect to the poly data
        self.shell_actors[shell_no].satsMapper = vtk.vtkPolyDataMapper()
        self.shell_actors[shell_no].satsMapper.SetInputData(
            self.shell_actors[shell_no].satPolyData
        )

        # create actor, and connect to the mapper
        # (again, its just what you do to make a vtk render pipeline)
        self.shell_actors[shell_no].satsActor = vtk.vtkActor()
        self.shell_actors[shell_no].satsActor.SetMapper(
            self.shell_actors[shell_no].satsMapper
        )

        # edit appearance of satellites
        self.shell_actors[shell_no].satsActor.GetProperty().SetOpacity(SAT_OPACITY)
        self.shell_actors[shell_no].satsActor.GetProperty().SetColor(
            self.sat_colors[shell_no]
        )
        self.shell_actors[shell_no].satsActor.GetProperty().SetPointSize(SAT_POINT_SIZE)

    def makeInactiveSatsActor(self, shell_no: int, shell_total_sats: int) -> None:
        """
        generate the point cloud to represent inactive satellites

        :param shell_no: index of this shell
        :param shell_total_satellites: number of satellites in the shell
        """

        # declare a points & cell array to hold position data
        self.shell_inactive_actors[shell_no].satVtkPts = vtk.vtkPoints()
        self.shell_inactive_actors[shell_no].satVtkVerts = vtk.vtkCellArray()

        # init a array for IDs
        self.shell_inactive_actors[shell_no].satPointIDs = [None] * shell_total_sats

        # initialize all the positions
        for i in range(len(self.sat_positions[shell_no])):
            self.shell_inactive_actors[shell_no].satPointIDs[i] = (
                self.shell_inactive_actors[shell_no].satVtkPts.InsertNextPoint(0, 0, 0)
            )

            self.shell_inactive_actors[shell_no].satVtkVerts.InsertNextCell(1)
            self.shell_inactive_actors[shell_no].satVtkVerts.InsertCellPoint(
                self.shell_inactive_actors[shell_no].satPointIDs[i]
            )

        # convert points into poly data
        # (because that's what they do in the vtk examples)
        self.shell_inactive_actors[shell_no].satPolyData = vtk.vtkPolyData()
        self.shell_inactive_actors[shell_no].satPolyData.SetPoints(
            self.shell_inactive_actors[shell_no].satVtkPts
        )
        self.shell_inactive_actors[shell_no].satPolyData.SetVerts(
            self.shell_inactive_actors[shell_no].satVtkVerts
        )

        # create mapper object and connect to the poly data
        self.shell_inactive_actors[shell_no].satsMapper = vtk.vtkPolyDataMapper()
        self.shell_inactive_actors[shell_no].satsMapper.SetInputData(
            self.shell_inactive_actors[shell_no].satPolyData
        )

        # create actor, and connect to the mapper
        # (again, its just what you do to make a vtk render pipeline)
        self.shell_inactive_actors[shell_no].inactiveSatsActor = vtk.vtkActor()
        self.shell_inactive_actors[shell_no].inactiveSatsActor.SetMapper(
            self.shell_inactive_actors[shell_no].satsMapper
        )

        # edit appearance of satellites
        self.shell_inactive_actors[shell_no].inactiveSatsActor.GetProperty().SetOpacity(
            SAT_INACTIVE_OPACITY
        )
        self.shell_inactive_actors[shell_no].inactiveSatsActor.GetProperty().SetColor(
            self.sat_colors[shell_no]
        )
        self.shell_inactive_actors[
            shell_no
        ].inactiveSatsActor.GetProperty().SetPointSize(SAT_POINT_SIZE)

    def makeLinkActors(self, shell_no: int, shell_total_satellites: int) -> None:
        """
        generate the lines to represent links

        source:
        https://vtk.org/Wiki/VTK/Examples/Python/GeometricObjects/Display/PolyLine

        :param shell_no: index of this shell
        :param shell_total_satellites: number of satellites in the shell
        """

        # build a vtkPoints object from array
        self.isl_actors[shell_no].linkPoints = vtk.vtkPoints()
        self.isl_actors[shell_no].linkPoints.SetNumberOfPoints(shell_total_satellites)

        for i in range(len(self.sat_positions[shell_no])):
            self.isl_actors[shell_no].linkPoints.SetPoint(
                i,
                self.sat_positions[shell_no][i]["x"],
                self.sat_positions[shell_no][i]["y"],
                self.sat_positions[shell_no][i]["z"],
            )

        # build a cell array to represent connectivity
        self.isl_actors[shell_no].islLinkLines = vtk.vtkCellArray()
        for i in range(len(self.links[shell_no])):
            e1 = self.links[shell_no][i]["node_1"]
            e2 = self.links[shell_no][i]["node_2"]
            # must translate link endpoints to point names
            self.isl_actors[shell_no].islLinkLines.InsertNextCell(2)
            self.isl_actors[shell_no].islLinkLines.InsertCellPoint(e1)
            self.isl_actors[shell_no].islLinkLines.InsertCellPoint(e2)

        self.isl_actors[
            shell_no
        ].pathLinkLines = vtk.vtkCellArray()  # init, but do not fill this one

        # #

        self.isl_actors[shell_no].islPolyData = vtk.vtkPolyData()
        self.isl_actors[shell_no].islPolyData.SetPoints(
            self.isl_actors[shell_no].linkPoints
        )
        self.isl_actors[shell_no].islPolyData.SetLines(
            self.isl_actors[shell_no].islLinkLines
        )

        # #

        self.isl_actors[shell_no].islMapper = vtk.vtkPolyDataMapper()
        self.isl_actors[shell_no].islMapper.SetInputData(
            self.isl_actors[shell_no].islPolyData
        )

        # #

        self.isl_actors[shell_no].islActor = vtk.vtkActor()
        self.isl_actors[shell_no].islActor.SetMapper(
            self.isl_actors[shell_no].islMapper
        )

        # #

        self.isl_actors[shell_no].islActor.GetProperty().SetOpacity(ISL_LINK_OPACITY)
        self.isl_actors[shell_no].islActor.GetProperty().SetColor(
            self.isl_colors[shell_no]
        )
        self.isl_actors[shell_no].islActor.GetProperty().SetLineWidth(ISL_LINE_WIDTH)

        # #

    def makeGstActor(self, gst_num: int) -> None:
        """
        generate the point cloud to represent ground stations

        :param gst_num: number of ground stations
        """

        # declare a points & cell array to hold position data
        self.gst_actor.gstVtkPts = vtk.vtkPoints()
        self.gst_actor.gstVtkVerts = vtk.vtkCellArray()

        # init a array for IDs
        self.gst_actor.gstPointIDs = [None] * gst_num

        # initialize all the positions
        for i in range(len(self.gst_positions)):
            self.gst_actor.gstPointIDs[i] = self.gst_actor.gstVtkPts.InsertNextPoint(
                self.gst_positions[i]["x"],
                self.gst_positions[i]["y"],
                self.gst_positions[i]["z"],
            )

            self.gst_actor.gstVtkVerts.InsertNextCell(1)
            self.gst_actor.gstVtkVerts.InsertCellPoint(self.gst_actor.gstPointIDs[i])

        # convert points into poly data
        # (because that's what they do in the vtk examples)
        self.gst_actor.gstPolyData = vtk.vtkPolyData()
        self.gst_actor.gstPolyData.SetPoints(self.gst_actor.gstVtkPts)
        self.gst_actor.gstPolyData.SetVerts(self.gst_actor.gstVtkVerts)

        # create mapper object and connect to the poly data
        self.gst_actor.gstsMapper = vtk.vtkPolyDataMapper()
        self.gst_actor.gstsMapper.SetInputData(self.gst_actor.gstPolyData)

        # create actor, and connect to the mapper
        # (again, its just what you do to make a vtk render pipeline)
        self.gst_actor.gstsActor = vtk.vtkActor()
        self.gst_actor.gstsActor.SetMapper(self.gst_actor.gstsMapper)

        # edit appearance of satellites
        self.gst_actor.gstsActor.GetProperty().SetOpacity(GST_OPACITY)
        self.gst_actor.gstsActor.GetProperty().SetColor(GST_COLOR)
        self.gst_actor.gstsActor.GetProperty().SetPointSize(GST_POINT_SIZE)

        # #

    # make this for all shells as well?
    def makeGstLinkActors(self, gst_num: int) -> None:
        """
        generate the links to represent ground stations links

        :param gst_num: number of ground stations
        """

        # build a vtkPoints object from array
        self.gst_link_actor.gstLinkPoints = vtk.vtkPoints()
        self.gst_link_actor.gstLinkPoints.SetNumberOfPoints(
            gst_num + sum(self.shell_sats)
        )

        # add gsts
        for i in range(self.gst_num):
            x = self.gst_positions[i]["x"]
            y = self.gst_positions[i]["y"]
            z = self.gst_positions[i]["z"]
            self.gst_link_actor.gstLinkPoints.SetPoint(i, x, y, z)

        # add all satellites?
        num_points = self.gst_num

        for s in range(self.num_shells):
            for i in range(self.shell_sats[s]):
                x = self.sat_positions[s][i]["x"]
                y = self.sat_positions[s][i]["y"]
                z = self.sat_positions[s][i]["z"]
                self.gst_link_actor.gstLinkPoints.SetPoint(num_points, x, y, z)
                num_points += 1

        # build a cell array to represent connectivity
        self.gst_link_actor.gstLinkLines = vtk.vtkCellArray()

        offset = self.gst_num

        for s in range(self.num_shells):
            for i in range(len(self.gst_links[s])):
                e1 = self.gst_links[s][i]["gst"] * -1 - 1

                e2 = self.gst_links[s][i]["sat"] + offset

                # must translate link endpoints to point names
                self.gst_link_actor.gstLinkLines.InsertNextCell(2)
                self.gst_link_actor.gstLinkLines.InsertCellPoint(e1)
                self.gst_link_actor.gstLinkLines.InsertCellPoint(e2)

            offset += self.shell_sats[s]

        # #

        self.gst_link_actor.gstLinkPolyData = vtk.vtkPolyData()
        self.gst_link_actor.gstLinkPolyData.SetPoints(self.gst_link_actor.gstLinkPoints)
        self.gst_link_actor.gstLinkPolyData.SetLines(self.gst_link_actor.gstLinkLines)

        # #

        self.gst_link_actor.gstLinkMapper = vtk.vtkPolyDataMapper()
        self.gst_link_actor.gstLinkMapper.SetInputData(
            self.gst_link_actor.gstLinkPolyData
        )

        # #

        self.gst_link_actor.gstLinkActor = vtk.vtkActor()
        self.gst_link_actor.gstLinkActor.SetMapper(self.gst_link_actor.gstLinkMapper)

        # #

        self.gst_link_actor.gstLinkActor.GetProperty().SetOpacity(GST_LINK_OPACITY)
        self.gst_link_actor.gstLinkActor.GetProperty().SetColor(GST_LINK_COLOR)
        self.gst_link_actor.gstLinkActor.GetProperty().SetLineWidth(GST_LINE_WIDTH)

        # #

    def makeEarthActor(self, earth_radius: int) -> None:
        """
        generate the earth sphere, and the landmass outline

        :param earth_radius: radius of the earth in meters
        """

        self.earthRadius = earth_radius

        # Create earth map
        # a point cloud that outlines all the earths landmass
        self.earthSource = vtk.vtkEarthSource()
        # draws as an outline of landmass, rather than fill it in
        # self.earthSource.OutlineOn()

        # want this to be slightly larger than the sphere it sits on
        # so that it is not occluded by the sphere
        self.earthSource.SetRadius(self.earthRadius * 1.001)

        # controles the resolution of surface data (1 = full resolution)
        self.earthSource.SetOnRatio(1)

        # Create a mapper
        self.earthMapper = vtk.vtkPolyDataMapper()
        self.earthMapper.SetInputConnection(self.earthSource.GetOutputPort())

        # Create an actor
        self.earthActor = vtk.vtkActor()
        self.earthActor.SetMapper(self.earthMapper)

        # set color
        self.earthActor.GetProperty().SetColor(LANDMASS_OUTLINE_COLOR)
        self.earthActor.GetProperty().SetOpacity(EARTH_LAND_OPACITY)

        # make sphere data
        num_pts = EARTH_SPHERE_POINTS
        indices = np.arange(0, num_pts, dtype=float) + 0.5
        phi = np.arccos(1 - 2 * indices / num_pts)
        theta = np.pi * (1 + 5**0.5) * indices
        x = np.cos(theta) * np.sin(phi) * self.earthRadius
        y = np.sin(theta) * np.sin(phi) * self.earthRadius
        z = np.cos(phi) * self.earthRadius

        # x,y,z is coordination of evenly distributed sphere
        # I will try to make poly data use this x,y,z
        points = vtk.vtkPoints()
        for i in range(len(x)):
            points.InsertNextPoint(x[i], y[i], z[i])

        poly = vtk.vtkPolyData()
        poly.SetPoints(points)

        # To create surface of a sphere we need to use Delaunay triangulation
        d3D = vtk.vtkDelaunay3D()
        d3D.SetInputData(poly)  # This generates a 3D mesh

        # We need to extract the surface from the 3D mesh
        dss = vtk.vtkDataSetSurfaceFilter()
        dss.SetInputConnection(d3D.GetOutputPort())
        dss.Update()

        # Now we have our final polydata
        spherePoly = dss.GetOutput()

        # Create a mapper
        sphereMapper = vtk.vtkPolyDataMapper()
        sphereMapper.SetInputData(spherePoly)

        # Create an actor
        self.sphereActor = vtk.vtkActor()
        self.sphereActor.SetMapper(sphereMapper)

        # set color
        self.sphereActor.GetProperty().SetColor(EARTH_BASE_COLOR)
        self.sphereActor.GetProperty().SetOpacity(EARTH_OPACITY)

    def controlThreadHandler(self) -> None:
        """
        这个函数处理与星座的所有通信
        """
        command_buffer = {}  # 缓存各种命令请求的响应
        consecutive_errors = 0  # 连续错误计数
        max_consecutive_errors = 5  # 最大连续错误次数
        error_cooldown = 0  # 错误冷却时间

        while True:
            # 如果有错误冷却时间，等待冷却结束
            if error_cooldown > 0:
                time.sleep(0.5)
                error_cooldown -= 1
                continue
                
            if not self.conn.poll(0.01):
                # 减少CPU使用
                time.sleep(0.01)
                consecutive_errors = 0  # 重置连续错误计数
                continue

            try:
                try:
                    received_data = self.conn.recv()
                    consecutive_errors = 0  # 成功接收数据，重置错误计数
                except (_pickle.UnpicklingError, EOFError) as e:
                    consecutive_errors += 1
                    print(f"接收数据时出错 ({consecutive_errors}/{max_consecutive_errors}): {e}")
                    
                    # 如果连续错误次数过多，设置冷却时间
                    if consecutive_errors >= max_consecutive_errors:
                        print("连续错误过多，暂停接收数据一段时间")
                        error_cooldown = 10  # 设置冷却时间
                        consecutive_errors = 0  # 重置错误计数
                    
                    # 短暂休眠后继续尝试
                    time.sleep(0.5)
                    continue

                if not isinstance(received_data, dict):
                    print(f"接收到非字典数据: {type(received_data)}")
                    continue

                command = received_data.get("type", "unknown")

                if command == "time":
                    # 更新模拟时间
                    self.current_simulation_time = received_data["time"]

                    # 更新仿真时长和时间偏移
                    if "duration" in received_data:
                        self.simulation_duration = received_data["duration"]
                    if "offset" in received_data:
                        self.simulation_offset = received_data["offset"]

                elif command == "config":
                    # 处理配置信息
                    if "duration" in received_data:
                        self.simulation_duration = received_data["duration"]
                    if "offset" in received_data:
                        self.simulation_offset = received_data["offset"]

                elif command == "shell":
                    # 更新壳层数据
                    try:
                        shell = received_data["shell"]

                        if 0 <= shell < self.num_shells:
                            self.sat_positions[shell] = received_data["sat_positions"]
                            self.links[shell] = received_data["links"]

                            # 只在第一个壳层中更新地面站信息
                            if shell == 0 and "gst_positions" in received_data:
                                self.gst_positions = received_data["gst_positions"]
                                if "gst_links" in received_data:
                                    self.gst_links[shell] = received_data["gst_links"]
                    except KeyError as e:
                        print(f"处理shell数据时缺少键: {e}")
                    except Exception as e:
                        print(f"处理shell数据时出错: {e}")

                elif command == "route":
                    # 立即处理路由路径响应
                    try:
                        # 检查是否处于重置状态，如果是则忽略响应
                        if hasattr(self, 'route_reset') and self.route_reset:
                            # 不打印消息，避免重复显示
                            # 清除请求挂起标志，确保不会卡住
                            self.route_request_pending = False
                            # 清除当前路径显示，确保重置状态下不显示任何路径
                            if hasattr(self, 'route_path_actor') and self.route_path_actor:
                                self.renderer.RemoveActor(self.route_path_actor)
                                self.route_path_actor = None
                            # 清除箭头
                            if hasattr(self, 'route_arrows_actors'):
                                for arrow_actor in self.route_arrows_actors:
                                    if arrow_actor:
                                        self.renderer.RemoveActor(arrow_actor)
                                self.route_arrows_actors = []
                            # 清除当前路径节点，防止重置后仍然显示路径
                            if hasattr(self, 'current_path_nodes'):
                                self.current_path_nodes = []
                            # 确保last_route_update设置为一个足够大的值，防止在重置后立即发送请求
                            if hasattr(self, 'last_route_update'):
                                self.last_route_update = float('inf')
                            continue
                            
                        if "path" in received_data:
                            # 确保路径中的所有元素都是整数
                            try:
                                path_nodes = [int(node) for node in received_data["path"]]
                                print(f"接收到路由路径，共 {len(path_nodes)} 个节点")

                                # 更新当前路径节点
                                self.current_path_nodes = path_nodes
                                # 更新路由更新时间戳，防止updateRoutePath立即再次请求
                                self.last_route_update = self.current_simulation_time
                                # 清除请求挂起标志
                                self.route_request_pending = False
                            except (ValueError, TypeError) as e:
                                print(f"处理路径节点时出错: {e}")
                                # 如果无法转换为整数，尝试使用原始数据
                                if isinstance(received_data["path"], list):
                                    self.current_path_nodes = received_data["path"]
                                    self.last_route_update = self.current_simulation_time
                    except Exception as e:
                        print(f"处理路由响应时出错: {e}")
                        import traceback
                        traceback.print_exc()
            except EOFError:
                print("Connection closed by constellation process")
                break
            except (ConnectionError, BrokenPipeError) as e:
                print(f"Connection error: {e}")
                # 尝试短暂休眠后继续
                time.sleep(1)
                continue
            except _pickle.UnpicklingError as e:
                print(f"数据反序列化错误: {e}")
                # 对于序列化错误，记录但继续运行
                time.sleep(0.5)
                continue
            except Exception as e:
                print(f"Error in control thread: {e}")
                import traceback
                traceback.print_exc()
                # 对于未知错误，记录但继续运行
                time.sleep(0.5)
                continue

    def displayRoutePath(self, path_nodes):
        """显示路由路径
        
        :param path_nodes: 路径节点列表，包含从源到目标的所有节点全局索引
        """
        try:
            if not path_nodes or len(path_nodes) < 2:
                print("路径节点不足，无法显示路径")
                return
                
            # 保存当前路径节点，用于后续更新
            self.current_path_nodes = path_nodes
            
            # 限制路径节点数量，防止过长路径导致性能问题
            max_path_nodes = 20  # 最大路径节点数
            if len(path_nodes) > max_path_nodes:
                # print(f"路径节点过多 ({len(path_nodes)}), 限制为 {max_path_nodes} 个节点")
                # 保留起点、终点和中间的一些关键节点
                step = len(path_nodes) // (max_path_nodes - 2)
                selected_nodes = [path_nodes[0]]  # 起点
                selected_nodes.extend(path_nodes[step::step][:max_path_nodes-2])  # 中间节点
                if path_nodes[-1] not in selected_nodes:
                    selected_nodes.append(path_nodes[-1])  # 终点
                path_nodes = selected_nodes
                # print(f"简化后的路径节点: {path_nodes}")
            
            # 清除现有路径
            if self.route_path_actor:
                self.renderer.RemoveActor(self.route_path_actor)
                self.route_path_actor = None
                
            # 清除现有箭头
            for arrow_actor in self.route_arrows_actors:
                if arrow_actor:
                    self.renderer.RemoveActor(arrow_actor)
            self.route_arrows_actors = []
            
            # 创建路径点集合
            path_points = vtk.vtkPoints()
            path_lines = vtk.vtkCellArray()
            
            # 获取所有节点的位置
            total_sats = sum(self.shell_sats)
            node_positions = []
            
            for node_idx in path_nodes:
                try:
                    node_idx = int(node_idx)  # 确保节点索引是整数
                    if node_idx < total_sats:  # 卫星
                        # 确定卫星所在的shell和在shell中的索引
                        shell_idx = 0
                        sat_idx = node_idx
                        for i, shell_sats in enumerate(self.shell_sats):
                            if sat_idx >= shell_sats:
                                sat_idx -= shell_sats
                            else:
                                shell_idx = i
                                break
                                
                        # 获取卫星位置
                        if shell_idx < len(self.sat_positions) and sat_idx < len(self.sat_positions[shell_idx]):
                            pos = self.sat_positions[shell_idx][sat_idx]
                            node_positions.append((pos['x'], pos['y'], pos['z']))
                        else:
                            print(f"无效的卫星索引: shell={shell_idx}, sat={sat_idx}")
                            continue
                    else:  # 地面站
                        gst_idx = node_idx - total_sats
                        if gst_idx < len(self.gst_positions):
                            pos = self.gst_positions[gst_idx]
                            node_positions.append((pos['x'], pos['y'], pos['z']))
                        else:
                            print(f"无效的地面站索引: {gst_idx}")
                            continue
                except Exception as e:
                    print(f"处理路径节点 {node_idx} 时出错: {e}")
                    continue
            
            # 如果没有有效的节点位置，则返回
            if len(node_positions) < 2:
                print("没有足够的有效节点位置来显示路径")
                return
            
            # 添加路径点和线段
            for i, pos in enumerate(node_positions):
                path_points.InsertNextPoint(pos[0], pos[1], pos[2])
                
                # 添加线段（除了最后一个点）
                if i < len(node_positions) - 1:
                    path_lines.InsertNextCell(2)
                    path_lines.InsertCellPoint(i)
                    path_lines.InsertCellPoint(i + 1)
                    
                    # 移除了箭头渲染代码，只保留路径线段
            
            # 创建路径的PolyData
            path_polydata = vtk.vtkPolyData()
            path_polydata.SetPoints(path_points)
            path_polydata.SetLines(path_lines)
            
            # 创建路径的映射器
            path_mapper = vtk.vtkPolyDataMapper()
            path_mapper.SetInputData(path_polydata)
            
            # 创建路径的演员
            self.route_path_actor = vtk.vtkActor()
            self.route_path_actor.SetMapper(path_mapper)
            self.route_path_actor.GetProperty().SetColor(ROUTE_PATH_COLOR)
            self.route_path_actor.GetProperty().SetOpacity(ROUTE_PATH_OPACITY)
            self.route_path_actor.GetProperty().SetLineWidth(ROUTE_PATH_WIDTH)
            
            # 添加到渲染器
            self.renderer.AddActor(self.route_path_actor)
        except Exception as e:
            print(f"显示路由路径时出错: {e}")
            import traceback
            traceback.print_exc()
        
        # 更新渲染
        self.renderWindow.Render()
        
        # print(f"显示路径: {path_nodes}")
