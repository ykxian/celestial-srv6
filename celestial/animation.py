"""Animation of the constellation"""

import vtk
import threading
import seaborn as sns
from multiprocessing.connection import Connection as MultiprocessingConnection
import typing
import time
import pickle
import math

from celestial.animation_constants import *
from celestial.animation_constellation import AnimationConstellation
from celestial.animation_ui import AnimationUI
from celestial.animation_actors import AnimationActors

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
        self.srv6_route_path_actor = None  # SRv6路由路径演员对象
        self.srv6_route_arrows_actors = []  # SRv6路由路径箭头演员对象列表
        self.current_path_nodes = None   # 当前路径节点
        self.last_route_update = 0       # 上次路由更新的时间
        self.route_request_pending = False  # 路由请求挂起标志
        self.route_request_time = 0      # 路由请求发送时间，用于超时检测

        self.initialized = True  # 初始化完成标志

        # 创建actors管理器（提前创建，以便后续使用）
        self.actors = AnimationActors(None)  # 暂时传入None，在makeRenderWindow中会重新设置

        # 准备颜色配置
        self.sat_colors = sns.color_palette(n_colors=self.num_shells)
        self.isl_colors = sns.color_palette(n_colors=self.num_shells, desat=0.5)
        
        # 移除不存在的常量引用
        # self.sat_inactive_color = INACTIVE_SAT_COLOR
        
        # 设置链路显示标志
        self.draw_links = draw_links
        
        # 设置地面站数量
        self.gst_num = len(self.gst_positions)

        self.lock = threading.Lock()

        # 先启动控制线程，确保能接收消息
        self.controlThread = threading.Thread(target=self.controlThreadHandler)
        self.controlThread.start()
        print("Animation: 控制线程已启动，准备接收消息")
        
        # 等待一小段时间确保控制线程已经开始运行
        time.sleep(0.5)


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

        # 计算地球旋转角度
        steps_to_animate = self.current_simulation_time - self.last_animate
        self.last_animate = self.current_simulation_time
        rotation_per_time_step = 360.0 / (SECONDS_PER_DAY) * steps_to_animate
        
        # 旋转地球（通过actors管理器访问地球演员）
        if hasattr(self.actors, 'earthActor') and self.actors.earthActor:
            self.actors.earthActor.RotateZ(rotation_per_time_step)
        if hasattr(self.actors, 'sphereActor') and self.actors.sphereActor:
            self.actors.sphereActor.RotateZ(rotation_per_time_step)

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

        # 更新卫星位置
        for s in range(self.num_shells):
            # 创建卫星是否在边界框内的标志列表
            in_bbox = [self.sat_positions[s][i]["in_bbox"] for i in range(self.shell_sats[s])]
            
            # 使用actors管理器更新卫星位置
            self.actors.updateSatPositions(s, self.sat_positions[s], in_bbox)
            
            # 如果启用了链路显示，更新链路
            if self.draw_links:
                self.actors.updateLinks(s, self.links[s], self.sat_positions[s])
                
        # 更新地面站链路（所有壳层一起更新）
        if self.draw_links:
            self.actors.updateGstLinks(self.gst_links, self.gst_positions, self.sat_positions)

        # 更新全局信息显示 - 传递已计算的活跃卫星数和总链路数，避免重复计算
        self.ui.updateInfoText(active_satellites=self.active_satellites, total_links=self.total_links_count)

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

        # 更新渲染窗口
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
                        # 出错时清除路径显示，防止显示错误的路径
                        self.clearRoutePath()
            elif hasattr(self, 'route_path_actor') and self.route_path_actor is None:
                # 如果没有活动路径但仍有路径显示，清除它
                self.clearRoutePath()
        except Exception as e:
            print(f"更新路由路径时出现未捕获的错误: {e}")
            # 出现未捕获的错误时，尝试清除路径显示
            try:
                self.clearRoutePath()
            except Exception:
                pass
            
    def _calculateSatelliteIndex(self, shell: int, sat_id: int) -> int:
        """
        计算卫星在整个网络中的索引
        :param shell: 壳层编号
        :param sat_id: 卫星ID
        :return: 卫星在整个网络中的索引
        """
        # 计算之前所有壳层的卫星总数
        total = 0
        for s in range(shell):
            total += self.shell_sats[s]
        # 加上当前壳层中的卫星ID
        return total + sat_id

    def showRoutePath(self, source_type: str, source_shell: int, source_id: int,
                     target_type: str, target_shell: int, target_id: int) -> None:
        """显示两个节点之间的路由路径，不考虑节点是否活跃"""
        # 清除现有路径
        if self.route_path_actor:
            self.renderer.RemoveActor(self.route_path_actor)
            self.route_path_actor = None

        # 清除现有箭头
        if hasattr(self, 'route_arrows_actors'):
            for arrow_actor in self.route_arrows_actors:
                if arrow_actor:
                    self.renderer.RemoveActor(arrow_actor)
            self.route_arrows_actors = []
        else:
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
            # 对于卫星，source_shell是从0开始的索引，但在UI显示和IP计算中shell_identifier是从1开始的
            # 所以在右键点击事件中，我们需要使用shell索引(0-based)而不是shell标识符(1-based)
            offset = 0
            for s in range(source_shell):
                offset += self.shell_sats[s]
            source_index = offset + source_id
        else:  # groundstation
            source_index = sum(self.shell_sats) + source_id

        # 计算目标节点全局索引
        if target_type == "satellite":
            # 同样，对于卫星，target_shell是从0开始的索引
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
                "source": self.route_source_index,
                "target": self.route_target_index
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
            if hasattr(self, 'route_arrows_actors'):
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
                            # 优先从地面站演员获取最新位置
                            if self.actors.gst_actor and self.actors.gst_actor.satVtkPts:
                                gst_world_pos = [0, 0, 0]  # 初始化坐标
                                self.actors.gst_actor.satVtkPts.GetPoint(gst_idx, gst_world_pos)
                                node_positions.append((gst_world_pos[0], gst_world_pos[1], gst_world_pos[2]))
                            else:
                                # 如果无法从演员获取，则使用存储的位置（可能不是最新的）
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
        
        # 更新渲染
        self.renderWindow.Render()
        
        # print(f"显示路径: {path_nodes}")

    def makeInfoTextActors(self) -> None:
        """Create text actors for displaying global information"""
        # 此方法已移至 animation_ui.py
        if hasattr(self, 'ui'):
            self.ui.makeInfoTextActors()
            
    def makeProgressBar(self) -> None:
        """创建进度条演员"""
        # 此方法已移至 animation_ui.py
        if hasattr(self, 'ui'):
            self.ui.makeProgressBar()
            
    def updateProgressBar(self, progress: float) -> None:
        """更新进度条显示"""
        # 此方法已移至 animation_ui.py
        if hasattr(self, 'ui'):
            self.ui.updateProgressBar(progress)
            
    def makeInfoPanel(self) -> None:
        """创建信息面板（初始隐藏）"""
        # 此方法已移至 animation_ui.py
        if hasattr(self, 'ui'):
            self.ui.makeInfoPanel()
            
    def setupPicker(self) -> None:
        """设置点击拾取器"""
        # 此方法已移至 animation_ui.py
        if hasattr(self, 'ui'):
            self.ui.setupPicker()
            
    def handleKeyPress(self, obj: typing.Any, event: typing.Any) -> None:
        """处理键盘按键事件"""
        # 此方法已移至 animation_ui.py
        if hasattr(self, 'ui'):
            self.ui.handleKeyPress(obj, event)
            
    def handleClick(self, obj: typing.Any, event: typing.Any) -> None:
        """处理鼠标点击事件"""
        # 此方法已移至 animation_ui.py
        if hasattr(self, 'ui'):
            self.ui.handleClick(obj, event)
            
    def handleRightClick(self, obj: typing.Any, event: typing.Any) -> None:
        """处理鼠标右键点击事件"""
        # 此方法已移至 animation_ui.py
        if hasattr(self, 'ui'):
            self.ui.handleRightClick(obj, event)
            
    def updateSatelliteInfoPanel(self, shell: int, sat_id: int) -> None:
        """更新卫星信息面板"""
        # 此方法已移至 animation_ui.py
        if hasattr(self, 'ui'):
            self.ui.updateSatelliteInfoPanel(shell, sat_id)
            
    def updateGroundStationInfoPanel(self, gst_id: int) -> None:
        """更新地面站信息面板"""
        # 此方法已移至 animation_ui.py
        if hasattr(self, 'ui'):
            self.ui.updateGroundStationInfoPanel(gst_id)
            
    def hideInfoPanel(self) -> None:
        """隐藏信息面板"""
        # 此方法已移至 animation_ui.py
        if hasattr(self, 'ui'):
            self.ui.hideInfoPanel()

    def makeRenderWindow(self) -> None:
        """
        Makes a render window object using vtk.

        This should not be called until all the actors are created.
        """
        # 创建渲染器
        self.renderer = vtk.vtkRenderer()
        self.renderer.SetBackground(BACKGROUND_COLOR)

        # 创建渲染窗口
        self.renderWindow = vtk.vtkRenderWindow()
        self.renderWindow.AddRenderer(self.renderer)
        self.renderWindow.SetSize(2048, 2048)  # 直接使用数值，与原始代码保持一致
        self.renderWindow.SetWindowName("Celestial Animation")

        # 创建交互器
        self.interactor = vtk.vtkRenderWindowInteractor()
        self.interactor.SetRenderWindow(self.renderWindow)

        # 创建UI管理器
        self.ui = AnimationUI(self)
        
        # 重新设置actors管理器
        self.actors.renderer = self.renderer
        
        # 初始化地球
        self.actors.makeEarthActor(EARTH_RADIUS_M)
        
        # 准备卫星和链路颜色
        self.sat_colors = sns.color_palette(n_colors=self.num_shells)
        self.isl_colors = sns.color_palette(n_colors=self.num_shells, desat=0.5)
        
        # 初始化卫星和链路演员
        for shell in range(self.num_shells):
            self.actors.makeSatsActor(shell, self.shell_sats[shell], self.sat_positions, self.sat_colors)
            self.actors.makeInactiveSatsActor(shell, self.shell_sats[shell])
            # 设置非活跃卫星的颜色（与活跃卫星相同）
            self.actors.shell_inactive_actors[shell].satsActor.GetProperty().SetColor(self.sat_colors[shell])
            if self.draw_links:
                self.actors.makeLinkActors(shell, self.shell_sats[shell], self.isl_colors[shell], self.sat_positions[shell], self.links[shell])
                
        # 初始化地面站和链路演员
        if self.gst_num > 0:
            self.actors.makeGstActor(self.gst_num, self.gst_positions)
            if self.draw_links:
                self.actors.makeGstLinkActor(self.gst_num, self.shell_sats, self.sat_positions, self.gst_positions, self.gst_links)

        # 创建UI组件（必须在渲染器设置后创建）
        self.ui.makeInfoTextActors()  # 创建全局信息文本
        
        # 设置交互器样式
        style = vtk.vtkInteractorStyleTrackballCamera()
        self.interactor.SetInteractorStyle(style)
        
        # 设置相机初始位置（解决初始缩过大问题）
        camera = self.renderer.GetActiveCamera()
        camera.SetPosition(0, 0, EARTH_RADIUS_M * 4)  # 设置相机位置在地球半径的4倍处
        camera.SetFocalPoint(0, 0, 0)  # 焦点设置在原点
        camera.SetViewUp(0, 1, 0)  # 设置视图向上方向
        self.renderer.ResetCamera()  # 重置相机以确保所有对象都在视图中

        # 添加动画回调
        self.interactor.AddObserver("TimerEvent", self._updateAnimation)
        self.timerId = self.interactor.CreateRepeatingTimer(1000 // self.frequency)

        # 启动渲染窗口
        self.renderWindow.Render()
        self.interactor.Start()

    def controlThreadHandler(self) -> None:
        """
        这个函数处理与星座的所有通信
        """
        command_buffer = {}  # 缓存各种命令请求的响应
        consecutive_errors = 0  # 连续错误计数
        max_consecutive_errors = 5  # 最大连续错误次数
        error_cooldown = 0  # 错误冷却时间

        print("Animation: controlThreadHandler已启动，准备接收消息")

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
                # 检查是否有数据可读
                if not self.conn.poll(0.1):  # 增加超时时间，确保有足够时间接收数据
                    continue
                    
                received_data = self.conn.recv()
                # 立即输出接收到的消息类型，帮助调试
                if isinstance(received_data, dict):
                    msg_type = received_data.get("type", "unknown")
                    print(f"Animation: 接收到消息类型: {msg_type}, 连接对象ID: {id(self.conn)}")
                    
                    # 处理测试连接消息
                    if msg_type == "test_connection" or msg_type == "parent_test":
                        print(f"Animation: 接收到测试连接消息: {received_data}")
                        try:
                            # 发送确认响应
                            response = {"type": f"{msg_type}_response", "message": "确认收到测试消息", "timestamp": time.time()}
                            print(f"Animation: 发送测试连接响应: {response}")
                            self.conn.send(response)
                            print("Animation: 测试连接响应发送成功")
                        except Exception as e:
                            print(f"Animation: 发送测试连接响应失败: {e}")
                            import traceback
                            print(traceback.format_exc())
                        # 不再使用continue，允许继续处理其他消息类型
                    
                    # 处理SRv6路由测试消息
                    elif msg_type == "srv6_route_test":
                        # 处理SRv6路由服务器的测试消息
                        print(f"接收到SRv6路由服务器测试消息: {received_data}")
                        print("SRv6路由服务器连接测试成功")
                        # 发送确认响应，确保双向通信正常
                        try:
                            response_msg = {"type": "srv6_route_test_response", "message": "Animation确认收到测试消息", "timestamp": time.time()}
                            print(f"发送测试响应消息: {response_msg}")
                            print(f"使用的连接对象ID: {id(self.conn)}")
                            self.conn.send(response_msg)
                            print("已成功发送测试响应消息")
                        except Exception as e:
                            print(f"发送测试响应消息失败: {e}")
                            import traceback
                            print(traceback.format_exc())
                        # 强制更新渲染窗口，确保测试消息也能触发界面更新
                        if hasattr(self, 'renderWindow') and self.renderWindow:
                            self.renderWindow.Render()
                            print("已强制更新渲染窗口 - 测试消息")
                
                # 消息处理逻辑应该在try块内
                if not isinstance(received_data, dict):
                    print(f"接收到非字典数据: {type(received_data)}")
                    continue

                command = received_data.get("type", "unknown")
                print(f"Animation: 处理消息类型: {command}")

                # SRv6路由测试消息已在上面的if语句块中处理
                                        
                # 处理SRv6路由数据
                if command == "srv6_route":
                    try:
                        print(f"接收到SRv6路由数据: {received_data}")
                        print(f"当前shell_sats配置: {self.shell_sats}")
                        
                        # 提取源节点和目标节点信息
                        source_info = received_data.get("source", {})
                        target_info = received_data.get("target", {})
                        segments = received_data.get("segments", [])
                        
                        # 计算源节点和目标节点的全局索引
                        source_shell = source_info.get("shell", 0)
                        source_id = source_info.get("id", 0)
                        target_shell = target_info.get("shell", 0)
                        target_id = target_info.get("id", 0)
                        
                        print(f"源节点信息: shell={source_shell}, id={source_id}")
                        print(f"目标节点信息: shell={target_shell}, id={target_id}")
                        
                        # 计算全局索引
                        source_index = self._calculate_node_global_index(source_shell, source_id)
                        target_index = self._calculate_node_global_index(target_shell, target_id)
                        
                        print(f"源节点全局索引: {source_index}")
                        print(f"目标节点全局索引: {target_index}")
                        
                        # 构建路径节点列表
                        path_nodes = [source_index]
                        
                        # 添加中间节点
                        for i, segment in enumerate(segments):
                            seg_shell = segment.get("shell", 0)
                            seg_id = segment.get("id", 0)
                            print(f"中间节点{i+1}信息: shell={seg_shell}, id={seg_id}")
                            seg_index = self._calculate_node_global_index(seg_shell, seg_id)
                            print(f"中间节点{i+1}全局索引: {seg_index}")
                            path_nodes.append(seg_index)
                        
                        # 确保路径以目标节点结束
                        if path_nodes[-1] != target_index:
                            path_nodes.append(target_index)
                        
                        print(f"SRv6路由路径: {path_nodes}")
                        print(f"卫星总数: {sum(self.shell_sats)}, 地面站总数: {len(self.gst_positions) if hasattr(self, 'gst_positions') else 0}")
                        
                        # 检查路径节点是否有效
                        valid_path = True
                        for i, node_index in enumerate(path_nodes):
                            if node_index < 0:
                                print(f"错误: 路径节点{i+1}的索引{node_index}小于0")
                                valid_path = False
                                continue
                                
                            # 检查sat_positions和gst_positions是否已初始化
                            if not hasattr(self, 'sat_positions') or len(self.sat_positions) == 0:
                                print(f"错误: sat_positions未初始化或为空")
                                valid_path = False
                                break
                                
                            if not hasattr(self, 'gst_positions'):
                                print(f"错误: gst_positions未初始化")
                                valid_path = False
                                break
                                
                            # 计算卫星总数
                            total_sats = sum(self.shell_sats)
                            print(f"节点{i+1}索引={node_index}, 卫星总数={total_sats}")
                                
                            if node_index < total_sats:  # 卫星
                                # 计算卫星所在的壳层和ID
                                shell_no = 0
                                sat_id = node_index
                                accumulated = 0
                                
                                for s in range(self.num_shells):
                                    if sat_id < accumulated + self.shell_sats[s]:
                                        shell_no = s
                                        sat_id -= accumulated
                                        break
                                    accumulated += self.shell_sats[s]
                                
                                print(f"  节点{i+1}是卫星: shell={shell_no}, id={sat_id}, sat_positions长度={len(self.sat_positions)}")
                                
                                # 检查卫星位置是否存在
                                if shell_no >= len(self.sat_positions):
                                    print(f"错误: 路径节点{i+1}的卫星壳层不存在: shell={shell_no}, 可用壳层数={len(self.sat_positions)}")
                                    valid_path = False
                                    continue
                                    
                                if sat_id >= len(self.sat_positions[shell_no]):
                                    print(f"错误: 路径节点{i+1}的卫星ID超出范围: id={sat_id}, 壳层{shell_no}的卫星数量={len(self.sat_positions[shell_no])}")
                                    valid_path = False
                                    continue
                            else:  # 地面站
                                gst_id = node_index - total_sats
                                print(f"  节点{i+1}是地面站: id={gst_id}, 地面站总数={len(self.gst_positions)}")
                                
                                if gst_id >= len(self.gst_positions):
                                    print(f"错误: 路径节点{i+1}的地面站位置不存在: id={gst_id}, 地面站总数={len(self.gst_positions)}")
                                    valid_path = False
                                    continue
                        
                        
                        # 清除之前的SRv6路由路径
                        if hasattr(self, 'srv6_route_path_actor') and self.srv6_route_path_actor:
                            self.renderer.RemoveActor(self.srv6_route_path_actor)
                            self.srv6_route_path_actor = None
                            
                        # 清除之前的SRv6路由箭头
                        if hasattr(self, 'srv6_route_arrows_actors'):
                            for arrow_actor in self.srv6_route_arrows_actors:
                                if arrow_actor:
                                    self.renderer.RemoveActor(arrow_actor)
                            self.srv6_route_arrows_actors = []
                        
                        # 显示SRv6路由路径（使用蓝色）
                        if len(path_nodes) >= 2 and valid_path:
                            self.displaySRv6RoutePath(path_nodes)
                            print(f"已显示SRv6路由路径，共{len(path_nodes)}个节点")
                            # 强制更新渲染窗口
                            if hasattr(self, 'renderWindow') and self.renderWindow:
                                self.renderWindow.Render()
                                print("已强制更新渲染窗口")
                        else:
                            print(f"SRv6路径无法显示: 节点数={len(path_nodes)}, 路径有效={valid_path}")
                    except Exception as e:
                        import traceback
                        print(f"处理SRv6路由数据时出错: {e}")
                        traceback.print_exc()
                    # 处理完SRv6路由消息后继续处理其他消息类型
                    # 移除continue语句，允许处理其他类型的消息
                
                if command == "time":
                    # 更新模拟时间
                    self.current_simulation_time = received_data["time"]

                elif command == "config":
                    self.simulation_duration = received_data["duration"]
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
                            if hasattr(self, 'last_route_update'):
                                self.last_route_update = float('inf')
                            
                            # 重置状态下直接返回，不处理任何路由请求
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
            except EOFError:
                print("Connection closed by constellation process")
                break
            except (ConnectionError, BrokenPipeError) as e:
                print(f"Connection error: {e}")
                # 尝试短暂休眠后继续
                time.sleep(1)
                continue
            except pickle.UnpicklingError as e:
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

    def calculateIPv6(self, shell: int, node_id: int) -> str:
        """
        根据shell和node_id计算IPv6地址
        """
        # 直接调用ui对象的方法，避免循环引用
        if hasattr(self, 'ui'):
            return self.ui.calculateIPv6(shell, node_id)
        
    def calculateIPv4(self, shell: int, node_id: int) -> str:
        """
        根据shell和node_id计算IPv4地址
        """
        # 直接调用ui对象的方法，避免循环引用
        if hasattr(self, 'ui'):
            return self.ui.calculateIPv4(shell, node_id)
        
    def executeSSHCommand(self) -> None:
        """
        执行SSH命令，连接到选中的卫星或地面站
        """
        # 直接调用ui对象的方法，避免循环引用
        if hasattr(self, 'ui'):
            self.ui.executeSSHCommand()
            
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
        
    def _calculate_node_global_index(self, shell: int, node_id: int) -> int:
        """计算节点的全局索引
        
        :param shell: 节点所在的壳层（0表示地面站）
        :param node_id: 节点在壳层中的ID
        :return: 节点的全局索引
        """
        print(f"计算节点全局索引: shell={shell}, id={node_id}, shell_sats={self.shell_sats}")
        
        if shell == 0 and hasattr(self, 'gst_positions') and node_id < len(self.gst_positions):  # 地面站
            # 地面站的全局索引 = 所有卫星数量 + 地面站ID
            result = sum(self.shell_sats) + node_id
            print(f"地面站全局索引计算: sum(shell_sats)={sum(self.shell_sats)} + node_id={node_id} = {result}")
            return result
        else:  # 卫星
            # 检查shell值是否有效 - 注意：shell值从0开始，而不是从1开始
            if shell < 0 or shell >= len(self.shell_sats):
                print(f"警告: shell值超出范围: {shell}, 有效范围: 0-{len(self.shell_sats)-1}")
                # 返回一个默认值，避免方法没有返回值
                return 0
                
            # 计算之前所有壳层的卫星总数
            total = 0
            for s in range(shell):
                total += self.shell_sats[s]
                
            # 检查节点ID是否有效
            if node_id < 0 or (shell < len(self.shell_sats) and node_id >= self.shell_sats[shell]):
                print(f"警告: 节点ID超出范围: {node_id}, 壳层{shell}的有效范围: 0-{self.shell_sats[shell]-1}")
                # 返回一个默认值，避免方法没有返回值
                return total
                
            # 加上当前壳层中的卫星ID
            result = total + node_id
            print(f"卫星全局索引计算: 之前壳层总数={total} + 节点ID={node_id} = {result}")
            return result
            
    def displaySRv6RoutePath(self, path_nodes: list) -> None:
        """显示SRv6路由路径（使用蓝色）
        
        :param path_nodes: 路径节点列表
        """
        print(f"开始显示SRv6路由路径，节点列表: {path_nodes}")
        # 确保路径节点列表有效
        if not isinstance(path_nodes, list):
            print(f"错误: 路径节点不是列表类型: {type(path_nodes)}")
            return
        if not path_nodes or len(path_nodes) < 2:
            print("SRv6路径节点不足，无法显示路径")
            return
            
        print(f"开始构建SRv6路由路径，节点列表: {path_nodes}")
        print(f"当前卫星配置: shells={self.num_shells}, 每个shell的卫星数量={self.shell_sats}")
        print(f"卫星总数: {sum(self.shell_sats)}, 地面站总数: {len(self.gst_positions) if hasattr(self, 'gst_positions') else 0}")
        
        # 创建静态路径显示（不随用户交互变化）
        # 创建点集合
        points = vtk.vtkPoints()
        
        # 创建线段集合
        lines = vtk.vtkCellArray()
        
        # 添加所有节点的位置
        valid_points = 0
        for i, node_index in enumerate(path_nodes):
            print(f"处理路径节点{i+1}: 全局索引={node_index}")
            # 确定节点类型和位置
            if node_index < sum(self.shell_sats):  # 卫星
                # 计算卫星所在的壳层和ID
                shell_no = 0
                sat_id = node_index
                accumulated = 0
                
                for s in range(self.num_shells):
                    if sat_id < accumulated + self.shell_sats[s]:
                        shell_no = s
                        sat_id -= accumulated
                        break
                    accumulated += self.shell_sats[s]
                
                print(f"  节点{i+1}是卫星: shell={shell_no}, id={sat_id}")
                
                # 检查sat_positions是否已初始化
                if not hasattr(self, 'sat_positions') or len(self.sat_positions) == 0:
                    print(f"  错误: sat_positions未初始化或为空")
                    return
                
                # 获取卫星位置
                if shell_no < len(self.sat_positions) and sat_id < len(self.sat_positions[shell_no]):
                    pos = self.sat_positions[shell_no][sat_id]
                    print(f"  卫星位置: x={pos['x']}, y={pos['y']}, z={pos['z']}")
                    points.InsertNextPoint(pos["x"], pos["y"], pos["z"])
                    valid_points += 1
                else:
                    print(f"  错误: 无法获取卫星位置: shell={shell_no}, id={sat_id}")
                    print(f"  sat_positions长度: {len(self.sat_positions)}")
                    if shell_no < len(self.sat_positions):
                        print(f"  shell {shell_no}的卫星数量: {len(self.sat_positions[shell_no])}")
                    return
            else:  # 地面站
                gst_id = node_index - sum(self.shell_sats)
                print(f"  节点{i+1}是地面站: id={gst_id}")
                
                # 检查gst_positions是否已初始化
                if not hasattr(self, 'gst_positions') or len(self.gst_positions) == 0:
                    print(f"  错误: gst_positions未初始化或为空")
                    return
                
                if gst_id < len(self.gst_positions):
                    pos = self.gst_positions[gst_id]
                    print(f"  地面站位置: x={pos['x']}, y={pos['y']}, z={pos['z']}")
                    points.InsertNextPoint(pos["x"], pos["y"], pos["z"])
                    valid_points += 1
                else:
                    print(f"  错误: 无法获取地面站位置: id={gst_id}, 地面站总数={len(self.gst_positions)}")
                    return
        
        print(f"成功添加了{valid_points}个有效点")
        
        # 创建路径线段
        for i in range(len(path_nodes) - 1):
            line = vtk.vtkLine()
            line.GetPointIds().SetId(0, i)  # 起点
            line.GetPointIds().SetId(1, i + 1)  # 终点
            lines.InsertNextCell(line)
        
        # 创建多边形数据
        polyData = vtk.vtkPolyData()
        polyData.SetPoints(points)
        polyData.SetLines(lines)
        
        # 创建管道（使路径更粗）
        tubes = vtk.vtkTubeFilter()
        tubes.SetInputData(polyData)
        tubes.SetRadius(SRV6_ROUTE_PATH_WIDTH * 0.0001 * EARTH_RADIUS_M)  # 设置管道半径
        tubes.SetNumberOfSides(8)  # 设置管道截面的边数
        tubes.Update()
        
        # 创建映射器
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(tubes.GetOutputPort())
        
        # 创建演员
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        
        # 设置颜色和透明度
        actor.GetProperty().SetColor(SRV6_ROUTE_PATH_COLOR)
        actor.GetProperty().SetOpacity(SRV6_ROUTE_PATH_OPACITY)
        
        # 添加到渲染器
        self.renderer.AddActor(actor)
        
        # 保存演员引用（用于后续移除）
        if hasattr(self, 'srv6_route_path_actor') and self.srv6_route_path_actor:
            self.renderer.RemoveActor(self.srv6_route_path_actor)
        self.srv6_route_path_actor = actor
        
        # 创建箭头（表示路径方向）
        self.srv6_route_arrows_actors = []
        for i in range(len(path_nodes) - 1):
            # 获取线段起点和终点
            if i >= points.GetNumberOfPoints() - 1:
                break
                
            p1 = [0, 0, 0]
            p2 = [0, 0, 0]
            points.GetPoint(i, p1)
            points.GetPoint(i + 1, p2)
            
            # 计算线段中点（箭头位置）
            mid_point = [(p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2, (p1[2] + p2[2]) / 2]
            
            # 计算线段方向
            direction = [p2[0] - p1[0], p2[1] - p1[1], p2[2] - p1[2]]
            
            # 归一化方向向量
            length = (direction[0]**2 + direction[1]**2 + direction[2]**2)**0.5
            if length > 0:
                direction = [d / length for d in direction]
            
            # 创建箭头源
            arrow_source = vtk.vtkArrowSource()
            arrow_source.SetTipResolution(16)
            arrow_source.SetShaftResolution(16)
            arrow_source.SetTipLength(0.3)  # 箭头头部长度比例
            arrow_source.SetTipRadius(0.1)  # 箭头头部半径比例
            
            # 创建变换
            transform = vtk.vtkTransform()
            transform.Translate(mid_point)  # 移动到线段中点
            
            # 计算旋转角度和轴
            # 默认箭头方向是(1,0,0)，需要旋转到线段方向
            default_direction = [1, 0, 0]
            
            # 计算旋转轴（叉积）
            axis = [0, 0, 0]
            axis[0] = default_direction[1] * direction[2] - default_direction[2] * direction[1]
            axis[1] = default_direction[2] * direction[0] - default_direction[0] * direction[2]
            axis[2] = default_direction[0] * direction[1] - default_direction[1] * direction[0]
            
            # 计算旋转角度（点积）
            dot_product = default_direction[0] * direction[0] + default_direction[1] * direction[1] + default_direction[2] * direction[2]
            angle = math.acos(max(-1, min(1, dot_product))) * 180 / math.pi
            
            # 应用旋转
            if abs(angle) > 0.001 and (axis[0]**2 + axis[1]**2 + axis[2]**2) > 0.001:
                transform.RotateWXYZ(angle, axis[0], axis[1], axis[2])
            
            # 缩放箭头
            arrow_scale = SRV6_ROUTE_PATH_ARROW_SIZE * 0.0001 * EARTH_RADIUS_M
            transform.Scale(arrow_scale, arrow_scale, arrow_scale)
            
            # 创建变换过滤器
            transform_filter = vtk.vtkTransformPolyDataFilter()
            transform_filter.SetInputConnection(arrow_source.GetOutputPort())
            transform_filter.SetTransform(transform)
            transform_filter.Update()
            
            # 创建映射器
            arrow_mapper = vtk.vtkPolyDataMapper()
            arrow_mapper.SetInputConnection(transform_filter.GetOutputPort())
            
            # 创建演员
            arrow_actor = vtk.vtkActor()
            arrow_actor.SetMapper(arrow_mapper)
            
            # 设置颜色和透明度
            arrow_actor.GetProperty().SetColor(SRV6_ROUTE_PATH_COLOR)
            arrow_actor.GetProperty().SetOpacity(SRV6_ROUTE_PATH_OPACITY)
            
            # 添加到渲染器
            self.renderer.AddActor(arrow_actor)
            
            # 保存箭头演员引用
            self.srv6_route_arrows_actors.append(arrow_actor)
