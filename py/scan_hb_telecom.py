import asyncio
import aiohttp
import os
import json

# --- 配置 ---
TARGET_PREFIX = "221.232"
TARGET_PORT = 7777
CHECK_PATH = "/iptv/live/1000.json?key=txipt"
OUTPUT_FILE = "py/hb_telecom_detected.m3u"
HISTORY_FILE = "py/scanned_history.json"  # 记录已抓取的 ID 组合
CONCURRENCY = 1000 

def load_history():
    """读取历史记录，返回已存在的 IP 列表"""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return []
    return []

def save_history(new_ips):
    """追加新的 IP 到历史记录"""
    old_history = load_history()
    # 合并去重
    updated_history = list(set(old_history + new_ips))
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(updated_history, f, indent=4, ensure_ascii=False)
    return len(updated_history)

async def check_host_alive(semaphore, ip):
    async with semaphore:
        try:
            fut = asyncio.open_connection(ip, TARGET_PORT)
            reader, writer = await asyncio.wait_for(fut, timeout=1.2)
            writer.close()
            await writer.wait_closed()
            return ip
        except:
            return None

async def fetch_and_parse_json(session, ip):
    url = f"http://{ip}:{TARGET_PORT}{CHECK_PATH}"
    try:
        async with session.get(url, timeout=4) as response:
            if response.status == 200:
                res_json = await response.json(content_type=None)
                if res_json.get("code") == 0 and "data" in res_json:
                    return [{"name": i["name"], "url": f"http://{ip}:{TARGET_PORT}{i['url']}", "ip": ip} for i in res_json["data"]]
    except:
        pass
    return None

async def main():
    # 1. 加载历史，排除已抓取的 IP
    history_ips = load_history()
    print(f"📜 历史记录中已有 {len(history_ips)} 个有效 IP。")

    all_ips = [f"{TARGET_PREFIX}.{i}.{j}" for i in range(0, 256) for j in range(0, 256)]
    # 过滤掉已存在的
    ips_to_scan = [ip for ip in all_ips if ip not in history_ips]
    
    print(f"🚀 开始扫描剩余的 {len(ips_to_scan)} 个未知主机...")
    if not ips_to_scan:
        print("✅ 所有 IP 已在历史记录中，无需重新扫描。")
        return

    semaphore = asyncio.Semaphore(CONCURRENCY)
    alive_tasks = [check_host_alive(semaphore, ip) for ip in ips_to_scan]
    alive_ips = [res for res in await asyncio.gather(*alive_tasks) if res]
    
    if not alive_ips:
        print("📡 未发现新的存活主机。")
        return

    # 2. 抓取新发现的 IP 内容
    new_found_channels = []
    async with aiohttp.ClientSession() as session:
        parse_tasks = [fetch_and_parse_json(session, ip) for ip in alive_ips]
        parsed_results = await asyncio.gather(*parse_tasks)
        successful_ips = []
        for i, res in enumerate(parsed_results):
            if res:
                new_found_channels.extend(res)
                successful_ips.append(alive_ips[i])

    # 3. 如果发现新内容，更新历史记录和 M3U
    if successful_ips:
        total_count = save_history(successful_ips)
        print(f"✨ 发现 {len(successful_ips)} 个新 IP！历史库已更新至 {total_count} 个。")
        
        # 写入 M3U (这里可以选：只写新的，或者重新生成全部已知的)
        # 建议：重新生成全部已知的 M3U，保证文件最全
        full_history = load_history()
        os.makedirs("py", exist_ok=True)
        
        # 此时需要重新抓取所有历史 IP 的最新频道（或者你只把新抓的追加进去）
        # 为了简单和速度，这里演示【追加模式】生成 M3U：
        with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
            if os.path.getsize(OUTPUT_FILE) < 10: # 如果文件是空的，写个头
                f.write("#EXTM3U\n")
            for ch in new_found_channels:
                f.write(f"#EXTINF:-1,湖北电信_{ch['ip']}_{ch['name']}\n")
                f.write(f"{ch['url']}\n")
    else:
        print("🧪 探测到了存活端口，但未解析到有效频道 JSON 数据。")

if __name__ == "__main__":
    asyncio.run(main())
