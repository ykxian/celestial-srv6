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

5. **AnimationConstants（animation_constants.py）**
   - 常量定义模块
   - 提供所有视觉元素的颜色、大小、透明度等参数
   - 定义界面布局和性能相关常量

### 2.2 模块关系图

```
┌─────────────────────┐      ┌─────────────────────┐
│  AnimationConstants │◄─────┤     Animation       │
└─────────────────────┘      │  (核心控制模块)      │
         ▲                   └──────────┬──────────┘
         │                              │
         │                              │ 协调
         │ 引用                         ▼
┌────────┴──────────┐      ┌─────────────────────┐
│   AnimationUI     │◄─────┤  AnimationActors    │
│ (用户界面模块)     │      │ (可视化元素模块)     │
└────────┬──────────┘      └──────────┬──────────┘
         │                            │
         │ 交互                       │ 更新
         ▼                            ▼
┌─────────────────────┐      ┌─────────────────────┐
│    用户交互          │      │     3D渲染场景      │
└─────────────────────┘      └─────────────────────┘
         │                            ▲
         └────────────────────────────┘
                      影响

```

### 2.3 数据流向

1. **初始化流程**：
   - Animation模块创建并初始化其他模块实例
   - 从配置文件加载卫星和地面站数据
   - 设置初始仿真参数和状态

2. **更新循环**：
   - Animation模块更新仿真时间
   - 计算卫星新位置和链路状态
   - 通知AnimationActors更新视觉元素
   - 通知AnimationUI更新界面信息

3. **用户交互**：
   - AnimationUI接收用户输入
   - 处理选择和点击事件
   - 通知Animation模块执行相应操作

## 3. 功能详解

### 3.1 卫星可视化

#### 3.1.1 卫星显示
- 支持多个卫星壳层（Shell）同时显示
- 卫星以彩色点表示，大小可通过`SAT_POINT_SIZE`调整
- 不同壳层的卫星使用自动生成的不同颜色，通过seaborn颜色调色板实现
- 活跃卫星（在当前视图中）与非活跃卫星透明度不同，通过`SAT_OPACITY`和`SAT_INACTIVE_OPACITY`控制

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

### 3.6 状态信息显示

- 屏幕顶部显示全局信息：仿真时间、进度、活跃卫星数等
- 进度条直观显示仿真进度
- 实时更新链路数量和活跃卫星数量
- 支持自定义文本样式和位置，通过`TEXT_COLOR`、`TEXT_SIZE`等常量控制

### 3.7 交互功能

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

#### 4.3.3 SSH连接
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

**关键方法**：
- `__init__`：初始化Animation对象
- `makeRenderWindow`：创建渲染窗口和视觉元素
- `updateAnimation`：更新动画状态
- `updateRoutePath`：更新路由路径请求
- `displayRoutePath`：显示路由路径
- `showRoutePath`：计算并显示路由路径
- `clearRoutePath`：清除路由路径

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

**关键方法**：
- `createEarthActor`：创建地球模型
- `makeSatsActor`：创建活跃卫星视觉元素
- `makeInactiveSatsActor`：创建非活跃卫星视觉元素
- `makeLinkActors`：创建星间链路
- `makeGstActor`：创建地面站
- `makeGstLinkActor`：创建地面站链路
- `updateSatPositions`：更新卫星位置
- `updateLinks`：更新链路显示
- `updateGstLinks`：更新地面站链路

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

### 5.5 AnimationConstants模块（animation_constants.py）

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

## 8. 常见问题与解决方案

### 8.1 性能问题
- **问题**：大量卫星导致渲染卡顿
- **解决方案**：
  - 减小`SAT_POINT_SIZE`
  - 增加非活跃卫星的透明度
  - 降低地球模型精度
  - 减少链路显示数量
  - 使用`--no-links`参数禁用链路显示

### 8.2 交互问题
- **问题**：难以选中特定卫星
- **解决方案**：
  - 增大`SAT_POINT_SIZE`
  - 使用键盘快捷键选择卫星
  - 通过ID直接查找卫星

### 8.3 路由问题
- **问题**：路由路径不显示或显示不正确
- **解决方案**：
  - 确认API服务正常运行（默认URL为`http://127.0.0.1`）
  - 检查源节点和目标节点是否正确设置
  - 尝试重新选择源节点和目标节点
  - 按数字键1重置路由选择
  - 检查网络连接是否正常

## 9. 未来发展

### 9.1 计划功能
- 支持多种卫星轨道模型
- 添加卫星轨迹预测显示
- 增强路由可视化效果
- 支持3D模型替代点精灵
- 添加时间控制面板
- 支持自定义地球纹理

### 9.2 架构改进
- 引入事件系统，减少模块间直接依赖
- 优化渲染管线，提高性能
- 增强异常处理机制
- 添加单元测试和集成测试
- 改进路由API接口，支持更复杂的路由策略

---

*本文档基于Celestial项目代码分析，详细介绍了可视化系统的架构、功能和使用方法。如有问题或建议，请联系项目维护者。*