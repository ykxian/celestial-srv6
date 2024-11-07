import json
import subprocess

def calculate_ips(shell_id, satellite_id):
    # 计算 IPv4 地址
    byte1 = 10  # 固定为10
    byte2 = shell_id  # shell identifier
    byte3 = (satellite_id >> 6) & 0xFF  # satellite identifier, shifted right by 6 bits
    byte4 = (satellite_id << 2) & 0xFF  # satellite identifier, shifted left by 2 bits

    # microVMs 地址
    microVM_ip = f"{byte1}.{byte2}.{byte3}.{byte4 + 2}"

    # 计算 IPv6 地址
    ipv6_address = f"fd00::{byte1:x}:{byte2:x}:{byte3:x}:{(byte4 + 2):x}"

    return microVM_ip, ipv6_address

def execute_command():
    try:
        # 执行 curl 命令并获取 JSON 输出
        result = subprocess.run(
            ["curl", "info.celestial/path/gst/validator/1/1040"],
            capture_output=True,
            text=True
        )
        json_data = json.loads(result.stdout)
        
        # 提取 segments
        segments = json_data.get("segments", [])
        
        # 记录路径的每个节点 (shell 和 id)
        path = []
        ipv6_segs = []  # 用于保存 IPv6 地址列表
        
        # 遍历 segments 并避免重复的中间节点
        for i, segment in enumerate(segments):
            source = segment["source"]
            target = segment["target"]
            
            # 第一个 segment，加入 source 和 target
            if i == 0:
                source_ip = calculate_ips(source["shell"], source["id"])[1]
                path.append(f"shell-{source['shell']}-id-{source['id']}")
                ipv6_segs.append(source_ip)
            
            # 只加入 target
            target_ip = calculate_ips(target["shell"], target["id"])[1]
            path.append(f"shell-{target['shell']}-id-{target['id']}")
            ipv6_segs.append(target_ip)
        
        # 将路径格式化为 a->b->c->d 形式
        path_str = " -> ".join(path)
        print("Path:", path_str)
        
        # 目标地址为最后一个 segment 的 target
        final_target_ip = ipv6_segs[-1]
        # 中间节点的 IPv6 地址，排除第一个和最后一个地址
        ipv6_segs_str = ",".join(ipv6_segs[1:-1])
        
        # 格式化 ip route 命令
        ip_route_cmd = f"ip -6 route add {final_target_ip} encap seg6 mode encap segs {ipv6_segs_str} dev eth0"
        print("Generated IP Route Command:")
        print(ip_route_cmd)
        
        # 执行 ip route 命令
        route_result = subprocess.run(ip_route_cmd, shell=True, text=True)
        if route_result.returncode == 0:
            print("Route command executed successfully.")
        else:
            print("Error executing route command:", route_result.stderr)

    except Exception as e:
        print(f"An error occurred: {e}")

# 调用函数
execute_command()

