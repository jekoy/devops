import whois
import logging
import time
from datetime import datetime

# 配置日志
logging.basicConfig(
    filename='dns-whois.log',
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

def get_name_servers(domain):
    """查询域名并返回名称服务器列表"""
    try:
        w = whois.whois(domain)
        # 处理不同格式的返回结果
        if isinstance(w.name_servers, list):
            return [ns.lower() for ns in w.name_servers if ns]
        elif w.name_servers:
            return [ns.strip().lower() for ns in w.name_servers.split(',') if ns.strip()]
        return []
    except Exception as e:
        logging.error(f"Domain: {domain}, Error: {str(e)}")
        return None

# 主处理流程
try:
    with open('dns-whois.txt', 'r') as file:
        domains = [line.strip() for line in file if line.strip()]

    total = len(domains)
    for i, domain in enumerate(domains, 1):
        if not domain:
            continue

        start_time = datetime.now()
        logging.info(f"Processing {i}/{total}: {domain}")
        #print(f"[{start_time.strftime('%H:%M:%S')}] Processing {i}/{total}: {domain}")

        name_servers = get_name_servers(domain)

        if name_servers is None:
            continue  # 已记录错误
        elif name_servers:
            ns_list = ', '.join(sorted(set(name_servers)))
            logging.info(f"Domain: {domain}, Name Servers: {ns_list}")
            #print(f"  Found {len(name_servers)} name servers")
        else:
            logging.info(f"Domain: {domain}, No name servers found")
            #print("  No name servers found")

        # 避免请求过快的延迟
        elapsed = (datetime.now() - start_time).total_seconds()
        if elapsed < 1.5:
            time.sleep(1.5 - elapsed)

except FileNotFoundError:
    logging.error("Error: dns-whois.txt file not found")
    #print("Error: dns-whois.txt file not found")
except Exception as e:
    logging.error(f"Unexpected error: {str(e)}")
    #print(f"Unexpected error: {str(e)}")