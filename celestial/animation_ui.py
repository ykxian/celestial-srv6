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

"""用户界面相关功能，包括信息面板、进度条和交互处理"""

import vtk
import typing
import os
import subprocess
import time

from celestial.animation_constants import *

class AnimationUI:
    """
    Animation UI related functionality
    """
    
    def __init__(self, animation):
        """
        Initialize the UI components
        
        :param animation: The Animation instance this UI belongs to
        """
        self.animation = animation
        self.renderer = animation.renderer
        self.interactor = animation.interactor
        self.renderWindow = animation.renderWindow
        
        # 全局信息显示相关属性
        self.text_actors = []         # 存储文本演员对象
        self.progress_bar_actor = None  # 进度条演员对象
        self.progress_bg_actor = None   # 进度条背景演员对象
        
        # 点击信息面板相关属性
        self.info_panel_actor = None     # 信息面板演员对象
        self.info_panel_text_actors = [] # 信息面板文本演员对象
        self.info_panel_close_btn = None # 信息面板关闭按钮
        self.info_panel_ssh_btn = None   # SSH按钮
        self.ssh_btn_text = None         # SSH按钮文本
        
        # 创建UI组件
        self.makeInfoTextActors()
        self.makeProgressBar()
        self.makeInfoPanel()
        self.setupPicker()

    def updateInfoText(self, active_satellites=None, total_links=None) -> None:
        """
        更新信息文本显示
        
        :param active_satellites: 活跃卫星数（如果提供）
        :param total_links: 总链路数（如果提供）
        """
        if not self.text_actors:
            return

        # 使用传入的参数或重新计算
        if active_satellites is None:
            # 计算活跃卫星数
            active_satellites = 0
            for s in range(self.animation.num_shells):
                for i in range(self.animation.shell_sats[s]):
                    # 处理numpy.void类型和字典类型
                    try:
                        # 如果是字典类型
                        if hasattr(self.animation.sat_positions[s][i], 'get'):
                            if self.animation.sat_positions[s][i].get("in_bbox", True):
                                active_satellites += 1
                        # 如果是numpy.void类型
                        elif hasattr(self.animation.sat_positions[s][i], 'item'):
                            if 'in_bbox' in self.animation.sat_positions[s].dtype.names and self.animation.sat_positions[s][i]['in_bbox']:
                                active_satellites += 1
                            else:
                                active_satellites += 1  # 如果没有in_bbox字段，默认计数
                        else:
                            active_satellites += 1  # 其他情况，默认计数
                    except Exception as e:
                        print(f"计算活跃卫星数时出错: {e}")
                        # 出错时默认计数该卫星
                        active_satellites += 1
        self.animation.active_satellites = active_satellites
        
        if total_links is None:
            # 计算总链路数
            total_links = 0
            for s in range(self.animation.num_shells):
                total_links += sum(1 for link in self.animation.links[s] if link["active"])
            for s in range(self.animation.num_shells):
                total_links += len(self.animation.gst_links[s])
        self.animation.total_links_count = total_links

        # 更新文本显示
        self.text_actors[0].SetInput(f"Simulation Time: {self.animation.current_simulation_time:.2f} s")

        # 计算和显示进度
        if self.animation.simulation_duration > 0:
            # 计算进度百分比
            progress = (self.animation.current_simulation_time - self.animation.simulation_offset) / self.animation.simulation_duration
            progress = max(0.0, min(1.0, progress))  # 确保进度在0-1范围内
            progress_percent = progress * 100

            # 更新进度文本
            self.text_actors[1].SetInput(f"Progress: {progress_percent:.1f}%")

            # 更新进度条
            self.updateProgressBar(progress)
        else:
            self.text_actors[1].SetInput("Progress: Unknown")

        self.text_actors[3].SetInput(f"Active Satellites: {self.animation.active_satellites}")
        self.text_actors[4].SetInput(f"Ground Stations: {self.animation.gst_num}")
        self.text_actors[5].SetInput(f"Total Links: {self.animation.total_links_count}")

        # 如果有选中的对象，更新信息面板
        if self.animation.selected_object == "satellite" and self.animation.selected_shell >= 0 and self.animation.selected_id >= 0:
            self.updateSatelliteInfoPanel(self.animation.selected_shell, self.animation.selected_id)
        elif self.animation.selected_object == "groundstation" and self.animation.selected_id >= 0:
            self.updateGroundStationInfoPanel(self.animation.selected_id)

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
        # 使用vtkCellPicker代替vtkPropPicker，更适合检测网格和单元格
        picker = vtk.vtkCellPicker()
        picker.SetTolerance(0.05)  # 保持原有容差设置
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
            # 直接调用animation对象的clearRoutePath方法，这不会导致循环引用
            # 因为animation.py中没有代理方法调用回ui.handleKeyPress
            self.animation.clearRoutePath()
            print("路由路径选择已重置")
            
    def handleClick(self, obj: typing.Any, event: typing.Any) -> None:
        """处理鼠标点击事件"""
        # 获取点击位置
        clickPos = self.interactor.GetEventPosition()
        
        # 检查是否点击了关闭按钮
        if self.info_panel_actor and self.info_panel_actor.GetVisibility():
            close_btn_pos = self.info_panel_close_btn.GetPosition()
            if (clickPos[0] >= close_btn_pos[0] and 
                clickPos[0] <= close_btn_pos[0] + INFO_PANEL_CLOSE_BTN_SIZE and
                clickPos[1] >= close_btn_pos[1] - INFO_PANEL_CLOSE_BTN_SIZE and
                clickPos[1] <= close_btn_pos[1]):
                self.hideInfoPanel()
                return
                
            # 检查是否点击了SSH按钮
            if self.info_panel_ssh_btn and self.info_panel_ssh_btn.GetVisibility():
                ssh_btn_pos = self.info_panel_ssh_btn.GetPosition()
                if (clickPos[0] >= ssh_btn_pos[0] and 
                    clickPos[0] <= ssh_btn_pos[0] + INFO_PANEL_SSH_BTN_WIDTH and
                    clickPos[1] >= ssh_btn_pos[1] - INFO_PANEL_SSH_BTN_HEIGHT and
                    clickPos[1] <= ssh_btn_pos[1]):
                    self.executeSSHCommand()
                    return
        
        # 使用拾取器检测点击的对象
        picker = self.interactor.GetPicker()
        
        # 首先尝试检测卫星点云（设置最高优先级）
        # 这是因为vtkPropPicker可能无法很好地拾取点云，所以我们使用屏幕坐标计算
        clickPos = self.interactor.GetEventPosition()
        closest_sat_shell = -1
        closest_sat_id = -1
        min_screen_distance = 20  # 屏幕像素距离阈值
        
        # 遍历所有shell中的卫星
        for s in range(self.animation.num_shells):
            if s >= len(self.animation.actors.shell_actors):
                continue
                
            # 获取点云数据
            points = None
            if hasattr(self.animation.actors.shell_actors[s], 'satVtkPts'):
                points = self.animation.actors.shell_actors[s].satVtkPts
            elif hasattr(self.animation.actors.shell_inactive_actors[s], 'satVtkPts'):
                points = self.animation.actors.shell_inactive_actors[s].satVtkPts
                
            if not points:
                continue
                
            # 检查每个卫星点
            for i in range(min(self.animation.shell_sats[s], points.GetNumberOfPoints())):
                # 只检查在视图范围内的卫星
                # 处理numpy.void类型和字典类型
                try:
                    # 如果是字典类型
                    if hasattr(self.animation.sat_positions[s][i], 'get'):
                        if not self.animation.sat_positions[s][i].get("in_bbox", True):
                            continue
                    # 如果是numpy.void类型
                    elif hasattr(self.animation.sat_positions[s][i], 'item'):
                        if 'in_bbox' in self.animation.sat_positions[s].dtype.names and not self.animation.sat_positions[s][i]['in_bbox']:
                            continue
                    # 其他情况，默认显示
                except Exception as e:
                    print(f"检查卫星可见性时出错: {e}")
                    # 出错时默认显示该卫星
                    pass
                    
                # 获取卫星世界坐标
                sat_world_pos = [0, 0, 0]
                points.GetPoint(i, sat_world_pos)
                
                # 转换为屏幕坐标
                coordinate = vtk.vtkCoordinate()
                coordinate.SetCoordinateSystemToWorld()
                coordinate.SetValue(sat_world_pos[0], sat_world_pos[1], sat_world_pos[2])
                sat_screen_pos = coordinate.GetComputedDisplayValue(self.renderer)
                
                if not sat_screen_pos:
                    continue
                    
                # 计算屏幕距离
                screen_dist = ((clickPos[0] - sat_screen_pos[0])**2 + 
                              (clickPos[1] - sat_screen_pos[1])**2)**0.5
                
                # 如果距离小于阈值且小于当前最小距离
                if screen_dist < min_screen_distance:
                    min_screen_distance = screen_dist
                    closest_sat_shell = s
                    closest_sat_id = i
        
        # 如果找到了最近的卫星，直接选中它
        if closest_sat_shell >= 0 and closest_sat_id >= 0:
            print(f"点击了卫星：shell {closest_sat_shell+1}, id {closest_sat_id}")
            self.animation.selected_object = "satellite"
            self.animation.selected_shell = closest_sat_shell
            self.animation.selected_id = closest_sat_id
            self.updateSatelliteInfoPanel(closest_sat_shell, closest_sat_id)
            return
            
        # 然后尝试检测地面站
        # 遍历所有地面站点，检查点击位置是否在地面站附近
        for gst_id in range(self.animation.gst_num):
            # 获取地面站的世界坐标 - 直接从地面站演员获取最新位置
            if self.animation.actors.gst_actor and self.animation.actors.gst_actor.satVtkPts:
                gst_world_pos = [0, 0, 0]  # 初始化坐标
                self.animation.actors.gst_actor.satVtkPts.GetPoint(gst_id, gst_world_pos)
            else:
                # 如果无法从演员获取，则使用存储的位置（可能不是最新的）
                gst_coords = self.animation.gst_positions[gst_id]
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
                print(f"点击了地面站: id={gst_id}")
                self.animation.selected_object = "groundstation"
                self.animation.selected_shell = -1
                self.animation.selected_id = gst_id
                self.updateGroundStationInfoPanel(gst_id)
                return
        
        # 获取拾取的演员（vtkCellPicker返回的是vtkActor）
        actor = picker.GetActor()
         
        if actor is None:
            # 如果点击空白处，隐藏信息面板
            self.hideInfoPanel()
            return
        
        # 如果到达这里，说明点击了其他对象
        print(f"点击了未识别对象: {actor}")
        self.hideInfoPanel()
        
    def handleRightClick(self, obj: typing.Any, event: typing.Any) -> None:
        """处理鼠标右键点击事件"""
        # 获取点击位置
        clickPos = self.interactor.GetEventPosition()
        print(f"右键点击位置: x={clickPos[0]}, y={clickPos[1]}")
        
        # 如果已经有请求挂起，不处理新的点击
        if hasattr(self.animation, 'route_request_pending') and self.animation.route_request_pending:
            print("路由请求正在处理中，请稍候...")
            return
            
        # 如果处于重置状态，检查是否已经过了足够的时间
        if hasattr(self.animation, 'route_reset') and self.animation.route_reset:
            # 如果已经过了重置持续时间，自动解除重置状态
            if hasattr(self.animation, 'reset_timer_start') and self.animation.reset_timer_start is not None:
                if time.time() - self.animation.reset_timer_start > ROUTE_RESET_DURATION:  # 使用常量
                    self.animation.route_reset = False
                    self.animation.reset_timer_start = None
                    print("系统已恢复，可以继续使用路由功能")
                else:
                    print("系统刚刚重置，请稍候再试...")
                    return
            else:
                print("系统刚刚重置，请稍候再试...")
                return
        
        # 获取点击位置
        clickPos = self.interactor.GetEventPosition()
        
        # 获取拾取器
        picker = self.interactor.GetPicker()
        
        # 首先尝试检测卫星点云（设置最高优先级）
        # 这是因为vtkPropPicker可能无法很好地拾取点云，所以我们使用屏幕坐标计算
        clickPos = self.interactor.GetEventPosition()
        closest_sat_shell = -1
        closest_sat_id = -1
        min_screen_distance = 20  # 屏幕像素距离阈值
        
        # 遍历所有shell中的卫星
        for s in range(self.animation.num_shells):
            if s >= len(self.animation.actors.shell_actors):
                continue
                
            # 获取点云数据
            points = None
            if hasattr(self.animation.actors.shell_actors[s], 'satVtkPts'):
                points = self.animation.actors.shell_actors[s].satVtkPts
            elif hasattr(self.animation.actors.shell_inactive_actors[s], 'satVtkPts'):
                points = self.animation.actors.shell_inactive_actors[s].satVtkPts
                
            if not points:
                continue
                
            # 检查每个卫星点
            for i in range(min(self.animation.shell_sats[s], points.GetNumberOfPoints())):
                # 只检查在视图范围内的卫星
                # 处理numpy.void类型和字典类型
                try:
                    # 如果是字典类型
                    if hasattr(self.animation.sat_positions[s][i], 'get'):
                        if not self.animation.sat_positions[s][i].get("in_bbox", True):
                            continue
                    # 如果是numpy.void类型
                    elif hasattr(self.animation.sat_positions[s][i], 'item'):
                        if 'in_bbox' in self.animation.sat_positions[s].dtype.names and not self.animation.sat_positions[s][i]['in_bbox']:
                            continue
                    # 其他情况，默认显示
                except Exception as e:
                    print(f"检查卫星可见性时出错: {e}")
                    # 出错时默认显示该卫星
                    pass
                    
                # 获取卫星世界坐标
                sat_world_pos = [0, 0, 0]
                points.GetPoint(i, sat_world_pos)
                
                # 转换为屏幕坐标
                coordinate = vtk.vtkCoordinate()
                coordinate.SetCoordinateSystemToWorld()
                coordinate.SetValue(sat_world_pos[0], sat_world_pos[1], sat_world_pos[2])
                sat_screen_pos = coordinate.GetComputedDisplayValue(self.renderer)
                
                if not sat_screen_pos:
                    continue
                    
                # 计算屏幕距离
                screen_dist = ((clickPos[0] - sat_screen_pos[0])**2 + 
                              (clickPos[1] - sat_screen_pos[1])**2)**0.5
                
                # 如果距离小于阈值且小于当前最小距离
                if screen_dist < min_screen_distance:
                    min_screen_distance = screen_dist
                    closest_sat_shell = s
                    closest_sat_id = i
        
        # 如果找到了最近的卫星，直接选中它
        if closest_sat_shell >= 0 and closest_sat_id >= 0:
            # print(f"右键点击了卫星点云（屏幕坐标检测）：shell {closest_sat_shell}, id {closest_sat_id}, 屏幕距离: {min_screen_distance}")
            # 如果没有选择起点，则设置为起点
            if self.animation.route_source_type is None:
                self.animation.route_source_type = "satellite"
                self.animation.route_source_shell = closest_sat_shell
                self.animation.route_source_id = closest_sat_id
                print(f"Selected satellite {closest_sat_shell+1}-{closest_sat_id} as route source")
                return
            # 如果已有起点，则计算并显示路径
            else:
                self.animation.route_target_type = "satellite"
                self.animation.route_target_shell = closest_sat_shell
                self.animation.route_target_id = closest_sat_id
                # 调用Animation类中的showRoutePath方法
                self.animation.showRoutePath(
                    self.animation.route_source_type,
                    self.animation.route_source_shell,
                    self.animation.route_source_id,
                    self.animation.route_target_type,
                    self.animation.route_target_shell,
                    self.animation.route_target_id
                )
                return
        
        # 然后尝试检测地面站（设置更高的优先级）
        # 遍历所有地面站点，检查点击位置是否在地面站附近
        for gst_id in range(self.animation.gst_num):
            # 获取地面站的世界坐标 - 直接从地面站演员获取最新位置
            if self.animation.actors.gst_actor and self.animation.actors.gst_actor.satVtkPts:
                gst_world_pos = [0, 0, 0]  # 初始化坐标
                self.animation.actors.gst_actor.satVtkPts.GetPoint(gst_id, gst_world_pos)
            else:
                # 如果无法从演员获取，则使用存储的位置（可能不是最新的）
                gst_coords = self.animation.gst_positions[gst_id]
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
                if self.animation.route_source_type is None:
                    self.animation.route_source_type = "groundstation"
                    self.animation.route_source_shell = -1  # 地面站的shell始终为-1
                    self.animation.route_source_id = gst_id
                    print(f"Selected ground station {gst_id} as route source")
                    return
                # 如果已有起点，则计算并显示路径
                else:
                    self.animation.route_target_type = "groundstation"
                    self.animation.route_target_shell = -1
                    self.animation.route_target_id = gst_id
                    # 调用Animation类中的showRoutePath方法
                    self.animation.showRoutePath(
                        self.animation.route_source_type,
                        self.animation.route_source_shell,
                        self.animation.route_source_id,
                        self.animation.route_target_type,
                        self.animation.route_target_shell,
                        self.animation.route_target_id
                    )
                    return
        return

    def updateSatelliteInfoPanel(self, shell: int, sat_id: int) -> None:
        """更新卫星信息面板"""
        if not self.info_panel_actor or shell < 0 or shell >= self.animation.num_shells or sat_id < 0 or sat_id >= self.animation.shell_sats[shell]:
            return

        # 获取卫星信息
        sat = self.animation.sat_positions[shell][sat_id]
        # 创建一个字典来存储卫星信息，确保统一访问方式
        sat_info = {}
        try:
            # 如果是字典类型
            if hasattr(sat, 'get'):
                for key in sat.keys():
                    sat_info[key] = sat[key]
            # 如果是numpy.void类型
            elif hasattr(sat, 'item'):
                for name in self.animation.sat_positions[shell].dtype.names:
                    sat_info[name] = sat[name]
            else:
                # 其他情况，尝试直接转换为字典
                sat_info = dict(sat)
        except Exception as e:
            print(f"处理卫星信息时出错: {e}")
            # 创建基本信息
            sat_info = {'ID': sat_id}

        # 计算卫星IP地址 - 确保使用正确的shell标识符
        # 使用shell确保IP地址计算与显示的SHELL-ID一致
        ipv6 = self.calculateIPv6(shell + 1, sat_id)  # shell_identifier从1开始
        ipv4 = self.calculateIPv4(shell + 1, sat_id)
        
        # 使用sat_info代替sat，确保统一访问方式

        # 固定面板位置在屏幕右上角
        window_size = self.renderWindow.GetSize()
        panel_pos_x = window_size[0] - INFO_PANEL_WIDTH - 20  # 右边距20像素
        panel_pos_y = window_size[1] - 20  # 顶部边距20像素
        self.info_panel_actor.SetPosition(panel_pos_x, panel_pos_y)

        # 更新面板文本
        self.info_panel_text_actors[0].SetInput(f"Satellite Info")
        # 确保使用正确的shell和sat_id，这里使用当前点击的卫星的实际索引
        self.info_panel_text_actors[1].SetInput(f"SHELL-ID: {shell+1}-{sat_id}")
        self.info_panel_text_actors[2].SetInput(f"IPv6: {ipv6}")
        
        # 显示IPv4地址
        self.info_panel_text_actors[3].SetInput(f"IPv4: {ipv4}")
        
        # 使用sat_info显示位置信息
        try:
            if 'x' in sat_info and 'y' in sat_info and 'z' in sat_info:
                self.info_panel_text_actors[4].SetInput(f"Position: ({sat_info['x']:.0f}, {sat_info['y']:.0f}, {sat_info['z']:.0f})")
            elif hasattr(sat, 'item') and all(attr in self.animation.sat_positions[shell].dtype.names for attr in ['x', 'y', 'z']):
                self.info_panel_text_actors[4].SetInput(f"Position: ({sat['x']:.0f}, {sat['y']:.0f}, {sat['z']:.0f})")
            else:
                self.info_panel_text_actors[4].SetInput(f"Position: Unknown")
        except Exception as e:
            print(f"显示卫星位置信息时出错: {e}")
            self.info_panel_text_actors[4].SetInput(f"Position: Unknown")
        # 显示卫星状态
        try:
            if hasattr(sat, 'get'):
                is_active = sat.get('in_bbox', False)
            elif hasattr(sat, 'item') and 'in_bbox' in self.animation.sat_positions[shell].dtype.names:
                is_active = bool(sat['in_bbox'])
            else:
                is_active = 'in_bbox' in sat_info and sat_info['in_bbox']
                
            self.info_panel_text_actors[5].SetInput(f"Status: {'Active' if is_active else 'Inactive'}")
        except Exception as e:
            print(f"显示卫星状态时出错: {e}")
            self.info_panel_text_actors[5].SetInput(f"Status: Unknown")

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
        if not self.info_panel_actor or gst_id < 0 or gst_id >= self.animation.gst_num:
            return
            
        # 获取地面站信息
        gst = self.animation.gst_positions[gst_id]
        
        # 计算地面站IP地址（地面站的shell为0）
        ipv6 = self.calculateIPv6(0, gst_id)
        ipv4 = self.calculateIPv4(0, gst_id)
        
        # 获取地面站名称（如果可用）
        name = "Unknown"
        # 简化名称获取逻辑，只要确保索引有效即可
        if hasattr(self.animation, 'gst_names') and self.animation.gst_names and gst_id < len(self.animation.gst_names):
            name = self.animation.gst_names[gst_id] or "Unknown"  # 使用or运算符简化逻辑
        
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
        
    def resizeInfoPanel(self, height: float) -> None:
        """调整信息面板高度"""
        if not self.info_panel_actor:
            return
            
        # 创建新的点集合
        panel_points = vtk.vtkPoints()
        panel_points.InsertNextPoint(0, 0, 0)  # 左上
        panel_points.InsertNextPoint(INFO_PANEL_WIDTH, 0, 0)  # 右上
        panel_points.InsertNextPoint(INFO_PANEL_WIDTH, -height, 0)  # 右下
        panel_points.InsertNextPoint(0, -height, 0)  # 左下
        
        # 创建新的单元格数组
        panel_cells = vtk.vtkCellArray()
        panel_cells.InsertNextCell(4)
        panel_cells.InsertCellPoint(0)
        panel_cells.InsertCellPoint(1)
        panel_cells.InsertCellPoint(2)
        panel_cells.InsertCellPoint(3)
        
        # 创建新的多边形数据
        panel_poly_data = vtk.vtkPolyData()
        panel_poly_data.SetPoints(panel_points)
        panel_poly_data.SetPolys(panel_cells)
        
        # 更新映射器输入数据
        self.info_panel_actor.GetMapper().SetInputData(panel_poly_data)
        self.info_panel_actor.GetMapper().Update()
        
    def showInfoPanel(self) -> None:
        """显示信息面板"""
        if not self.info_panel_actor:
            return
            
        # 显示面板背景
        self.info_panel_actor.VisibilityOn()
        
        # 显示关闭按钮
        self.info_panel_close_btn.VisibilityOn()
        
        # 显示文本
        for actor in self.info_panel_text_actors:
            actor.VisibilityOn()
            
    def hideInfoPanel(self) -> None:
        """隐藏信息面板"""
        if not self.info_panel_actor:
            return
            
        # 隐藏面板背景
        self.info_panel_actor.VisibilityOff()
        
        # 隐藏关闭按钮
        self.info_panel_close_btn.VisibilityOff()
        
        # 隐藏SSH按钮
        self.info_panel_ssh_btn.VisibilityOff()
        self.ssh_btn_text.VisibilityOff()
        
        # 隐藏文本
        for actor in self.info_panel_text_actors:
            actor.VisibilityOff()
            
        # 重置选择状态
        self.animation.selected_object = None
        self.animation.selected_shell = -1
        self.animation.selected_id = -1
        
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
        if self.animation.selected_object is None:
            print("No object selected for SSH connection")
            return

        # 获取IP地址
        ip_address = ""
        terminal_title = "Terminal"  # 默认终端标题

        if self.animation.selected_object == "satellite" and self.animation.selected_shell >= 0 and self.animation.selected_id >= 0:
            # 使用IPv4地址连接卫星
            ip_address = self.calculateIPv4(self.animation.selected_shell + 1, self.animation.selected_id)
            # 设置终端标题为SHELL-ID格式
            terminal_title = f"SHELL{self.animation.selected_shell + 1}-{self.animation.selected_id}"
        elif self.animation.selected_object == "groundstation" and self.animation.selected_id >= 0:
            # 使用IPv4地址连接地面站
            ip_address = self.calculateIPv4(0, self.animation.selected_id)
            # 设置终端标题为gst-NAME格式
            if self.animation.selected_id < len(self.animation.gst_names) and self.animation.gst_names[self.animation.selected_id]:
                terminal_title = f"gst-{self.animation.gst_names[self.animation.selected_id]}"
            else:
                terminal_title = f"gst-{self.animation.selected_id}"

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
