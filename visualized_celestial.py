#
# This file is part of Celestial (https://github.com/OpenFogStack/celestial).
# Copyright (c) 2024 Tobias Pfandzelter, The OpenFogStack Team.
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

"""
这是带有可视化界面的 Celestial 仿真协调器。它读取 Celestial .zip 文件
并根据文件中的配置运行仿真，同时显示卫星轨迹的 3D 可视化。

前提条件
-------------

确保安装了所有必要的依赖项。可以使用 pip 在虚拟环境中安装：

    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    pip install -r requirements-animation.txt

使用方法
-----

    python3 visualized_celestial.py [celestial.zip] [host1_addr] [host2_addr] ... [hostN_addr]

可选参数：
    --no-links: 不显示卫星间链路
    --frequency: 设置动画刷新频率（默认：7）
"""

import sys
import os
import time
import argparse
import multiprocessing
import threading
import logging
import concurrent.futures
import signal
import typing
import json

import celestial.zip_serializer
import celestial.config
import celestial.animation
import celestial.host
import celestial.types
import celestial.proto_util
import proto.celestial.celestial_pb2
import proto.celestial.celestial_pb2_grpc

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="Celestial simulation coordinator with visualization interface")
    
    parser.add_argument(
        "zip_file",
        type=str,
        help="Path to Celestial .zip file"
    )
    
    parser.add_argument(
        "hosts",
        type=str,
        nargs="+",
        help="List of host addresses in format host:port or just host (default port 1969 will be used)"
    )
    
    parser.add_argument(
        "--no-links",
        action="store_true",
        help="Do not display inter-satellite links"
    )
    
    parser.add_argument(
        "--frequency",
        type=int,
        default=7,
        help="Animation refresh frequency (default: 7)"
    )
    
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show detailed logs"
    )
    
    return parser.parse_args()

def start_animation(conn, draw_links, frequency):
    """启动动画进程"""
    # 只创建并启动动画，AnimationConstellation 已在主进程中创建
    
    # 创建Animation对象，确保使用相同的连接对象
    animation = celestial.animation.Animation(conn, draw_links, frequency)
    return animation

def main():
    """主函数"""
    args = parse_args()
    
    # 设置日志级别和编码
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', encoding='utf-8')
    else:
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', encoding='utf-8')
    
    # 读取 zip 文件
    try:
        serializer = celestial.zip_serializer.ZipDeserializer(args.zip_file)
        config = serializer.config()
        if config is None:
            logging.error("Configuration file is empty")
            sys.exit(1)
    except FileNotFoundError:
        logging.error(f"File not found: {args.zip_file}")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Unable to read Celestial .zip file: {e}")
        sys.exit(1)
    
    # 处理主机地址
    host_addrs = args.hosts
    DEFAULT_PORT = 1969
    
    for i in range(len(host_addrs)):
        if ":" not in host_addrs[i]:
            host_addrs[i] = f"{host_addrs[i]}:{DEFAULT_PORT}"
    
    # 创建主机连接
    hosts: typing.List[celestial.host.Host] = [
        celestial.host.Host(num=i, addr=host_addrs[i]) for i in range(len(host_addrs))
    ]
    
    # 创建多进程通信管道
    parent_conn, child_conn = multiprocessing.Pipe()
    
    # 创建动画星座对象（用于更新动画）
    print("visualized_celestial: 创建动画星座对象")
    animation_constellation = celestial.animation.AnimationConstellation(
        config, 
        parent_conn,
    )
    
    
    # 初始化SRv6路由服务器
    from celestial.srv6_route_server import SRv6RouteServer
    from celestial.srv6_route_server import SRv6RouteHandler
    
    # 使用parent_conn初始化SRv6路由服务器
    srv6_route_server = SRv6RouteServer(port=8080, animation_conn=parent_conn)
    srv6_route_server.start()
    
    # 确认连接对象是否一致
    if id(SRv6RouteServer.animation_conn_instance) == id(parent_conn):
        print("visualized_celestial: 连接对象ID一致，消息传递应该正常工作")
    else:
        print("visualized_celestial: 警告 - 连接对象ID不一致，可能导致消息传递问题")
    
    # 创建并启动动画进程
    animation_process = multiprocessing.Process(
        target=start_animation,
        args=(child_conn, not args.no_links, args.frequency)
    )
    animation_process.daemon = True  # 设置为守护进程，主进程结束时自动终止
    animation_process.start()
    print("visualized_celestial: 动画进程已启动")
    
    # 发送配置信息到动画进程
    parent_conn.send(
        {
            "type": "config",
            "duration": config.duration,
            "offset": config.offset,
        }
    )
    
    # 注册主机
    logging.info("Registering hosts...")
    with concurrent.futures.ThreadPoolExecutor() as e:
        for h in hosts:
            e.submit(h.register)
    logging.info("Host registration complete!")
    
    # 初始化主机
    inits = serializer.init_machines()
    
    # 分配机器到主机
    machines: typing.Dict[
        int,
        typing.List[
            typing.Tuple[
                celestial.types.MachineID_dtype, celestial.config.MachineConfig
            ]
        ],
    ] = {h: [] for h in range(len(hosts))}
    count = 0
    
    for m_id, m_config in inits:
        # 轮询分配机器到主机
        m_host = count % len(hosts)
        machines[m_host].append((m_id, m_config))
        count += 1
    
    # 初始化主机
    logging.info("Initializing hosts...")
    init_request = celestial.proto_util.make_init_request(hosts, machines)
    with concurrent.futures.ThreadPoolExecutor() as e:
        for h in hosts:
            e.submit(h.init, init_request)
    
    logging.info("Host initialization complete!")
    
    # 定义获取差异数据的函数
    def get_diff(
        t: celestial.types.timestamp_s,
    ) -> typing.List[proto.celestial.celestial_pb2.StateUpdateRequest]:
        t1 = time.perf_counter()
        s = [
            *celestial.proto_util.make_update_request_iter(
                serializer.diff_machines(t), serializer.diff_links(t)
            )
        ]
        logging.debug(f"Getting diff data took {time.perf_counter() - t1} seconds")
        return s
    
    # 开始仿真
    timestep: celestial.types.timestamp_s = 0 + config.offset
    updates = get_diff(timestep)
    
    start_time = time.perf_counter()
    logging.info("Starting simulation...")
    
    # 安装信号处理器
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    
    try:
        while True:
            logging.info(f"Updating timestep {timestep}")
            
            # 更新主机
            with concurrent.futures.ThreadPoolExecutor() as e:
                for i in range(len(hosts)):
                    e.submit(hosts[i].update, (u for u in updates))
            
            # 更新动画
            animation_constellation.step(timestep)
            
            timestep += config.resolution
            
            if timestep > config.duration + config.offset:
                break
            
            logging.debug(f"Getting update data for timestep {timestep}")
            
            # 提前获取下一个时间步的更新数据
            updates = get_diff(timestep)
            
            # 等待直到达到仿真时间
            wait_time = timestep - config.offset - (time.perf_counter() - start_time)
            logging.debug(f"Waiting {wait_time} seconds")
            while time.perf_counter() - start_time < timestep - config.offset:
                time.sleep(0.001)
    
    except KeyboardInterrupt:
        logging.info("Simulation interrupted by user")
    
    finally:
        # 停止主机
        logging.info("Stopping simulation...")
        with concurrent.futures.ThreadPoolExecutor() as e:
            for i in range(len(hosts)):
                e.submit(hosts[i].stop)
        
        # 停止SRv6路由服务器
        logging.info("Stopping SRv6 route server...")
        if 'srv6_route_server' in locals() and srv6_route_server is not None:
            srv6_route_server.stop()
            logging.info("SRv6 route server stopped")
        
        # 等待动画进程结束
        logging.info("Simulation complete, waiting for visualization window to close...")
        if animation_process.is_alive():
            animation_process.join(timeout=5)  # 设置超时时间，避免无限等待
            if animation_process.is_alive():
                logging.warning("Animation process did not end normally, forcing termination")
                animation_process.terminate()
        
        logging.info("Done")

if __name__ == "__main__":
    main()