import subprocess
import re
import logging
from datetime import datetime

DNS_SERVER = "123.125.29.99"
DNS_FILE = "dns-ip.txt"
LOG_FILE = "dns-ip.log"

# 配置 logging
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

def extract_ns_records(lines):
    """从 dig 输出中提取 NS 记录"""
    ns_records = set()
    for line in lines:
        if re.search(r"\sIN\s+NS\s", line):
            parts = line.strip().split()
            if len(parts) >= 5:
                ns_records.add(parts[4].rstrip('.').lower())  # 统一转换为小写并移除末尾的点
    return ns_records

def get_direct_ns(domain):
    """从指定 DNS 查询域名的 NS 记录"""
    try:
        result = subprocess.run(
            ["dig", f"@{DNS_SERVER}", domain, "ns"],
            capture_output=True, text=True, timeout=10
        )
        return extract_ns_records(result.stdout.splitlines())
    except Exception:
        return set()

def get_trace_hop_ns(domain):
    """执行 dig +trace，提取倒数第二跳的 NS 记录"""
    try:
        result = subprocess.run(
            ["dig", domain, "ns", "+trace"],
            capture_output=True, text=True, timeout=20
        )
        lines = result.stdout.splitlines()

        trace_blocks = []
        current_block = {"ns_lines": [], "server": None}

        for line in lines:
            match = re.search(r";; Received \d+ bytes from [\d.]+#53\((.*?)\)", line)
            if match:
                if current_block["server"]:
                    trace_blocks.append(current_block)
                current_block = {"ns_lines": [], "server": match.group(1)}
            elif line.strip() and not line.startswith(";"):
                current_block["ns_lines"].append(line)

        if current_block["server"]:
            trace_blocks.append(current_block)

        if len(trace_blocks) < 2:
            return None, set()

        penultimate_block = trace_blocks[-2]
        ns_set = extract_ns_records(penultimate_block["ns_lines"])
        return penultimate_block["server"], ns_set

    except Exception:
        return None, set()

def get_ns_ips(dns_server, ns_set):
    """查询 NS 主机名对应的 IP 地址（A 记录）"""
    ns_ip_map = {}
    for ns in ns_set:
        fqdn = ns if ns.endswith('.') else f"{ns}."  # 保证完全匹配 dig 输出格式
        try:
            result = subprocess.run(
                ["dig", f"@{dns_server}", fqdn, "+time=5 +retry=3"],
                capture_output=True, text=True, timeout=10
            )
            lines = result.stdout.splitlines()
            ips = set()
            for line in lines:
                m = re.match(rf"^{re.escape(fqdn)}\s+\d+\s+IN\s+A\s+([\d\.]+)", line, re.IGNORECASE)
                if m:
                    ips.add(m.group(1))
            ns_ip_map[ns] = ips
        except Exception:
            ns_ip_map[ns] = set()
    return ns_ip_map

def send_alert(message):
    exec_command(f'python /data0/nscheck/send_alert_3_ip.py --subject="{message}"')

def exec_command(command):
    result = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    cmd_result = result.stdout.read().strip().decode('utf-8')
    return result, cmd_result

def main():
    logging.info(f"\n======================================= 检查时间：{datetime.now()} ================================================")
    try:
        with open(DNS_FILE, "r") as f:
            domains = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        logging.error(f"[ERROR] 文件 {DNS_FILE} 未找到。")
        return

    # 定义 sina.com 的特定 NS 记录
    SINA_SPECIFIC_NS = {"ns1.sina.com", "ns2.sina.com", "ns3.sina.com", "ns4.sina.com"}

    # 用于统计不一致的域名和NS
    inconsistent_domains = set()
    inconsistent_ns_records = []

    for domain in domains:
        domain_has_issue = False
        logging.info(f"\n🌐 检查域名: {domain}")
        direct_ns = get_direct_ns(domain)
        trace_server, trace_ns = get_trace_hop_ns(domain)

        logging.info(f"🔸 @指定DNS({DNS_SERVER})返回 NS记录: {sorted(direct_ns)}")
        if trace_server:
            logging.info(f"🔹 trace 中途（来自 {trace_server}）返回 NS记录: {sorted(trace_ns)}")
        else:
            logging.error(f"❌ trace 中未获取有效中转 NS")
            domain_has_issue = True

        if direct_ns == trace_ns:
            logging.info("✅ NS 记录一致")
        else:
            logging.error("❌ NS 记录不一致")
            domain_has_issue = True
            only_in_direct = sorted(direct_ns - trace_ns)
            only_in_trace = sorted(trace_ns - direct_ns)
            if only_in_direct:
                logging.info(f"   ➕ 仅在 direct 中出现: {only_in_direct}")
            if only_in_trace:
                logging.info(f"   ➖ 仅在 trace 中出现: {only_in_trace}")

        # 对比 NS 对应的 IP
        if trace_server:
            direct_ns_ips = get_ns_ips(DNS_SERVER, direct_ns)
            trace_ns_ips = get_ns_ips(trace_server, trace_ns)

            # 如果是 sina.com 则只关注特定 NS
            if domain.lower() == "sina.com":
                # 筛选出特定 NS 记录
                filtered_ns = SINA_SPECIFIC_NS & (direct_ns | trace_ns)
                # 记录被过滤掉的 NS
                ignored_ns = (direct_ns | trace_ns) - filtered_ns
                if ignored_ns:
                    logging.info(f"🔍 域名 sina.com 忽略非特定 NS: {sorted(ignored_ns)}")
            else:
                filtered_ns = direct_ns | trace_ns

            ip_mismatch = False

            for ns in filtered_ns:
                direct_ips = sorted(direct_ns_ips.get(ns, set()))
                trace_ips = sorted(trace_ns_ips.get(ns, set()))
                if direct_ips == trace_ips:
                    logging.info(f"✅ NS {ns} 的 IP 一致")
                else:
                    logging.error(f"❌ NS {ns} 的 IP 不一致")
                    logging.info(f"   ➕ direct IP: {direct_ips}")
                    logging.info(f"   ➖ trace IP : {trace_ips}")
                    ip_mismatch = True
                    domain_has_issue = True
                    inconsistent_ns_records.append(f"{domain}: {ns} (Direct: {direct_ips}, Trace: {trace_ips})")

            if ip_mismatch:
                logging.error("❌ NS对应IP地址不一致")
                inconsistent_domains.add(domain)
            else:
                logging.info("✅ 所有 NS 的 IP 地址一致")

        # 如果这个域名有任何问题，添加到统计中
        if domain_has_issue:
            inconsistent_domains.add(domain)

    if inconsistent_domains or inconsistent_ns_records:
        message = f"⚠️  域名NS及其ip direct和trace结果不一致,请核实!"
        send_alert(message)

    # 统计并打印不一致情况
    if inconsistent_domains:
        logging.error("\n" + "="*60)
        logging.error("⚠️ 检测到不一致的域名统计")
        logging.error("="*60)
        logging.error(f"不一致域名总数: {len(inconsistent_domains)}")
        logging.error(f"不一致域名列表: {sorted(inconsistent_domains)}")

        if inconsistent_ns_records:
            logging.error("\n不一致的NS记录详情:")
            for record in inconsistent_ns_records:
                logging.error(f"  - {record}")
        logging.error("="*60)
    else:
        logging.info("\n✅ 所有域名检查一致，未发现不一致情况")

if __name__ == "__main__":
    main()