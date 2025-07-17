import subprocess
import re
import logging
from datetime import datetime

DNS_SERVER = "123.125.29.99"
DNS_FILE = "dns-ns.txt"
LOG_FILE = "dns-ns.log"
CONSISTENT_LOG = "ns_consistent.log"
INCONSISTENT_LOG = "ns_inconsistent.log"

def setup_logging():
    # 主 logger：所有信息写入文件
    logger = logging.getLogger("dns_check")
    logger.setLevel(logging.DEBUG)

    # 文件处理器 - 总日志
    fh = logging.FileHandler(LOG_FILE, encoding='utf-8')
    fh.setLevel(logging.DEBUG)

    formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
    fh.setFormatter(formatter)

    logger.addHandler(fh)

    # 记录一致和不一致的 logger（仅写文件）
    consistent_logger = logging.getLogger("consistent")
    consistent_logger.setLevel(logging.INFO)
    ch_consistent = logging.FileHandler(CONSISTENT_LOG, encoding='utf-8')
    ch_consistent.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
    consistent_logger.addHandler(ch_consistent)

    inconsistent_logger = logging.getLogger("inconsistent")
    inconsistent_logger.setLevel(logging.INFO)
    ch_inconsistent = logging.FileHandler(INCONSISTENT_LOG, encoding='utf-8')
    ch_inconsistent.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
    inconsistent_logger.addHandler(ch_inconsistent)

    return logger, consistent_logger, inconsistent_logger

def extract_ns_records(lines):
    ns_records = set()
    for line in lines:
        if re.search(r"\sIN\s+NS\s", line, re.IGNORECASE):
            parts = line.strip().split()
            if len(parts) >= 5:
                ns_records.add(parts[4].rstrip('.'))
    return ns_records

def get_direct_ns(domain):
    try:
        result = subprocess.run(
            ["dig", f"@{DNS_SERVER}", domain, "ns"],
            capture_output=True, text=True, timeout=10
        )
        return extract_ns_records(result.stdout.splitlines())
    except Exception as e:
        return set()

def get_trace_hop_ns(domain):
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

def send_alert(message):
    exec_command(
        'python /data0/nscheck/send_alert_3.py --subject="{}"'.format(message))

def exec_command(command):
    result = subprocess.Popen('{}'.format(command), shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    cmd_result = result.stdout.read().strip()
    cmd_result = cmd_result.decode('utf-8')
    return result, cmd_result

def main():
    logger, consistent_logger, inconsistent_logger = setup_logging()
    inconsistent_domains = []  # 存储不一致的域名
    consistent_domains = []
    try:
        with open(DNS_FILE, "r") as f:
            domains = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        logger.error(f"文件 {DNS_FILE} 未找到。")
        return

    logger.info(f"==================================================== 检查时间：{datetime.now()} ===============================================================")

    for domain in domains:
        logger.info(f"\n🌐 检查域名: {domain}")

        direct_ns = get_direct_ns(domain)
        trace_server, trace_ns = get_trace_hop_ns(domain)

        logger.info(f"🔸 @指定DNS({DNS_SERVER})返回 NS记录: {sorted(direct_ns)}")

        if trace_server:
            logger.info(f"🔹 trace 中途（来自 {trace_server}）返回 NS记录: {sorted(trace_ns)}")
        else:
            logger.warning(f"❌ trace 中未获取有效中转 NS")

        if direct_ns == trace_ns:
            logger.info("✅ NS 记录一致")
            consistent_logger.info(f"{domain} - NS记录一致")
            consistent_domains.append(domain)
        else:
            logger.error("❌ NS 记录不一致")
            inconsistent_logger.info(f"{domain} - NS记录不一致")
            inconsistent_domains.append(domain)

            only_in_direct = sorted(direct_ns - trace_ns)
            only_in_trace = sorted(trace_ns - direct_ns)

            if only_in_direct:
                logger.info(f"   ➕ 仅在 direct 中出现: {only_in_direct}")
            if only_in_trace:
                logger.info(f"   ➖ 仅在 trace 中出现: {only_in_trace}")

    if len(inconsistent_domains) != 0:
        logger.info(inconsistent_domains)
        result = "\n".join(inconsistent_domains)
        message = f"⚠️  以下域NS记录direct和trace结果不一致,请核实! \n{result}"
        send_alert(message)

    logger.info(f"总域名数: {len(domains)}")
    logger.info(f"不一致域名数: {len(inconsistent_domains)}")
    logger.info("不一致域名列表:")
    for i, domain in enumerate(inconsistent_domains, 1):
        logger.info(f"{i}. {domain}")

if __name__ == "__main__":
    main()