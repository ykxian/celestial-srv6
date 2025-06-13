# Celestial 卫星星座可视化系统

## 1. 系统概述

Celestial是一个先进的卫星星座仿真与可视化系统，专为卫星网络研究和教育设计。系统采用模块化架构，通过VTK（Visualization Toolkit）提供高质量的3D实时渲染，能够精确模拟卫星轨道运动、星间通信以及地面站连接。本文档详细介绍了可视化系统的架构、功能、使用方法及各模块间的关系。

## 2. 模块架构

Celestial的可视化系统由以下五个核心模块组成，每个模块负责特定功能：

### 2.1 模块概述

1. **Animation（animation.py）**
   - 核心控制模块，负责协调其他组件
   - 管理仿真时间和状态
   - 处理数据流分发和事件协调
   - 处理SRv6路由路径的显示和更新

2. **AnimationActors（animation_actors.py）**
   - 可视化元素管理模块
   - 负责创建、更新和管理所有3D渲染对象
   - 处理卫星、链路、地面站等视觉元素的渲染

3. **AnimationUI（animation_ui.py）**
   - 用户界面和交互处理模块
   - 管理信息面板、进度条和文本显示
   - 处理鼠标点击和键盘输入事件

4. **AnimationConstellation（animation_constellation.py）**
   - 星座模型和路由处理模块
   - 负责卫星位置计算和更新
   - 处理路由请求和路径计算

5. **SRv6RouteServer（srv6_route_server.py）**
   - SRv6路由服务器模块
   - 接收和处理SRv6路由信息
   - 解析IPv6地址获取节点信息
   - 将路由数据转发给动画系统

6. **AnimationConstants（animation_constants.py）**
   - 常量定义模块
   - 提供所有视觉元素的颜色、大小、透明度等参数
   - 定义界面布局和性能相关常量

### 2.2 模块关系图

```
┌─────────────────────┐      ┌─────────────────────┐      ┌─────────────────────┐
│  AnimationConstants │◄─────┤     Animation       │◄─────┤  SRv6RouteServer   │
└─────────────────────┘      │  (核心控制模块)      │      │  (路由服务器模块)   │
         ▲                   └──────────┬──────────┘      └─────────────────────┘
         │                              │                          ▲
         │                              │ 协调                      │
         │ 引用                         ▼                          │
┌────────┴──────────┐      ┌─────────────────────┐                │
│   AnimationUI     │◄─────┤  AnimationActors    │                │
│ (用户界面模块)     │      │ (可视化元素模块)     │                │
└────────┬──────────┘      └──────────┬──────────┘                │
         │                            │                          │
         │ 交互                       │ 更新                      │
         ▼                            ▼                          │
┌─────────────────────┐      ┌─────────────────────┐            │
│    用户交互          │      │     3D渲染场景      │            │
└─────────────────────┘      └─────────────────────┘            │
         │                            ▲                          │
         └────────────────────────────┘                          │
                      影响                                       │
                                                               │
┌─────────────────────┐                                         │
│ SRv6DynamicRouter  │─────────────────────────────────────────┘
│  (路由管理模块)     │            发送路由数据
└─────────────────────┘

```

### 2.3 数据流向

1. **初始化流程**：
   - Animation模块创建并初始化其他模块实例
   - 从配置文件加载卫星和地面站数据
   - 设置初始仿真参数和状态
   - 创建SRv6RouteServer并建立与Animation的通信管道

2. **更新循环**：
   - Animation模块更新仿真时间
   - 计算卫星新位置和链路状态
   - 通知AnimationActors更新视觉元素
   - 通知AnimationUI更新界面信息

3. **用户交互**：
   - AnimationUI接收用户输入
   - 处理选择和点击事件
   - 通知Animation模块执行相应操作

4. **SRv6路由数据流**：
   - SRv6DynamicRouter监控IPv6流量并生成路由信息
   - 路由信息通过HTTP POST请求发送到SRv6RouteServer
   - SRv6RouteServer解析IPv6地址，获取节点信息
   - 路由数据通过multiprocessing.Pipe发送到Animation模块
   - Animation模块接收数据并在3D场景中显示路由路径

## 3. 功能详解

### 3.1 卫星可视化

#### 3.1.1 卫星显示
- 支持多个卫星壳层（Shell）同时显示
- 卫星以彩色点表示，大小可通过`SAT_POINT_SIZE`调整
- 不同壳层的卫星使用自动生成的不同颜色，通过seaborn颜色调色板实现
- 活跃卫星（在当前视图中）与非活跃卫星透明度不同，通过`SAT_OPACITY`和`SAT_INACTIVE_OPACITY`控制
- 支持基于距离的LOD（细节层次）显示：
  - 近距离查看时显示详细的卫星3D模型（包含主体、太阳能板、天线和接收器）
  - 远距离查看时显示简单的点精灵，提高渲染性能
  - LOD切换距离通过`SAT_LOD_DISTANCE`常量控制（默认为15,000,000米）
  - 只有在活跃区域内且距离足够近的卫星才会显示3D模型
  - 卫星模型自动朝向地球中心，模拟真实卫星姿态

#### 3.1.2 卫星信息
- 点击卫星显示详细信息面板
- 信息包括：卫星ID、壳层号、IPv4/IPv6地址、位置坐标
- 支持通过SSH连接到选中卫星

### 3.2 地球模型

- 高精度地球球体模型，支持旋转动画
- 使用纹理贴图增强视觉效果，纹理路径通过`EARTH_TEXTURE_PATH`指定
- 显示陆地轮廓，增强视觉效果
- 支持自定义地球颜色和透明度，通过`EARTH_OPACITY`和`EARTH_LAND_OPACITY`控制

### 3.3 地面站功能

- 地面站以特殊颜色（默认绿色`GST_COLOR`）标记
- 显示地面站名称和位置信息
- 点击地面站显示详细信息，包括ID、名称、IP地址
- 支持通过SSH连接到地面站

### 3.4 链路可视化

- **星间链路（ISL）**：显示卫星之间的通信连接，颜色通过seaborn调色板自动生成
- **地面站链路（GSL）**：显示卫星与地面站之间的连接，使用`GST_LINK_COLOR`
- **路由路径**：高亮显示数据包传输路径，使用`ROUTE_PATH_COLOR`
- 所有链路类型支持自定义颜色、线宽和透明度
- 可通过命令行参数`--no-links`或界面控制开关链路显示

### 3.5 路由功能

- 支持右键选择源节点和目标节点
- 通过HTTP API自动计算并显示最优路由路径
- 路径以高亮颜色显示，并带有方向箭头
- 支持四种路由类型：卫星到卫星、卫星到地面站、地面站到卫星、地面站到地面站
- 路径实时更新，随卫星位置变化而调整，更新频率受`ROUTE_MIN_UPDATE_INTERVAL`控制
- 路由请求失败时自动回退到直接连接路径

### 3.6 SRv6路由可视化

- 支持IPv6分段路由(SRv6)路径的实时可视化
- 通过独立的SRv6路由服务器(SRv6RouteServer)接收路由信息
- 路由路径使用蓝色高亮显示，与普通路由路径区分
- 显示完整的SRv6路径，包括源节点、目标节点和所有中间节点
- 支持路径上的方向箭头指示数据流向
- 路径自动更新，随卫星位置变化而调整
- 支持多线程安全的路径更新机制，确保渲染线程安全

### 3.7 状态信息显示

- 屏幕顶部显示全局信息：仿真时间、进度、活跃卫星数等
- 进度条直观显示仿真进度
- 实时更新链路数量和活跃卫星数量
- 支持自定义文本样式和位置，通过`TEXT_COLOR`、`TEXT_SIZE`等常量控制

### 3.8 交互功能

- 鼠标左键点击选择对象（卫星或地面站）
- 鼠标右键设置路由源点和目标点
- 鼠标滚轮缩放视图
- 鼠标拖拽旋转视图
- 键盘快捷键控制仿真（如数字键1重置路由路径选择）

## 4. 使用指南

### 4.1 启动系统

```bash
# 基本启动命令
python visualized_celestial.py <配置文件路径>

# 完整参数示例
python visualized_celestial.py config.zip 127.0.0.1 --no-links --frequency 10 -v
```

### 4.2 命令行参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `zip_file` | Celestial配置文件路径 | 必填 |
| `hosts` | 主机地址列表 | 127.0.0.1 |
| `--no-links` | 不显示星间链路 | 默认显示 |
| `--frequency` | 动画刷新频率(Hz) | 7 |
| `-v`或`--verbose` | 显示详细日志 | 默认关闭 |

### 4.3 交互操作说明

#### 4.3.1 基本操作
- **视图控制**：
  - 鼠标左键拖拽：旋转视图
  - 鼠标右键拖拽：平移视图
  - 鼠标滚轮：缩放视图
  - 按住Shift+左键拖拽：在XY平面平移
  - 按住Ctrl+左键拖拽：在Z轴方向平移

- **对象选择**：
  - 左键点击卫星或地面站：显示详细信息
  - 点击信息面板关闭按钮：关闭信息面板
  - 点击空白区域：取消选择

#### 4.3.2 路由操作
1. 右键点击第一个节点（源节点）
2. 右键点击第二个节点（目标节点）
3. 系统自动计算并显示路由路径
4. 路径将随卫星位置变化而更新
5. 点击空白区域或按数字键1取消路由显示

#### 4.3.3 SRv6路由可视化
1. 确保SRv6RouteServer已正确启动（在visualized_celestial.py中自动启动）
2. 配置SRv6DynamicRouter将路由数据发送到可视化系统（默认地址为http://localhost:8080/api/route）
3. 当SRv6路由建立时，系统会自动接收路由数据并在3D场景中显示
4. SRv6路由路径以蓝色高亮显示，与普通路由路径区分
5. 路径上的箭头指示数据流向
6. 路径会随卫星位置变化自动更新

#### 4.3.4 SSH连接
1. 左键点击卫星或地面站
2. 在信息面板中点击"SSH"按钮
3. 系统自动打开终端并建立SSH连接
4. 默认使用`SSH_KEY_PATH`指定的密钥进行认证

### 4.4 自定义配置

可以通过修改`animation_constants.py`文件自定义视觉效果：

```python
# 卫星点大小
SAT_POINT_SIZE = 10  # 增大卫星点大小

# 卫星透明度
SAT_OPACITY = 1.0  # 活跃卫星透明度
SAT_INACTIVE_OPACITY = 0.5  # 非活跃卫星透明度

# 链路样式
ISL_LINK_COLOR = (0.9, 0.5, 0.1)  # 星间链路颜色
ISL_LINK_OPACITY = 1.0  # 星间链路透明度
ISL_LINE_WIDTH = 2  # 增加线宽

# 地面站链路样式
GST_LINK_COLOR = (0.5, 0.9, 0.5)  # 地面站链路颜色
GST_LINK_OPACITY = 0.75  # 地面站链路透明度
GST_LINE_WIDTH = 2  # 地面站链路线宽

# 路由路径样式
ROUTE_PATH_COLOR = (1.0, 0.0, 0.0)  # 路由路径颜色
ROUTE_PATH_OPACITY = 1.0  # 路由路径透明度
ROUTE_PATH_WIDTH = 4  # 路由路径线宽
ROUTE_PATH_ARROW_SIZE = 12  # 路由路径箭头大小
```

## 5. 模块详解

### 5.1 Animation模块（animation.py）

核心控制模块，负责协调其他组件的工作。

**主要功能**：
- 初始化和管理仿真环境
- 更新卫星位置和链路状态
- 处理用户交互事件
- 协调其他模块的工作
- 管理路由路径的请求和显示
- 处理SRv6路由路径的显示和更新

**关键方法**：
- `__init__`：初始化Animation对象
- `makeRenderWindow`：创建渲染窗口和视觉元素
- `updateAnimation`：更新动画状态
- `updateRoutePath`：更新路由路径请求
- `displayRoutePath`：显示路由路径
- `showRoutePath`：计算并显示路由路径
- `clearRoutePath`：清除路由路径
- `displaySRv6RoutePath`：显示SRv6路由路径
- `clearSRv6RoutePath`：清除SRv6路由路径
- `calculateIPv6`：根据shell和node_id计算IPv6地址

**与其他模块的关系**：
- 持有AnimationUI、AnimationActors和AnimationConstellation的实例
- 向AnimationActors提供数据更新
- 接收AnimationUI的交互事件
- 通过进程间通信与AnimationConstellation交换数据

### 5.2 AnimationActors模块（animation_actors.py）

负责管理所有可视化元素（演员）。

**主要功能**：
- 创建和管理卫星、地面站、链路等视觉元素
- 更新视觉元素的位置和属性
- 处理渲染管线配置
- 管理卫星LOD（细节层次）显示逻辑

**关键方法**：
- `createEarthActor`：创建地球模型
- `makeSatsActor`：创建活跃卫星视觉元素
- `makeInactiveSatsActor`：创建非活跃卫星视觉元素
- `makeLinkActors`：创建星间链路
- `makeGstActor`：创建地面站
- `makeGstLinkActor`：创建地面站链路
- `createSatelliteModels`：创建卫星3D模型（使用实例化渲染）
- `updateSatPositions`：更新卫星位置和LOD显示状态
- `updateLinks`：更新链路显示
- `updateGstLinks`：更新地面站链路

**卫星LOD（细节层次）显示**：
- 系统实现了基于距离的LOD机制，在近距离查看时显示详细的卫星3D模型，远距离时显示简单的点精灵
- 卫星3D模型包含主体（圆柱体）、太阳能板（扁平长方体）、天线（圆锥体）和接收器（半球体）
- LOD切换基于两个严格条件：
  1. 卫星必须在活跃区域内（in_bbox为True）
  2. 卫星到相机的距离必须小于阈值（由`SAT_LOD_DISTANCE`常量定义，默认为15,000,000米）
- 使用实例化渲染（vtkGlyph3D）优化性能，避免为每个卫星创建单独的模型
- 通过可见性数组（Visibility）控制哪些卫星显示3D模型，哪些显示为点精灵
- 卫星模型自动朝向地球中心，模拟真实卫星姿态控制
- 点精灵和3D模型可以同时显示，确保在任何距离都有良好的可视化效果

**与其他模块的关系**：
- 被Animation模块调用和控制
- 使用AnimationConstants中定义的常量

### 5.3 AnimationUI模块（animation_ui.py）

处理用户界面和交互。

**主要功能**：
- 创建和管理信息面板、文本显示和进度条
- 处理鼠标和键盘事件
- 显示节点详细信息

**关键方法**：
- `makeInfoTextActors`：创建信息文本
- `updateInfoText`：更新信息显示
- `makeProgressBar`：创建进度条
- `updateProgressBar`：更新进度条
- `makeInfoPanel`：创建信息面板
- `updateSatelliteInfoPanel`：更新卫星信息面板
- `updateGroundStationInfoPanel`：更新地面站信息面板
- `handleClick`：处理左键点击事件
- `handleRightClick`：处理右键点击（路由选择）
- `handleKeyPress`：处理键盘事件
- `executeSSHCommand`：执行SSH连接命令

**与其他模块的关系**：
- 持有对Animation的引用
- 向Animation报告用户交互事件
- 使用AnimationConstants中定义的常量

### 5.4 AnimationConstellation模块（animation_constellation.py）

管理星座模型和路由请求。

**主要功能**：
- 更新卫星位置
- 处理路由请求
- 通过HTTP API计算最优路径

**关键方法**：
- `step`：更新星座状态
- `get_route_path`：获取路由路径
- `handle_control_message`：处理来自Animation的控制消息
- `_get_node_info`：获取节点的shell和ID信息

**与其他模块的关系**：
- 被Animation模块通过进程间通信调用
- 提供路由数据给Animation模块
- 使用HTTP API获取路由信息

### 5.5 SRv6RouteServer模块（srv6_route_server.py）

负责接收和处理SRv6路由信息，并将其传递给动画系统进行可视化。

**主要功能**：
- 提供HTTP服务器接收SRv6路由数据
- 解析IPv6地址获取节点信息
- 处理路由数据并转发给动画系统
- 维护路由数据的状态和历史记录

**关键类**：
- `SRv6RouteServer`：主服务器类，管理HTTP服务器和动画连接
- `SRv6RouteHandler`：HTTP请求处理器，处理GET和POST请求
- `SRv6RouteData`：路由数据结构，存储和处理路由信息

**关键方法**：
- `start`：启动SRv6路由服务器
- `stop`：停止服务器
- `set_animation_conn`：设置与动画系统的连接
- `do_POST`：处理POST请求，接收路由信息
- `_parse_ipv6_to_node_info`：解析IPv6地址获取节点信息

**与其他模块的关系**：
- 通过multiprocessing.Pipe与Animation模块通信
- 接收来自SRv6DynamicRouter的路由数据
- 向Animation模块发送路由路径信息

### 5.6 AnimationConstants模块（animation_constants.py）

定义所有常量。

**主要内容**：
- 颜色定义（卫星、链路、地球等）
- 大小和透明度设置
- 界面布局参数
- 性能相关常量
- 路由更新相关常量
- SSH连接相关常量

**与其他模块的关系**：
- 被所有其他模块引用
- 提供统一的常量定义

## 6. 性能优化

### 6.1 渲染优化
- 使用点精灵（vtkPointSprite）减少卫星渲染开销
- 实现基于距离的LOD（细节层次）机制：
  - 近距离查看时显示详细的卫星3D模型
  - 远距离查看时显示简单的点精灵
  - 使用实例化渲染（vtkGlyph3D）优化3D模型显示性能
  - 通过可见性数组动态控制每个卫星的显示方式
  - 严格的LOD切换条件确保只有必要的卫星显示为3D模型
- 非活跃卫星使用透明度降低渲染负担
- 路由路径节点数量限制，防止过长路径导致性能问题
- 使用纹理贴图提高地球渲染质量和性能

### 6.2 计算优化
- 使用列表推导式优化活跃卫星和链路计算
- 避免重复计算，如在updateInfoText方法中接受预计算的参数
- 路由请求设置最小更新间隔，避免频繁请求
- 路由请求失败时使用回退机制，确保系统稳定性

### 6.3 交互优化
- 使用vtkCellPicker提高选择精度
- 信息面板延迟创建，减少初始化时间
- 按需更新视觉元素
- 路由请求异步处理，避免阻塞UI线程

## 7. 扩展开发

### 7.1 添加新的视觉元素

```python
# 在AnimationActors类中添加新方法
def createNewVisualElement(self, data):
    # 创建点/线/多边形数据
    points = vtk.vtkPoints()
    # 添加点数据...
    
    # 创建单元
    cells = vtk.vtkCellArray()
    # 设置单元...
    
    # 创建PolyData
    polyData = vtk.vtkPolyData()
    polyData.SetPoints(points)
    polyData.SetPolys(cells)
    
    # 创建Mapper和Actor
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputData(polyData)
    
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    # 设置属性...
    
    # 添加到渲染器
    self.renderer.AddActor(actor)
    
    return actor
```

### 7.2 添加新的交互功能

```python
# 在AnimationUI类中添加新方法
def handleMiddleClick(self, obj, event):
    """处理鼠标中键点击事件"""
    # 获取点击位置
    clickPos = self.interactor.GetEventPosition()
    
    # 执行拾取操作
    self.picker.Pick(clickPos[0], clickPos[1], 0, self.renderer)
    
    # 处理拾取结果
    # ...
    
    # 通知Animation模块
    self.animation.onMiddleClick(pickedObject)
```

### 7.3 自定义路由算法

可以通过修改AnimationConstellation模块中的路由请求方法，实现自定义路由算法：

```python
def get_route_path(self, source_index, target_index):
    """使用自定义算法计算路由路径"""
    # 实现自定义路由算法
    # ...
    
    # 返回路径节点列表
    return path_nodes
```

### 7.4 自定义SRv6路由可视化

可以通过修改SRv6RouteServer和Animation模块，实现自定义的SRv6路由可视化效果：

```python
# 在srv6_route_server.py中自定义路由数据处理
class SRv6RouteHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        # 接收路由数据
        route_data = json.loads(post_data.decode('utf-8'))
        
        # 自定义数据处理逻辑
        # ...
        
        # 发送到动画系统
        animation_conn = self.get_animation_conn()
        if animation_conn:
            animation_conn.send({
                "type": "srv6_route",
                "path_nodes": path_nodes,
                # 添加自定义属性
                "custom_property": value
            })

# 在animation.py中自定义路由显示效果
def displaySRv6RoutePath(self, path_nodes, **kwargs):
    # 获取自定义属性
    custom_property = kwargs.get("custom_property")
    
    # 根据自定义属性调整显示效果
    # 例如修改颜色、线宽、箭头大小等
    # ...
    
    # 显示路径
    self.displayRoutePath(path_nodes, is_srv6=True)
```

## 8. 常见问题与解决方案

### 8.1 性能问题

| 问题 | 解决方案 |
|------|----------|
| 帧率下降 | 1. 减少同时显示的卫星数量<br>2. 降低地球纹理分辨率<br>3. 关闭不必要的视觉效果<br>4. 检查是否有内存泄漏 |
| 内存占用过高 | 1. 减少卫星和地面站数量<br>2. 优化纹理和模型<br>3. 检查是否有资源未正确释放 |
| 启动时间过长 | 1. 使用预计算的轨道数据<br>2. 优化配置文件加载过程<br>3. 延迟加载非关键资源 |

### 8.2 显示问题

| 问题 | 解决方案 |
|------|----------|
| 卫星位置不准确 | 1. 检查TLE数据是否最新<br>2. 验证时间设置是否正确<br>3. 检查坐标转换计算 |
| 链路显示异常 | 1. 检查链路计算逻辑<br>2. 验证可见性判断条件<br>3. 调整链路更新频率 |
| 地球纹理失真 | 1. 检查纹理图像格式<br>2. 验证UV映射是否正确<br>3. 调整球体细分级别 |
| SRv6路由路径不显示 | 1. 检查SRv6RouteServer是否正常运行<br>2. 验证路由数据是否正确发送到服务器<br>3. 检查IPv6地址解析是否正确<br>4. 确认Animation模块是否正确接收路由数据 |

### 8.3 交互问题

| 问题 | 解决方案 |
|------|----------|
| 选择卫星困难 | 1. 调整选择碰撞范围<br>2. 实现智能选择逻辑<br>3. 添加卫星搜索功能 |
| 相机控制不流畅 | 1. 调整相机移动速度<br>2. 检查输入事件处理<br>3. 优化相机更新逻辑 |
| 界面响应延迟 | 1. 减少UI更新频率<br>2. 优化事件处理队列<br>3. 将耗时操作移至后台线程 |

### 8.4 SRv6路由问题

| 问题 | 解决方案 |
|------|----------|
| 路由服务器无响应 | 1. 检查SRv6RouteServer端口配置<br>2. 验证HTTP服务是否正常启动<br>3. 检查网络连接和防火墙设置 |
| 路由路径计算错误 | 1. 检查IPv6地址解析逻辑<br>2. 验证节点索引映射是否正确<br>3. 确认路由数据格式符合要求 |
| 路由更新不及时 | 1. 调整路由更新频率<br>2. 检查进程间通信管道是否畅通<br>3. 优化路由数据处理逻辑 |

## 9. 未来发展

### 9.1 计划功能

1. **高级路由可视化**：显示路由协议详细信息和路由决策过程
2. **流量模拟**：可视化网络流量和拥塞情况
3. **故障模拟**：模拟链路或节点故障及其对网络的影响
4. **多层次可视化**：支持物理层、链路层、网络层等多层次可视化
5. **历史数据回放**：记录和回放历史状态数据
6. **SRv6路由优化**：支持更复杂的SRv6路由策略和路径优化算法
7. **多路径SRv6可视化**：同时显示多条SRv6路由路径及其比较
8. **SRv6性能指标**：实时显示SRv6路由的延迟、带宽等性能指标

### 9.2 技术改进

1. **性能优化**：提高大规模卫星网络的渲染性能
2. **WebGL支持**：开发基于WebGL的浏览器版本
3. **分布式架构**：支持分布式部署和多用户协作
4. **AI辅助分析**：集成AI算法辅助网络分析和优化
5. **VR/AR支持**：开发虚拟现实和增强现实版本
6. **SRv6路由服务器集群**：支持高可用性和负载均衡的SRv6路由服务器集群
7. **实时路由分析**：提供SRv6路由路径的实时分析和优化建议

---

*本文档基于Celestial项目代码分析，详细介绍了可视化系统的架构、功能和使用方法。如有问题或建议，请联系项目维护者。*