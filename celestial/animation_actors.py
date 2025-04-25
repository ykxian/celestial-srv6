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

"""可视化元素（Actors）相关功能，包括卫星、地面站、链路和地球模型的创建和更新"""

import vtk
import numpy as np
import typing
from dataclasses import dataclass

from celestial.animation_constants import *

@dataclass
class ShellActor:
    """单个壳层的演员数据结构"""
    satVtkPts: typing.Any = None
    satVtkVerts: typing.Any = None
    satPolyData: typing.Any = None
    satsMapper: typing.Any = None
    satsActor: typing.Any = None
    satPointIDs: typing.List = None

@dataclass
class LinkActor:
    """链路演员数据结构"""
    linkVtkPts: typing.Any = None
    linkVtkLines: typing.Any = None
    linkPolyData: typing.Any = None
    linkMapper: typing.Any = None
    linkActor: typing.Any = None
    pathLinkLines: typing.Any = None

@dataclass
class GstLinkActor:
    """地面站链路演员数据结构"""
    gstLinkPoints: typing.Any = None
    gstLinkLines: typing.Any = None
    gstLinkPolyData: typing.Any = None
    gstLinkMapper: typing.Any = None
    gstLinkActor: typing.Any = None

class AnimationActors:
    """
    负责创建和管理所有可视化元素（Actors）
    """
    
    def __init__(self, renderer):
        """
        初始化
        
        :param renderer: VTK渲染器
        """
        self.renderer = renderer
        
        # 存储各种演员的容器
        self.earthActor = None
        self.sphereActor = None
        self.earthRadius = None
        
        # 卫星和链路演员
        self.shell_actors = []
        self.shell_inactive_actors = []
        self.link_actors = []
        
        # 地面站和链路演员
        self.gst_actor = None
        self.gst_link_actor = GstLinkActor()  # 单个全局地面站链路演员，而不是按壳层分开
        
    def makeSatsActor(self, shell_no: int, shell_total_sats: int, sat_positions, sat_colors) -> None:
        """
        生成卫星点云
        
        :param shell_no: 壳层索引
        :param shell_total_sats: 壳层中的卫星总数
        :param sat_positions: 卫星位置数据
        :param sat_colors: 卫星颜色
        """
        # 确保演员列表足够长
        while len(self.shell_actors) <= shell_no:
            self.shell_actors.append(ShellActor())
            
        # 声明点和单元格数组来保存位置数据
        self.shell_actors[shell_no].satVtkPts = vtk.vtkPoints()
        self.shell_actors[shell_no].satVtkVerts = vtk.vtkCellArray()

        # 初始化ID数组
        self.shell_actors[shell_no].satPointIDs = [None] * shell_total_sats

        # 初始化所有位置
        for i in range(len(sat_positions[shell_no])):
            self.shell_actors[
                shell_no
            ].satPointIDs[i] = self.shell_actors[
                shell_no
            ].satVtkPts.InsertNextPoint(
                sat_positions[shell_no][i]["x"],
                sat_positions[shell_no][i]["y"],
                sat_positions[shell_no][i]["z"],
            )

            self.shell_actors[shell_no].satVtkVerts.InsertNextCell(1)
            self.shell_actors[shell_no].satVtkVerts.InsertCellPoint(
                self.shell_actors[shell_no].satPointIDs[i]
            )

        # 将点转换为多边形数据
        self.shell_actors[shell_no].satPolyData = vtk.vtkPolyData()
        self.shell_actors[shell_no].satPolyData.SetPoints(
            self.shell_actors[shell_no].satVtkPts
        )
        self.shell_actors[shell_no].satPolyData.SetVerts(
            self.shell_actors[shell_no].satVtkVerts
        )

        # 创建映射器对象并连接到多边形数据
        self.shell_actors[shell_no].satsMapper = vtk.vtkPolyDataMapper()
        self.shell_actors[shell_no].satsMapper.SetInputData(
            self.shell_actors[shell_no].satPolyData
        )

        # 创建演员并连接到映射器
        self.shell_actors[shell_no].satsActor = vtk.vtkActor()
        self.shell_actors[shell_no].satsActor.SetMapper(
            self.shell_actors[shell_no].satsMapper
        )

        # 编辑卫星外观
        self.shell_actors[shell_no].satsActor.GetProperty().SetOpacity(SAT_OPACITY)
        self.shell_actors[shell_no].satsActor.GetProperty().SetColor(
            sat_colors[shell_no]
        )
        self.shell_actors[shell_no].satsActor.GetProperty().SetPointSize(SAT_POINT_SIZE)
        
        # 添加到渲染器
        self.renderer.AddActor(self.shell_actors[shell_no].satsActor)

    def makeInactiveSatsActor(self, shell_no: int, shell_total_sats: int) -> None:
        """
        生成非活跃卫星点云
        
        :param shell_no: 壳层索引
        :param shell_total_sats: 壳层中的卫星总数
        """
        # 确保演员列表足够长
        while len(self.shell_inactive_actors) <= shell_no:
            self.shell_inactive_actors.append(ShellActor())
            
        # 声明点和单元格数组来保存位置数据
        self.shell_inactive_actors[shell_no].satVtkPts = vtk.vtkPoints()
        self.shell_inactive_actors[shell_no].satVtkVerts = vtk.vtkCellArray()

        # 初始化ID数组
        self.shell_inactive_actors[shell_no].satPointIDs = [None] * shell_total_sats

        # 初始化所有位置（初始设为原点）
        for i in range(shell_total_sats):
            self.shell_inactive_actors[shell_no].satPointIDs[i] = (
                self.shell_inactive_actors[shell_no].satVtkPts.InsertNextPoint(0, 0, 0)
            )

            self.shell_inactive_actors[shell_no].satVtkVerts.InsertNextCell(1)
            self.shell_inactive_actors[shell_no].satVtkVerts.InsertCellPoint(
                self.shell_inactive_actors[shell_no].satPointIDs[i]
            )

        # 将点转换为多边形数据
        self.shell_inactive_actors[shell_no].satPolyData = vtk.vtkPolyData()
        self.shell_inactive_actors[shell_no].satPolyData.SetPoints(
            self.shell_inactive_actors[shell_no].satVtkPts
        )
        self.shell_inactive_actors[shell_no].satPolyData.SetVerts(
            self.shell_inactive_actors[shell_no].satVtkVerts
        )

        # 创建映射器对象并连接到多边形数据
        self.shell_inactive_actors[shell_no].satsMapper = vtk.vtkPolyDataMapper()
        self.shell_inactive_actors[shell_no].satsMapper.SetInputData(
            self.shell_inactive_actors[shell_no].satPolyData
        )

        # 创建演员并连接到映射器
        self.shell_inactive_actors[shell_no].satsActor = vtk.vtkActor()
        self.shell_inactive_actors[shell_no].satsActor.SetMapper(
            self.shell_inactive_actors[shell_no].satsMapper
        )

        # 编辑非活跃卫星外观
        self.shell_inactive_actors[shell_no].satsActor.GetProperty().SetOpacity(
            SAT_INACTIVE_OPACITY
        )
        self.shell_inactive_actors[shell_no].satsActor.GetProperty().SetColor(
            self.renderer.GetActiveCamera().GetViewUp()  # 临时占位，将在makeRenderWindow中设置正确的颜色
        )
        self.shell_inactive_actors[shell_no].satsActor.GetProperty().SetPointSize(
            SAT_POINT_SIZE
        )
        
        # 添加到渲染器
        self.renderer.AddActor(self.shell_inactive_actors[shell_no].satsActor)

    def makeLinkActors(self, shell_no: int, shell_total_satellites: int, link_color, sat_positions, links) -> None:
        """
        生成卫星链路
        
        :param shell_no: 壳层索引
        :param shell_total_satellites: 壳层中的卫星总数
        :param link_color: 链路颜色
        :param sat_positions: 卫星位置数据
        :param links: 链路数据
        """
        # 确保演员列表足够长
        while len(self.link_actors) <= shell_no:
            self.link_actors.append(LinkActor())
            
        # 声明点数组来保存卫星位置
        self.link_actors[shell_no].linkVtkPts = vtk.vtkPoints()
        self.link_actors[shell_no].linkVtkPts.SetNumberOfPoints(shell_total_satellites)

        # 设置每个卫星的位置
        for i in range(len(sat_positions)):
            self.link_actors[shell_no].linkVtkPts.SetPoint(
                i,
                sat_positions[i]["x"],
                sat_positions[i]["y"],
                sat_positions[i]["z"],
            )

        # 创建线段数组来表示连接关系
        self.link_actors[shell_no].linkVtkLines = vtk.vtkCellArray()

        # 填充链路数据
        for i in range(len(links)):
            e1 = links[i]["node_1"]
            e2 = links[i]["node_2"]
            # 必须将链路端点转换为点名称
            self.link_actors[shell_no].linkVtkLines.InsertNextCell(2)
            self.link_actors[shell_no].linkVtkLines.InsertCellPoint(e1)
            self.link_actors[shell_no].linkVtkLines.InsertCellPoint(e2)

        # 初始化路径链路线（但不填充）
        self.link_actors[shell_no].pathLinkLines = vtk.vtkCellArray()

        # 将点和线段转换为多边形数据
        self.link_actors[shell_no].linkPolyData = vtk.vtkPolyData()
        self.link_actors[shell_no].linkPolyData.SetPoints(
            self.link_actors[shell_no].linkVtkPts
        )
        self.link_actors[shell_no].linkPolyData.SetLines(
            self.link_actors[shell_no].linkVtkLines
        )

        # 创建映射器对象并连接到多边形数据
        self.link_actors[shell_no].linkMapper = vtk.vtkPolyDataMapper()
        self.link_actors[shell_no].linkMapper.SetInputData(
            self.link_actors[shell_no].linkPolyData
        )

        # 创建演员并连接到映射器
        self.link_actors[shell_no].linkActor = vtk.vtkActor()
        self.link_actors[shell_no].linkActor.SetMapper(
            self.link_actors[shell_no].linkMapper
        )

        # 编辑链路外观
        self.link_actors[shell_no].linkActor.GetProperty().SetOpacity(ISL_LINK_OPACITY)
        self.link_actors[shell_no].linkActor.GetProperty().SetColor(link_color)
        self.link_actors[shell_no].linkActor.GetProperty().SetLineWidth(ISL_LINE_WIDTH)
        
        # 添加到渲染器
        self.renderer.AddActor(self.link_actors[shell_no].linkActor)

    def makeGstActor(self, gst_num: int, gst_positions) -> None:
        """
        生成地面站
        
        :param gst_num: 地面站数量
        :param gst_positions: 地面站位置数据
        """
        # 创建地面站演员
        self.gst_actor = ShellActor()
        
        # 声明点和单元格数组来保存位置数据
        self.gst_actor.satVtkPts = vtk.vtkPoints()
        self.gst_actor.satVtkVerts = vtk.vtkCellArray()

        # 初始化ID数组
        self.gst_actor.satPointIDs = [None] * gst_num

        # 初始化所有位置
        for i in range(gst_num):
            self.gst_actor.satPointIDs[i] = self.gst_actor.satVtkPts.InsertNextPoint(
                gst_positions[i]["x"],
                gst_positions[i]["y"],
                gst_positions[i]["z"],
            )

            self.gst_actor.satVtkVerts.InsertNextCell(1)
            self.gst_actor.satVtkVerts.InsertCellPoint(self.gst_actor.satPointIDs[i])

        # 将点转换为多边形数据
        self.gst_actor.satPolyData = vtk.vtkPolyData()
        self.gst_actor.satPolyData.SetPoints(self.gst_actor.satVtkPts)
        self.gst_actor.satPolyData.SetVerts(self.gst_actor.satVtkVerts)

        # 创建映射器对象并连接到多边形数据
        self.gst_actor.satsMapper = vtk.vtkPolyDataMapper()
        self.gst_actor.satsMapper.SetInputData(self.gst_actor.satPolyData)

        # 创建演员并连接到映射器
        self.gst_actor.satsActor = vtk.vtkActor()
        self.gst_actor.satsActor.SetMapper(self.gst_actor.satsMapper)

        # 编辑地面站外观
        self.gst_actor.satsActor.GetProperty().SetOpacity(GST_OPACITY)
        self.gst_actor.satsActor.GetProperty().SetColor(GST_COLOR)
        self.gst_actor.satsActor.GetProperty().SetPointSize(GST_POINT_SIZE)
        
        # 添加到渲染器
        self.renderer.AddActor(self.gst_actor.satsActor)

    def makeGstLinkActor(self, gst_num: int, shell_sats, sat_positions, gst_positions, gst_links) -> None:
        """
        生成地面站链路
        
        :param gst_num: 地面站数量
        :param shell_sats: 每个壳层的卫星数量
        :param sat_positions: 卫星位置数据
        :param gst_positions: 地面站位置数据
        :param gst_links: 地面站链路数据
        """
        # 声明点数组来保存地面站和卫星位置
        self.gst_link_actor.gstLinkPoints = vtk.vtkPoints()
        self.gst_link_actor.gstLinkPoints.SetNumberOfPoints(
            gst_num + sum(shell_sats)
        )

        # 添加地面站点
        for i in range(gst_num):
            x = gst_positions[i]["x"]
            y = gst_positions[i]["y"]
            z = gst_positions[i]["z"]
            self.gst_link_actor.gstLinkPoints.SetPoint(i, x, y, z)

        # 添加所有卫星点
        num_points = gst_num

        for s in range(len(shell_sats)):
            for i in range(shell_sats[s]):
                x = sat_positions[s][i]["x"]
                y = sat_positions[s][i]["y"]
                z = sat_positions[s][i]["z"]
                self.gst_link_actor.gstLinkPoints.SetPoint(num_points, x, y, z)
                num_points += 1

        # 创建线段数组来表示连接关系
        self.gst_link_actor.gstLinkLines = vtk.vtkCellArray()

        offset = gst_num

        for s in range(len(shell_sats)):
            for i in range(len(gst_links[s])):
                e1 = gst_links[s][i]["gst"] * -1 - 1
                e2 = gst_links[s][i]["sat"] + offset

                # 必须将链路端点转换为点名称
                self.gst_link_actor.gstLinkLines.InsertNextCell(2)
                self.gst_link_actor.gstLinkLines.InsertCellPoint(e1)
                self.gst_link_actor.gstLinkLines.InsertCellPoint(e2)

            offset += shell_sats[s]

        # 将点和线段转换为多边形数据
        self.gst_link_actor.gstLinkPolyData = vtk.vtkPolyData()
        self.gst_link_actor.gstLinkPolyData.SetPoints(
            self.gst_link_actor.gstLinkPoints
        )
        self.gst_link_actor.gstLinkPolyData.SetLines(
            self.gst_link_actor.gstLinkLines
        )

        # 创建映射器对象并连接到多边形数据
        self.gst_link_actor.gstLinkMapper = vtk.vtkPolyDataMapper()
        self.gst_link_actor.gstLinkMapper.SetInputData(
            self.gst_link_actor.gstLinkPolyData
        )

        # 创建演员并连接到映射器
        self.gst_link_actor.gstLinkActor = vtk.vtkActor()
        self.gst_link_actor.gstLinkActor.SetMapper(
            self.gst_link_actor.gstLinkMapper
        )

        # 编辑地面站链路外观
        self.gst_link_actor.gstLinkActor.GetProperty().SetOpacity(GST_LINK_OPACITY)
        self.gst_link_actor.gstLinkActor.GetProperty().SetColor(GST_LINK_COLOR)
        self.gst_link_actor.gstLinkActor.GetProperty().SetLineWidth(GST_LINE_WIDTH)
        
        # 添加到渲染器
        self.renderer.AddActor(self.gst_link_actor.gstLinkActor)

    def makeEarthActor(self, earth_radius: int) -> None:
        """
        生成地球模型
        
        :param earth_radius: 地球半径（米）
        """
        self.earthRadius = earth_radius

        # 创建地球地图（轮廓）
        self.earthSource = vtk.vtkEarthSource()
        self.earthSource.SetRadius(self.earthRadius * 1.001)
        self.earthSource.SetOnRatio(1)

        # 创建映射器
        self.earthMapper = vtk.vtkPolyDataMapper()
        self.earthMapper.SetInputConnection(self.earthSource.GetOutputPort())

        # 创建演员
        self.earthActor = vtk.vtkActor()
        self.earthActor.SetMapper(self.earthMapper)

        # 设置颜色
        self.earthActor.GetProperty().SetColor(LANDMASS_OUTLINE_COLOR)
        self.earthActor.GetProperty().SetOpacity(EARTH_LAND_OPACITY)

        # 创建地球球体
        num_pts = EARTH_SPHERE_POINTS
        indices = np.arange(0, num_pts, dtype=float) + 0.5
        phi = np.arccos(1 - 2 * indices / num_pts)
        theta = np.pi * (1 + 5**0.5) * indices
        x = np.cos(theta) * np.sin(phi) * self.earthRadius
        y = np.sin(theta) * np.sin(phi) * self.earthRadius
        z = np.cos(phi) * self.earthRadius

        # 创建球体点
        points = vtk.vtkPoints()
        for i in range(len(x)):
            points.InsertNextPoint(x[i], y[i], z[i])

        poly = vtk.vtkPolyData()
        poly.SetPoints(points)

        # 使用Delaunay三角剖分创建球面
        d3D = vtk.vtkDelaunay3D()
        d3D.SetInputData(poly)

        # 提取表面
        dss = vtk.vtkDataSetSurfaceFilter()
        dss.SetInputConnection(d3D.GetOutputPort())
        dss.Update()

        # 获取最终的多边形数据
        spherePoly = dss.GetOutput()

        # 创建映射器
        sphereMapper = vtk.vtkPolyDataMapper()
        sphereMapper.SetInputData(spherePoly)

        # 创建演员
        self.sphereActor = vtk.vtkActor()
        self.sphereActor.SetMapper(sphereMapper)

        # 设置颜色
        self.sphereActor.GetProperty().SetColor(EARTH_BASE_COLOR)
        self.sphereActor.GetProperty().SetOpacity(EARTH_OPACITY)
        
        # 添加到渲染器
        self.renderer.AddActor(self.earthActor)
        self.renderer.AddActor(self.sphereActor)

    def updateSatPositions(self, shell_no: int, sat_positions, in_bbox) -> None:
        """
        更新卫星位置
        
        :param shell_no: 壳层索引
        :param sat_positions: 卫星位置数据
        :param in_bbox: 卫星是否在边界框内的标志
        """
        # 确保壳层索引有效
        if shell_no >= len(self.shell_actors) or shell_no >= len(self.shell_inactive_actors):
            return
            
        # 获取活跃和非活跃卫星的点集合
        active_pts = self.shell_actors[shell_no].satVtkPts
        inactive_pts = self.shell_inactive_actors[shell_no].satVtkPts

        # 更新每个卫星的位置
        for i in range(len(sat_positions)):
            if i < len(in_bbox) and in_bbox[i]:
                # 活跃卫星
                active_pts.SetPoint(
                    i,
                    sat_positions[i]["x"],
                    sat_positions[i]["y"],
                    sat_positions[i]["z"],
                )
                inactive_pts.SetPoint(i, 0, 0, 0)  # 非活跃点设为原点
            else:
                # 非活跃卫星
                inactive_pts.SetPoint(
                    i,
                    sat_positions[i]["x"],
                    sat_positions[i]["y"],
                    sat_positions[i]["z"],
                )
                active_pts.SetPoint(i, 0, 0, 0)  # 活跃点设为原点

        # 标记点已修改
        active_pts.Modified()
        inactive_pts.Modified()

    def updateLinks(self, shell_no: int, links, sat_positions) -> None:
        """
        更新卫星链路
        
        :param shell_no: 壳层索引
        :param links: 链路数据
        :param sat_positions: 卫星位置数据
        """
        # 确保壳层索引有效
        if shell_no >= len(self.link_actors):
            return
            
        # 获取链路点和线段集合
        link_pts = self.link_actors[shell_no].linkVtkPts
        link_lines = self.link_actors[shell_no].linkVtkLines
        
        # 更新卫星点位置
        for i in range(len(sat_positions)):
            link_pts.SetPoint(
                i,
                sat_positions[i]["x"],
                sat_positions[i]["y"],
                sat_positions[i]["z"],
            )
        
        # 重置所有链路线段
        link_lines.Reset()

        # 填充链路数据
        for i in range(len(links)):
            e1 = links[i]["node_1"]
            e2 = links[i]["node_2"]
            # 必须将链路端点转换为点名称
            link_lines.InsertNextCell(2)
            link_lines.InsertCellPoint(e1)
            link_lines.InsertCellPoint(e2)

        # 标记点和线段已修改
        link_pts.Modified()
        link_lines.Modified()

        # 更新多边形数据
        self.link_actors[shell_no].linkPolyData.SetPoints(link_pts)
        self.link_actors[shell_no].linkPolyData.SetLines(link_lines)
        self.link_actors[shell_no].linkPolyData.Modified()

    def updateGstLinks(self, gst_links, gst_positions, sat_positions) -> None:
        """
        更新地面站链路
        
        :param gst_links: 地面站链路数据
        :param gst_positions: 地面站位置数据
        :param sat_positions: 卫星位置数据（按壳层组织的二维数组）
        """
        # 获取地面站链路点和线段集合
        gst_link_pts = self.gst_link_actor.gstLinkPoints
        gst_link_lines = self.gst_link_actor.gstLinkLines

        # 更新地面站点位置
        for i in range(len(gst_positions)):
            gst_link_pts.SetPoint(
                i,
                gst_positions[i]["x"],
                gst_positions[i]["y"],
                gst_positions[i]["z"],
            )

        # 更新卫星点位置
        num_points = len(gst_positions)
        
        for s in range(len(sat_positions)):
            for i in range(len(sat_positions[s])):
                gst_link_pts.SetPoint(
                    num_points,
                    sat_positions[s][i]["x"],
                    sat_positions[s][i]["y"],
                    sat_positions[s][i]["z"],
                )
                num_points += 1

        # 重置所有链路线段
        gst_link_lines.Reset()

        # 计算每个壳层的卫星数量前缀和，用于偏移计算
        shell_offsets = [len(gst_positions)]
        for s in range(len(sat_positions) - 1):
            shell_offsets.append(shell_offsets[-1] + len(sat_positions[s]))

        # 更新地面站链路
        for s in range(len(gst_links)):
            for i in range(len(gst_links[s])):
                # 地面站索引为负值
                e1 = gst_links[s][i]["gst"] * -1 - 1
                # 卫星索引为正值，需要加上地面站数量和前面壳层卫星数量的偏移
                e2 = gst_links[s][i]["sat"] + shell_offsets[s]
                
                # 添加链路
                gst_link_lines.InsertNextCell(2)
                gst_link_lines.InsertCellPoint(e1)
                gst_link_lines.InsertCellPoint(e2)

        # 标记点和线段已修改
        gst_link_pts.Modified()
        gst_link_lines.Modified()

        # 更新多边形数据
        self.gst_link_actor.gstLinkPolyData.SetPoints(gst_link_pts)
        self.gst_link_actor.gstLinkPolyData.SetLines(gst_link_lines)
        self.gst_link_actor.gstLinkPolyData.Modified()
