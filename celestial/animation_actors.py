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
    # 卫星3D模型相关
    satModels: typing.List = None  # 存储卫星3D模型的列表
    satModelActors: typing.List = None  # 存储卫星3D模型演员的列表
    satModelVisible: typing.List = None  # 存储卫星3D模型可见性的列表

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
        
        # 相机对象，用于LOD计算
        self.camera = None
        
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
        
        # 创建卫星3D模型
        self.createSatelliteModels(shell_no, shell_total_sats, sat_positions[shell_no], sat_colors[shell_no])

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
            for i in range(len(sat_positions[s])):
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
                e1 = gst_links[s][i]["gst"] *-1 -1
                e2 = gst_links[s][i]["sat"] + offset

                # 添加链路
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
        # 保存相机引用，用于LOD计算
        self.camera = self.renderer.GetActiveCamera()

        # 创建地球地图（轮廓）
        self.earthSource = vtk.vtkEarthSource()
        self.earthSource.SetRadius(self.earthRadius * 1.001)
        self.earthSource.SetOnRatio(1)
        
        # 更新地球轮廓
        self.earthSource.Update()

        # 创建映射器
        self.earthMapper = vtk.vtkPolyDataMapper()
        self.earthMapper.SetInputConnection(self.earthSource.GetOutputPort())

        # 创建演员
        self.earthActor = vtk.vtkActor()
        self.earthActor.SetMapper(self.earthMapper)

        # 设置颜色
        self.earthActor.GetProperty().SetColor(LANDMASS_OUTLINE_COLOR)
        self.earthActor.GetProperty().SetOpacity(EARTH_LAND_OPACITY)

        # 创建地球球体（推荐用TexturedSphereSource，避免经线对称问题）
        sphere = vtk.vtkTexturedSphereSource()
        sphere.SetRadius(self.earthRadius)
        sphere.SetThetaResolution(100)
        sphere.SetPhiResolution(100)
        
        # 加载纹理图像
        jpegReader = vtk.vtkJPEGReader()
        jpegReader.SetFileName(EARTH_TEXTURE_PATH)
        
        # 创建纹理对象
        texture = vtk.vtkTexture()
        texture.SetInputConnection(jpegReader.GetOutputPort())
        texture.InterpolateOn()
        
        # 创建映射器
        sphereMapper = vtk.vtkPolyDataMapper()
        sphereMapper.SetInputConnection(sphere.GetOutputPort())
        
        # 创建演员
        self.sphereActor = vtk.vtkActor()
        self.sphereActor.SetMapper(sphereMapper)
        self.sphereActor.SetTexture(texture)
        
        # 设置地球球体初始旋转，让南极方向正对（Z轴旋转180度）
        self.sphereActor.SetOrientation(0, 0, 180)
        
        # 设置不透明度
        self.sphereActor.GetProperty().SetOpacity(EARTH_OPACITY)
        
        # 添加到渲染器
        self.renderer.AddActor(self.earthActor)
        self.renderer.AddActor(self.sphereActor)

    def createSatelliteModels(self, shell_no: int, shell_total_sats: int, sat_positions, sat_color) -> None:
        """
        创建卫星3D模型（卫星主体+太阳能板+天线）
        
        :param shell_no: 壳层索引
        :param shell_total_sats: 壳层中的卫星总数
        :param sat_positions: 卫星位置数据
        :param sat_color: 卫星颜色
        """
        # 初始化模型列表
        self.shell_actors[shell_no].satModels = []
        self.shell_actors[shell_no].satModelActors = []
        self.shell_actors[shell_no].satModelVisible = [False] * shell_total_sats
        
        # 为每个卫星创建3D模型
        for i in range(shell_total_sats):
            # 创建卫星主体（圆柱体）
            bodySource = vtk.vtkCylinderSource()
            bodySource.SetHeight(SAT_MODEL_SIZE * 0.8)
            bodySource.SetRadius(SAT_MODEL_SIZE * 0.4)
            bodySource.SetResolution(16)  # 提高分辨率使其更圆滑
            
            # 创建太阳能板（扁平长方体）
            solarPanel1 = vtk.vtkCubeSource()
            solarPanel1.SetXLength(SAT_MODEL_SIZE * 2.5)  # 长
            solarPanel1.SetYLength(SAT_MODEL_SIZE * 0.05)  # 薄
            solarPanel1.SetZLength(SAT_MODEL_SIZE * 0.8)   # 宽
            
            solarPanel2 = vtk.vtkCubeSource()
            solarPanel2.SetXLength(SAT_MODEL_SIZE * 2.5)  # 长
            solarPanel2.SetYLength(SAT_MODEL_SIZE * 0.05)  # 薄
            solarPanel2.SetZLength(SAT_MODEL_SIZE * 0.8)   # 宽
            
            # 创建天线（圆锥体）
            antennaSource = vtk.vtkConeSource()
            antennaSource.SetHeight(SAT_MODEL_SIZE * 0.6)
            antennaSource.SetRadius(SAT_MODEL_SIZE * 0.2)
            antennaSource.SetResolution(12)  # 提高分辨率
            antennaSource.SetDirection(0, 1, 0)  # 指向Y轴正方向
            
            # 创建天线碟形接收器（扁平球体）
            dishSource = vtk.vtkSphereSource()
            dishSource.SetRadius(SAT_MODEL_SIZE * 0.3)
            dishSource.SetThetaResolution(16)
            dishSource.SetPhiResolution(16)
            dishSource.SetStartTheta(0)
            dishSource.SetEndTheta(180)  # 半球形
            
            # 创建变换过滤器，放置太阳能板
            panel1Transform = vtk.vtkTransform()
            panel1Transform.Translate(0, SAT_MODEL_SIZE * 0.8, 0)  # 放在主体右侧
            panel1Transform.RotateZ(90)  # 旋转使其垂直于主体
            
            panel1TransformFilter = vtk.vtkTransformPolyDataFilter()
            panel1TransformFilter.SetInputConnection(solarPanel1.GetOutputPort())
            panel1TransformFilter.SetTransform(panel1Transform)
            
            panel2Transform = vtk.vtkTransform()
            panel2Transform.Translate(0, -SAT_MODEL_SIZE * 0.8, 0)  # 放在主体左侧
            panel2Transform.RotateZ(90)  # 旋转使其垂直于主体
            
            panel2TransformFilter = vtk.vtkTransformPolyDataFilter()
            panel2TransformFilter.SetInputConnection(solarPanel2.GetOutputPort())
            panel2TransformFilter.SetTransform(panel2Transform)
            
            # 创建变换过滤器，放置天线
            antennaTransform = vtk.vtkTransform()
            antennaTransform.Translate(0, 0, SAT_MODEL_SIZE * 0.6)  # 放在主体顶部
            antennaTransform.RotateX(90)  # 旋转使其指向Z轴正方向
            
            antennaTransformFilter = vtk.vtkTransformPolyDataFilter()
            antennaTransformFilter.SetInputConnection(antennaSource.GetOutputPort())
            antennaTransformFilter.SetTransform(antennaTransform)
            
            # 创建变换过滤器，放置接收器
            dishTransform = vtk.vtkTransform()
            dishTransform.Translate(0, 0, -SAT_MODEL_SIZE * 0.6)  # 放在主体底部
            dishTransform.RotateX(180)  # 旋转使开口朝向地球
            
            dishTransformFilter = vtk.vtkTransformPolyDataFilter()
            dishTransformFilter.SetInputConnection(dishSource.GetOutputPort())
            dishTransformFilter.SetTransform(dishTransform)
            
            # 将所有部件组合成一个模型
            appendFilter = vtk.vtkAppendPolyData()
            appendFilter.AddInputConnection(bodySource.GetOutputPort())
            appendFilter.AddInputConnection(panel1TransformFilter.GetOutputPort())
            appendFilter.AddInputConnection(panel2TransformFilter.GetOutputPort())
            appendFilter.AddInputConnection(antennaTransformFilter.GetOutputPort())
            appendFilter.AddInputConnection(dishTransformFilter.GetOutputPort())
            
            # 创建映射器
            mapper = vtk.vtkPolyDataMapper()
            mapper.SetInputConnection(appendFilter.GetOutputPort())
            
            # 创建演员
            actor = vtk.vtkActor()
            actor.SetMapper(mapper)
            
            # 创建单独的映射器和演员，以便为不同部件设置不同颜色
            # 卫星主体
            bodyMapper = vtk.vtkPolyDataMapper()
            bodyMapper.SetInputConnection(bodySource.GetOutputPort())
            bodyActor = vtk.vtkActor()
            bodyActor.SetMapper(bodyMapper)
            bodyActor.GetProperty().SetColor(sat_color)  # 使用传入的颜色参数
            
            # 太阳能板1
            panel1Mapper = vtk.vtkPolyDataMapper()
            panel1Mapper.SetInputConnection(panel1TransformFilter.GetOutputPort())
            panel1Actor = vtk.vtkActor()
            panel1Actor.SetMapper(panel1Mapper)
            panel1Actor.GetProperty().SetColor(SAT_SOLAR_PANEL_COLOR)
            
            # 太阳能板2
            panel2Mapper = vtk.vtkPolyDataMapper()
            panel2Mapper.SetInputConnection(panel2TransformFilter.GetOutputPort())
            panel2Actor = vtk.vtkActor()
            panel2Actor.SetMapper(panel2Mapper)
            panel2Actor.GetProperty().SetColor(SAT_SOLAR_PANEL_COLOR)
            
            # 天线
            antennaMapper = vtk.vtkPolyDataMapper()
            antennaMapper.SetInputConnection(antennaTransformFilter.GetOutputPort())
            antennaActor = vtk.vtkActor()
            antennaActor.SetMapper(antennaMapper)
            antennaActor.GetProperty().SetColor(SAT_ANTENNA_COLOR)
            
            # 接收器
            dishMapper = vtk.vtkPolyDataMapper()
            dishMapper.SetInputConnection(dishTransformFilter.GetOutputPort())
            dishActor = vtk.vtkActor()
            dishActor.SetMapper(dishMapper)
            dishActor.GetProperty().SetColor(SAT_DISH_COLOR)
            
            # 创建一个组合演员
            assembly = vtk.vtkAssembly()
            assembly.AddPart(bodyActor)
            assembly.AddPart(panel1Actor)
            assembly.AddPart(panel2Actor)
            assembly.AddPart(antennaActor)
            assembly.AddPart(dishActor)
            
            # 添加材质效果到所有部件
            for part in [bodyActor, panel1Actor, panel2Actor, antennaActor, dishActor]:
                part.GetProperty().SetAmbient(0.3)
                part.GetProperty().SetDiffuse(0.7)
                part.GetProperty().SetSpecular(0.5)
                part.GetProperty().SetSpecularPower(20)
            
            # 初始位置设置
            if i < len(sat_positions):
                assembly.SetPosition(
                    sat_positions[i]["x"],
                    sat_positions[i]["y"],
                    sat_positions[i]["z"]
                )
                
                # 计算朝向地球中心的方向
                x = sat_positions[i]["x"]
                y = sat_positions[i]["y"]
                z = sat_positions[i]["z"]
                length = (x**2 + y**2 + z**2)**0.5
                if length > 0:
                    # 计算从卫星指向地球中心的向量
                    dx = -x/length
                    dy = -y/length
                    dz = -z/length
                    
                    # 计算旋转轴和角度
                    # 默认方向是(0,0,1)，需要旋转到(dx,dy,dz)
                    default_dir = [0, 0, 1]
                    target_dir = [dx, dy, dz]
                    
                    # 计算旋转轴（叉积）
                    axis = [
                        default_dir[1]*target_dir[2] - default_dir[2]*target_dir[1],
                        default_dir[2]*target_dir[0] - default_dir[0]*target_dir[2],
                        default_dir[0]*target_dir[1] - default_dir[1]*target_dir[0]
                    ]
                    
                    # 计算旋转角度（点积）
                    dot_product = default_dir[0]*target_dir[0] + default_dir[1]*target_dir[1] + default_dir[2]*target_dir[2]
                    angle = 180 * (1 - dot_product) / 3.14159
                    
                    # 应用旋转
                    if abs(axis[0]) + abs(axis[1]) + abs(axis[2]) > 0.001:  # 避免零向量
                        assembly.RotateWXYZ(angle, axis[0], axis[1], axis[2])
            
            # 初始状态为隐藏
            assembly.VisibilityOff()
            
            # 添加到渲染器
            self.renderer.AddActor(assembly)
            
            # 保存到列表
            self.shell_actors[shell_no].satModelActors.append(assembly)

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
        
        # 获取相机位置
        camera_pos = self.camera.GetPosition()

        # 更新每个卫星的位置
        for i in range(len(sat_positions)):
            # 卫星位置
            sat_x = sat_positions[i]["x"]
            sat_y = sat_positions[i]["y"]
            sat_z = sat_positions[i]["z"]
            
            # 计算卫星到相机的距离
            distance = ((sat_x - camera_pos[0])**2 + 
                        (sat_y - camera_pos[1])**2 + 
                        (sat_z - camera_pos[2])**2)**0.5
            
            # 根据距离决定使用点精灵还是3D模型
            use_model = distance < SAT_LOD_DISTANCE and i < len(in_bbox) and in_bbox[i]
            
            # 更新3D模型可见性和位置
            if shell_no < len(self.shell_actors) and hasattr(self.shell_actors[shell_no], 'satModelActors') and \
               self.shell_actors[shell_no].satModelActors and i < len(self.shell_actors[shell_no].satModelActors):
                model_actor = self.shell_actors[shell_no].satModelActors[i]
                
                # 更新模型位置
                model_actor.SetPosition(sat_x, sat_y, sat_z)
                
                # 计算朝向地球中心的方向
                length = (sat_x**2 + sat_y**2 + sat_z**2)**0.5
                if length > 0:
                    # 重置旋转，避免累积旋转错误
                    model_actor.SetOrientation(0, 0, 0)
                    
                    # 计算从卫星指向地球中心的向量
                    dx = -sat_x/length
                    dy = -sat_y/length
                    dz = -sat_z/length
                    
                    # 计算旋转轴和角度
                    default_dir = [0, 0, 1]
                    target_dir = [dx, dy, dz]
                    
                    # 计算旋转轴（叉积）
                    axis = [
                        default_dir[1]*target_dir[2] - default_dir[2]*target_dir[1],
                        default_dir[2]*target_dir[0] - default_dir[0]*target_dir[2],
                        default_dir[0]*target_dir[1] - default_dir[1]*target_dir[0]
                    ]
                    
                    # 计算旋转角度（点积）
                    dot_product = default_dir[0]*target_dir[0] + default_dir[1]*target_dir[1] + default_dir[2]*target_dir[2]
                    angle = 180 * (1 - dot_product) / 3.14159
                    
                    # 应用旋转
                    if abs(axis[0]) + abs(axis[1]) + abs(axis[2]) > 0.001:  # 避免零向量
                        model_actor.RotateWXYZ(angle, axis[0], axis[1], axis[2])
                
                # 更新模型可见性
                if use_model:
                    model_actor.VisibilityOn()
                    self.shell_actors[shell_no].satModelVisible[i] = True
                else:
                    model_actor.VisibilityOff()
                    self.shell_actors[shell_no].satModelVisible[i] = False
            
            # 更新点精灵位置 - 即使使用3D模型也保持点的位置正确，以便点击选择功能正常工作
            if i < len(in_bbox) and in_bbox[i]:
                # 活跃卫星 - 始终保持点的实际位置，但在使用3D模型时降低不透明度
                active_pts.SetPoint(i, sat_x, sat_y, sat_z)
                
                # 如果使用3D模型，将点的不透明度设为0（在UI层面处理）
                # 但保持点的位置正确，以便点击选择功能正常工作
                inactive_pts.SetPoint(i, 0, 0, 0)  # 非活跃点设为原点
            else:
                # 非活跃卫星
                inactive_pts.SetPoint(i, sat_x, sat_y, sat_z)
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

        # 注意：不再更新地面站位置，因为地面站是固定的

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
                # 地面站索引直接用gst字段，确保与点集一致
                e1 = gst_links[s][i]["gst"] *-1 -1
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
