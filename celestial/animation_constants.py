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

"""常量定义，用于动画模块"""

EARTH_RADIUS_M = 6371000  # radius of Earth in meters

# API相关常量
API_BASE_URL = "http://127.0.0.1"  # API基础URL

LANDMASS_OUTLINE_COLOR = (0.0, 0.0, 0.0)  # black, best contrast
EARTH_LAND_OPACITY = 1.0

EARTH_OPACITY = 1.0

BACKGROUND_COLOR = (1.0, 1.0, 1.0)  # white

# SAT_COLOR = (1.0, 0.0, 0.0)  # red, color of satellites
SAT_OPACITY = 1.0
SAT_INACTIVE_OPACITY = 0.5

GST_COLOR = (0.0, 1.0, 0.0)  # green, color of groundstations
GST_OPACITY = 1.0

ISL_LINK_COLOR = (0.9, 0.5, 0.1)  # yellow-brown, satellite-satellite links
ISL_LINK_OPACITY = 1.0
ISL_LINE_WIDTH = 1  # how wide to draw line in pixels

GST_LINK_COLOR = (0.5, 0.9, 0.5)  # greenish? satellite-groundstation links
GST_LINK_OPACITY = 0.75
GST_LINE_WIDTH = 2  # how wide to draw line in pixels

PATH_LINK_COLOR = (0.8, 0.2, 0.8)  # purpleish? path links
PATH_LINK_OPACITY = 0.7
PATH_LINE_WIDTH = 13  # how wide to draw line in pixels

# 地球纹理相关常量
EARTH_TEXTURE_PATH = "/home/ubuntu/celestial/celestial/earth_texture.jpg"  # 地球纹理图像路径

SAT_POINT_SIZE = 8  # how big satellites are in (probably) screen pixels
GST_POINT_SIZE = 8  # how big ground points are in (probably) screen pixels

# 卫星LOD（Level of Detail）相关常量
SAT_LOD_DISTANCE = 15000000  # 卫星模型切换距离阈值（米）
SAT_MODEL_SIZE = 100000  # 卫星模型大小（米）- 减小尺寸
SAT_ANTENNA_SIZE = 70000  # 卫星天线大小（米）- 减小尺寸
SAT_ANTENNA_COLOR = (0.9, 0.9, 0.0)  # 卫星天线颜色（黄色）
SAT_SOLAR_PANEL_COLOR = (0.1, 0.1, 0.6)  # 太阳能板颜色（深蓝色）
SAT_DISH_COLOR = (0.8, 0.8, 0.8)  # 接收器颜色（银色）

SECONDS_PER_DAY = 86400  # number of seconds per earth rotation (day)

# 文本显示相关常量
TEXT_COLOR = (0.0, 0.0, 0.7)  # 深蓝色文本，在浅色和深色背景上都有良好的可见性
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

# SRv6路由路径显示相关常量
SRV6_ROUTE_PATH_COLOR = (0.0, 0.3, 1.0)  # 蓝色SRv6路径
SRV6_ROUTE_PATH_OPACITY = 1.0  # SRv6路径透明度
SRV6_ROUTE_PATH_WIDTH = 5  # SRv6路径线宽
SRV6_ROUTE_PATH_ARROW_SIZE = 14  # SRv6箭头大小

# 路由更新相关常量
ROUTE_MIN_UPDATE_INTERVAL = 2.0  # 路由最小更新间隔（秒）
ROUTE_RESET_DURATION = 3.0  # 路由重置状态持续时间（秒）

# SSH按钮相关常量
INFO_PANEL_SSH_BTN_WIDTH = 80  # SSH按钮宽度
INFO_PANEL_SSH_BTN_HEIGHT = 25  # SSH按钮高度
INFO_PANEL_SSH_BTN_COLOR = (0.2, 0.6, 0.8)  # SSH按钮颜色（蓝色）
INFO_PANEL_SSH_BTN_TEXT_COLOR = (1.0, 1.0, 1.0)  # SSH按钮文本颜色（白色）
SSH_KEY_PATH = "~/id_ed25519"  # SSH密钥路径
