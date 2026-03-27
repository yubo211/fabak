import asyncio
import aiohttp
import os
import json
import re

# --- 配置 ---
TARGET_PREFIX = "221.232"
TARGET_PORT = 7777
CHECK_PATH = "/iptv/live/1000.json?key=txipt"
M3U_FILE = "py/hb_telecom.m3u"
TVBOX_FILE = "py/hb_telecom_tvbox.txt"
HISTORY_FILE = "py/scanned_history.json"
CONCURRENCY = 1000 

# 卫视优先级排序列表
PROVINCIAL_LOGIC = ['浙江卫视', '湖南卫视', '东方卫视', '北京卫视', '江苏卫视', '江西卫视', '深圳卫视', '湖北卫视', '吉林卫视', '四川卫视', '天津卫视', '宁夏卫视', '安徽卫视', '山东卫视', '山西卫视', '广东卫视', '广西卫视', '东南卫视', '内蒙古卫视', '黑龙江卫视', '新疆卫视', '河北卫视', '河南卫视', '云南卫视', '海南卫视', '甘肃卫视', '西藏卫视', '贵州卫视', '辽宁卫视', '陕西卫视', '青海卫视', '康巴卫视', '三沙卫视', '大湾区卫视']

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
    return updated

def clean_and_weight(name):
    """规范频道名并计算排序权重"""
    # 1. 规范 CCTV
    if "CCTV" in name.upper():
        # 匹配 CCTV1, CCTV-1, CCTV1综合 等
        match = re.search(r'CCTV[- ]?(\d+)', name, re.I)
        if match:
            num = match.group(1)
            return f"CCTV{num}", int(num) # 权重就是频道号
        if "5+" in name: return "CCTV5+", 5.5
        return name, 99 # 其他 CCTV

    # 2. 卫视排序
    for i, province in enumerate(PROVINCIAL_LOGIC):
        if province in name:
            return province, 100 + i # 权重 100 以后
            
    # 3. 其他卫视
    if "卫视" in name:
        return name, 200
        
    return name, 999 # 地方台排最后

async def check_host_alive(semaphore, ip):
    async with semaphore:
        try:
            fut = asyncio.open_connection(ip, TARGET_PORT)
            reader, writer = await asyncio.wait_for(fut, timeout=1.2)
            writer.close()
            await writer.wait_closed()
            return ip
        except: return None

async def fetch_all_data(session, ip_list):
    """抓取所有历史 IP 和新 IP 的最新数据"""
    results = []
    tasks = []
    for ip in ip_list:
        url = f"http://{ip}:{TARGET_PORT}{CHECK_PATH}"
        tasks.append(session.get(url, timeout=5))
    
    responses = await asyncio.gather(*tasks, return_exceptions=True)
    for i, resp in enumerate(responses):
        if isinstance(resp, aiohttp.ClientResponse) and resp.status == 200:
            try:
                data = await resp.json(content_type=None)
                if data.get("code") == 0:
                    for item in data["data"]:
                        raw_name = item.get("name", "")
                        clean_name, weight = clean_and_weight(raw_name)
                        
                        # 确定分类
                        if weight < 100: cat = "央视"
                        elif weight < 300: cat = "卫视"
                        else: cat = "地方"
                        
                        results.append({
                            "name": clean_name,
                            "url": f"http://{ip_list[i]}:{TARGET_PORT}{item.get('url')}",
                            "cat": cat,
                            "weight": weight
                        })
            except: pass
    return results

async def main():
    history_ips = load_history()
    all_range_ips = [f"{TARGET_PREFIX}.{i}.{j}" for i in range(0, 256) for j in range(0, 256)]
    ips_to_scan = [ip for ip in all_range_ips if ip not in history_ips]
    
    # 1. 扫描新 IP
    print(f"🚀 正在扫描新主机...")
    semaphore = asyncio.Semaphore(CONCURRENCY)
    alive_tasks = [check_host_alive(semaphore, ip) for ip in ips_to_scan]
    new_alive_ips = [res for res in await asyncio.gather(*alive_tasks) if res]
    
    # 2. 合并所有存活 IP (历史+新发现) 重新抓取完整列表
    # 这样可以保证文件是全量更新，不漏掉老 IP 的新变动
    current_ips = list(set(history_ips + new_alive_ips))
    
    async with aiohttp.ClientSession() as session:
        print(f"🧪 正在从 {len(current_ips)} 个服务器同步频道列表...")
        all_channels = await fetch_all_data(session, current_ips)

    if all_channels:
        # 3. 排序逻辑：先按分类(央视>卫视>地方)，再按权重
        # 分类排序：央视(0) < 卫视(1) < 地方(2)
        cat_order = {"央视": 0, "卫视": 1, "地方": 2}
        all_channels.sort(key=lambda x: (cat_order.get(x['cat'], 3), x['weight'], x['name']))

        # 4. 生成文件 (覆盖写入)
        os.makedirs("py", exist_ok=True)
        
        # M3U 格式
        with open(M3U_FILE, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for ch in all_channels:
                f.write(f"#EXTINF:-1 group-title=\"{ch['cat']}\",{ch['name']}\n")
                f.write(f"{ch['url']}\n")
        
        # TVBox 格式
        cat_dict = {}
        for ch in all_channels:
            cat_dict.setdefault(ch['cat'], []).append(f"{ch['name']},{ch['url']}")
        
        with open(TVBOX_FILE, "w", encoding="utf-8") as f:
            for cat in ["央视", "卫视", "地方"]:
                if cat in cat_dict:
                    f.write(f"{cat},#genre#\n")
                    f.write("\n".join(cat_dict[cat]) + "\n")

        # 更新历史记录 (只有抓取成功的 IP 才算入历史)
        valid_ips = list(set([ch['url'].split('/')[2].split(':')[0] for ch in all_channels]))
        save_history(valid_ips)
        
        print(f"✨ 同步完成！M3U 条数: {len(all_channels)}, TXT 条数: {len(all_channels)}")
    else:
        print("❌ 未获取到任何有效频道。")

if __name__ == "__main__":
    asyncio.run(main())
