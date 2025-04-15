# Celestial 可视化界面功能总结

## 1. 系统概述

Celestial是一个卫星星座仿真系统，具有3D可视化功能，可以显示卫星轨道、地面站、星间链路等。该系统使用VTK（Visualization Toolkit）进行3D渲染，支持实时动画展示卫星运动和通信链路。

## 2. 可视化界面主要功能

### 2.1 卫星轨道与位置显示

- 支持多个卫星壳层（Shell）的同时显示
- 卫星以点的形式显示，大小为`SAT_POINT_SIZE`（默认8像素）
- 卫星状态可视化：活跃卫星与非活跃卫星透明度不同
- 使用不同颜色区分不同壳层的卫星

### 2.2 地球模型

- 显示地球球体，颜色为浅蓝色（`EARTH_BASE_COLOR`）
- 显示陆地轮廓，颜色为黑色（`LANDMASS_OUTLINE_COLOR`）
- 地球模型精度可通过`EARTH_SPHERE_POINTS`参数调整（默认5000点）

### 2.3 地面站显示

- 地面站以绿色点显示（`GST_COLOR`）
- 地面站大小为`GST_POINT_SIZE`（默认8像素）
- 显示地面站名称（如果提供）

### 2.4 链路可视化

- 星间链路（ISL）：黄棕色（`ISL_LINK_COLOR`），线宽为`ISL_LINE_WIDTH`
- 地面站链路（GSL）：绿色（`GST_LINK_COLOR`），线宽为`GST_LINE_WIDTH`
- 路径链路：紫色（`PATH_LINK_COLOR`），线宽为`PATH_LINE_WIDTH`
- 可通过命令行参数`--no-links`选择不显示链路

### 2.5 路由路径显示

- 显示从源节点到目标节点的路由路径
- 路径颜色为红色（`ROUTE_PATH_COLOR`）
- 路径线宽为`ROUTE_PATH_WIDTH`（默认4像素）
- 路径上显示箭头指示方向，箭头大小为`ROUTE_PATH_ARROW_SIZE`
- 通过HTTP API获取路由路径信息

### 2.6 状态信息显示

- 在屏幕上显示文本信息，如当前时间、仿真状态等
- 文本颜色为黑色（`TEXT_COLOR`），大小为`TEXT_SIZE`
- 显示进度条，宽度为`PROGRESS_BAR_WIDTH`，高度为`PROGRESS_BAR_HEIGHT`

## 3. 交互功能

### 3.1 点击获取信息

- 点击卫星或地面站可显示详细信息面板
- 信息面板背景色为浅灰色（`INFO_PANEL_BG_COLOR`）
- 面板包含节点ID、类型、位置等信息
- 面板右上角有关闭按钮

### 3.2 SSH连接功能

- 信息面板中包含SSH按钮
- 点击按钮可通过SSH连接到选中的卫星或地面站
- 使用`SSH_KEY_PATH`指定的密钥进行认证

### 3.3 路由路径查询

- 可选择源节点和目标节点，查看它们之间的路由路径
- 路径以高亮方式显示在3D场景中
- 支持卫星到卫星、卫星到地面站、地面站到卫星、地面站到地面站的路径查询

## 4. 配置选项

### 4.1 命令行参数

- `zip_file`：指定Celestial .zip配置文件路径
- `hosts`：指定主机地址列表
- `--no-links`：不显示星间链路
- `--frequency`：设置动画刷新频率（默认7）
- `-v`或`--verbose`：显示详细日志

### 4.2 视觉样式配置

- 通过常量定义各种视觉元素的颜色、大小、透明度等
- 背景颜色为白色（`BACKGROUND_COLOR`）
- 可调整卫星、地面站、链路的颜色和大小

### 4.3 性能配置

- 地球模型精度可调整（`EARTH_SPHERE_POINTS`）
- 动画刷新频率可通过命令行参数设置

## 5. 技术实现

### 5.1 多进程架构

- 使用Python的multiprocessing模块创建动画进程
- 通过Pipe进行进程间通信
- 主进程负责仿真计算，子进程负责可视化显示

### 5.2 API集成

- 通过HTTP API获取路由路径信息
- 默认API基础URL为`http://127.0.0.1`

### 5.3 VTK渲染管线

- 使用VTK库进行3D渲染
- 为场景中的每个对象配置渲染管线
- 支持点、线、文本等多种渲染对象

---

*注：本文档基于对animation.py和visualized_celestial.py代码的分析，总结了Celestial项目的可视化界面功能。*