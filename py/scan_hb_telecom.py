import asyncio
import aiohttp
import os

# --- 配置 ---
TARGET_PREFIX = "221.232"
TARGET_PORT = 7777
CHECK_PATH = "/iptv/live/1000.json?key=txipt"
OUTPUT_FILE = "py/hb_telecom_detected.m3u"
CONCURRENCY = 1500  # 提高并发，因为第一步只是握手检测

async def check_host_alive(semaphore, ip):
    """第一步：快速检测端口是否开放 (代替 Ping)"""
    async with semaphore:
        try:
            # 尝试建立 TCP 连接，超时设短一点
            fut = asyncio.open_connection(ip, TARGET_PORT)
            reader, writer = await asyncio.wait_for(fut, timeout=1.5)
            writer.close()
            await writer.wait_closed()
            return ip
        except:
            return None

async def verify_iptv_service(session, ip):
    """第二步：对存活主机进行业务路径验证"""
    url = f"http://{ip}:{TARGET_PORT}{CHECK_PATH}"
    try:
        async with session.get(url, timeout=3) as response:
            if response.status == 200:
                text = await response.text()
                # 湖北电信酒店源通常返回包含 "data" 或 "channel" 的 JSON
                if len(text) > 100: 
                    return ip
    except:
        pass
    return None

async def main():
    print(f"🚀 开始扫描 {TARGET_PREFIX}.0.0/16 存活主机...")
    ips_to_scan = [f"{TARGET_PREFIX}.{i}.{j}" for i in range(0, 256) for j in range(0, 256)]
    
    semaphore = asyncio.Semaphore(CONCURRENCY)
    
    # --- 第一阶段：筛选存活主机 ---
    alive_tasks = [check_host_alive(semaphore, ip) for ip in ips_to_scan]
    alive_ips = []
    for f in asyncio.as_completed(alive_tasks):
        res = await f
        if res:
            alive_ips.append(res)
            
    print(f"📡 探测完成，发现 {len(alive_ips)} 个主机开启了 {TARGET_PORT} 端口。")

    if not alive_ips:
        print("终止：未发现任何潜在主机。")
        return

    # --- 第二阶段：业务逻辑验证 ---
    print("🧪 正在执行 IPTV 业务逻辑验证...")
    results = []
    async with aiohttp.ClientSession() as session:
        verify_tasks = [verify_iptv_service(session, ip) for ip in alive_ips]
        verified_results = await asyncio.gather(*verify_tasks)
        results = [ip for ip in verified_results if ip]

    # --- 第三阶段：保存结果 ---
    os.makedirs("py", exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        for ip in sorted(results):
            f.write(f"#EXTINF:-1,湖北电信_{ip}\n")
            f.write(f"http://{ip}:{TARGET_PORT}/tsfile/live/0001_1.m3u8?key=txipt&playlive=1&authid=0\n")
            
    print(f"✨ 爆破成功！共保存 {len(results)} 个有效源至 {OUTPUT_FILE}")

if __name__ == "__main__":
    asyncio.run(main())
