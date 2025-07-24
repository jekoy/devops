import subprocess
import platform

def ping(host):
    """
    执行ping命令检测主机是否可达
    参数：host - 目标IP地址
    返回：布尔值表示是否可达
    """
    # 根据不同操作系统设置ping参数
    param = '-n' if platform.system().lower() == 'windows' else '-c'
    timeout = '1000' if platform.system().lower() == 'windows' else '1'
    command = ['ping', param, '1', '-w', timeout, host]

    try:
        # 执行ping命令，超时设置为2秒
        response = subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2
        )
        return response.returncode == 0
    except subprocess.TimeoutExpired:
        return False

def main():
    base_ip = '202.108.7.'
    reachable_ips = []

    # 遍历0-255所有最后一位IP
    for i in range(256):
        current_ip = f"{base_ip}{i}"
        print(f"正在检测 {current_ip}...", end='\r')

        if ping(current_ip):
            print(f"{current_ip} 可达        ")
            reachable_ips.append(current_ip)
        else:
            print(f"{current_ip} 不可达      ")

    # 将结果写入文件
    with open('2021087-new-tong.txt', 'w') as f:
        for ip in reachable_ips:
            f.write(f"{ip}\n")
    print(f"\n检测完成，找到 {len(reachable_ips)} 个可达IP，结果已保存到 tong.txt")

if __name__ == "__main__":
    main()