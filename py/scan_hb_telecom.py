import asyncio
import aiohttp
import os
import json

# --- 配置 ---
TARGET_PREFIX = "221.232"
TARGET_PORT = 7777
# 这里的 1000.json 似乎是总表
CHECK_PATH = "/iptv/live/1000.json?key=txipt"
OUTPUT_FILE = "py/hb_telecom_detected.m3u"
CONCURRENCY = 1000 

async def check_host_alive(semaphore, ip):
    """第一步：检测 TCP 端口存活"""
    async with semaphore:
        try:
            fut = asyncio.open_connection(ip, TARGET_PORT)
            reader, writer = await asyncio.wait_for(fut, timeout=1.5)
            writer.close()
            await writer.wait_closed()
            return ip
        except:
            return None

async def fetch_and_parse_json(session, ip):
    """第二步：访问 JSON 并解析频道列表"""
    url = f"http://{ip}:{TARGET_PORT}{CHECK_PATH}"
    try:
        async with session.get(url, timeout=4) as response:
            if response.status == 200:
                res_json = await response.json(content_type=None)
                if res_json.get("code") == 0 and "data" in res_json:
                    channels = []
                    for item in res_json["data"]:
                        ch_name = item.get("name")
                        ch_url = item.get("url")
                        if ch_name and ch_url:
                            # 拼接完整地址
                            full_url = f"http://{ip}:{TARGET_PORT}{ch_url}"
                            channels.append({
                                "name": ch_name,
                                "url": full_url,
                                "ip": ip
                            })
                    return channels
    except:
        pass
    return None

async def main():
    print(f"🚀 开始爆破 {TARGET_PREFIX}.0.0/16 ...")
    ips_to_scan = [f"{TARGET_PREFIX}.{i}.{j}" for i in range(0, 256) for j in range(0, 256)]
    
    semaphore = asyncio.Semaphore(CONCURRENCY)
    
    # 1. 找存活 IP
    alive_tasks = [check_host_alive(semaphore, ip) for ip in ips_to_scan]
    alive_ips = [res for res in await asyncio.gather(*alive_tasks) if res]
    print(f"📡 发现 {len(alive_ips)} 个潜在服务器。")

    if not alive_ips: return

    # 2. 获取 JSON 内容
    all_extracted_channels = []
    async with aiohttp.ClientSession() as session:
        parse_tasks = [fetch_and_parse_json(session, ip) for ip in alive_ips]
        parsed_results = await asyncio.gather(*parse_tasks)
        for res in parsed_results:
            if res: all_extracted_channels.extend(res)

    # 3. 写入 M3U (按 IP 分组排序)
    if all_extracted_channels:
        os.makedirs("py", exist_ok=True)
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for ch in all_extracted_channels:
                f.write(f"#EXTINF:-1,湖北电信_{ch['ip']}_{ch['name']}\n")
                f.write(f"{ch['url']}\n")
        print(f"✨ 成功！共提取到 {len(all_extracted_channels)} 个频道，保存至 {OUTPUT_FILE}")
    else:
        print("❌ 未能从存活服务器中解析出有效的频道数据。")

if __name__ == "__main__":
    asyncio.run(main())
