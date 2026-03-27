import asyncio
import aiohttp
import os
import json

# --- 配置 ---
TARGET_PREFIX = "221.232"
TARGET_PORT = 7777
CHECK_PATH = "/iptv/live/1000.json?key=txipt"
M3U_FILE = "py/hb_telecom.m3u"
TVBOX_FILE = "py/hb_telecom_tvbox.txt"  # TVBox 格式文件
HISTORY_FILE = "py/scanned_history.json"
CONCURRENCY = 1000 

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: return []
    return []

def save_history(new_ips):
    old = load_history()
    updated = list(set(old + new_ips))
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(updated, f, indent=4, ensure_ascii=False)

async def check_host_alive(semaphore, ip):
    async with semaphore:
        try:
            fut = asyncio.open_connection(ip, TARGET_PORT)
            reader, writer = await asyncio.wait_for(fut, timeout=1.2)
            writer.close()
            await writer.wait_closed()
            return ip
        except: return None

async def fetch_channels(session, ip):
    url = f"http://{ip}:{TARGET_PORT}{CHECK_PATH}"
    try:
        async with session.get(url, timeout=4) as response:
            if response.status == 200:
                res = await response.json(content_type=None)
                if res.get("code") == 0 and "data" in res:
                    extracted = []
                    for item in res["data"]:
                        name = item.get("name", "").replace("-综合", "").replace("-", "")
                        # 简单分类逻辑
                        category = item.get("typename", "其他")
                        if "CCTV" in name: category = "央视"
                        elif "卫视" in name: category = "卫视"
                        
                        full_url = f"http://{ip}:{TARGET_PORT}{item.get('url')}"
                        extracted.append({"name": name, "url": full_url, "cat": category})
                    return extracted
    except: pass
    return None

async def main():
    history_ips = load_history()
    all_ips = [f"{TARGET_PREFIX}.{i}.{j}" for i in range(0, 256) for j in range(0, 256)]
    ips_to_scan = [ip for ip in all_ips if ip not in history_ips]
    
    print(f"🚀 开始扫描 {len(ips_to_scan)} 个新主机...")
    if not ips_to_scan: return

    semaphore = asyncio.Semaphore(CONCURRENCY)
    alive_tasks = [check_host_alive(semaphore, ip) for ip in ips_to_scan]
    alive_ips = [res for res in await asyncio.gather(*alive_tasks) if res]
    
    if not alive_ips:
        print("📡 未发现新存活主机。")
        return

    all_channels = []
    successful_ips = []
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_channels(session, ip) for ip in alive_ips]
        results = await asyncio.gather(*tasks)
        for i, res in enumerate(results):
            if res:
                all_channels.extend(res)
                successful_ips.append(alive_ips[i])

    if successful_ips:
        save_history(successful_ips)
        
        # --- 生成 M3U 格式 ---
        with open(M3U_FILE, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for ch in all_channels:
                f.write(f"#EXTINF:-1 group-title=\"{ch['cat']}\",{ch['name']}\n")
                f.write(f"{ch['url']}\n")
        
        # --- 生成 TVBox 格式 (分类#genre#) ---
        # 先按分类排序
        cat_dict = {}
        for ch in all_channels:
            cat_dict.setdefault(ch['cat'], []).append(f"{ch['name']},{ch['url']}")
        
        with open(TVBOX_FILE, "w", encoding="utf-8") as f:
            for cat, lines in cat_dict.items():
                f.write(f"{cat},#genre#\n")
                f.write("\n".join(lines) + "\n")
        
        print(f"✨ 完成！已生成 M3U 和 TVBox 格式文件。")

if __name__ == "__main__":
    asyncio.run(main())
