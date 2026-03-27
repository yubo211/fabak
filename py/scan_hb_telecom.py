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
HISTORY_FILE = "py/scanned_history.json" # 仅作为发现记录，不参与扫描过滤
CONCURRENCY = 1000 

PROVINCIAL_LOGIC = ['浙江卫视', '湖南卫视', '东方卫视', '北京卫视', '江苏卫视', '江西卫视', '深圳卫视', '湖北卫视', '吉林卫视', '四川卫视', '天津卫视', '宁夏卫视', '安徽卫视', '山东卫视', '山西卫视', '广东卫视', '广西卫视', '东南卫视', '内蒙古卫视', '黑龙江卫视', '新疆卫视', '河北卫视', '河南卫视', '云南卫视', '海南卫视', '甘肃卫视', '西藏卫视', '贵州卫视', '辽宁卫视', '陕西卫视', '青海卫视', '康巴卫视', '三沙卫视', '大湾区卫视']

def update_history_log(current_ips):
    """对比并追加新发现的 IP ID"""
    existing_history = []
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                existing_history = json.load(f)
        except: pass
    
    # 找出本次扫描中，历史记录里没有的新 IP
    new_ips = [ip for ip in current_ips if ip not in existing_history]
    
    if new_ips:
        updated_history = list(set(existing_history + new_ips))
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(updated_history, f, indent=4, ensure_ascii=False)
        print(f"📝 历史记录已更新，新增了 {len(new_ips)} 个新发现的 IP。")
    else:
        print("ℹ️ 本次未发现新的 IP ID。")

def clean_and_weight(name):
    name_upper = name.upper().replace(" ", "").replace("-", "")
    if "CCTV5+" in name_upper or "CCTV5体育赛事" in name_upper:
        return "CCTV5+", 5.5
    if "CCTV" in name_upper:
        match = re.search(r'CCTV(\d+)', name_upper)
        if match:
            num = match.group(1)
            return f"CCTV{num}", int(num)
        return name, 99
    for i, province in enumerate(PROVINCIAL_LOGIC):
        if province in name:
            return province, 100 + i 
    if "卫视" in name:
        return name, 200
    return name, 999

async def check_host_alive(semaphore, ip):
    async with semaphore:
        try:
            fut = asyncio.open_connection(ip, TARGET_PORT)
            reader, writer = await asyncio.wait_for(fut, timeout=1.0) # 缩短超时加快全量扫描
            writer.close()
            await writer.wait_closed()
            return ip
        except: return None

async def fetch_data(session, ip_list):
    results = []
    tasks = [session.get(f"http://{ip}:{TARGET_PORT}{CHECK_PATH}", timeout=5) for ip in ip_list]
    responses = await asyncio.gather(*tasks, return_exceptions=True)
    for i, resp in enumerate(responses):
        if isinstance(resp, aiohttp.ClientResponse) and resp.status == 200:
            try:
                data = await resp.json(content_type=None)
                if data.get("code") == 0:
                    for item in data["data"]:
                        clean_name, weight = clean_and_weight(item.get("name", ""))
                        cat = "央视" if weight < 100 else ("卫视" if weight < 300 else "地方")
                        results.append({
                            "name": clean_name, "url": f"http://{ip_list[i]}:{TARGET_PORT}{item.get('url')}",
                            "cat": cat, "weight": float(weight), "ip": ip_list[i]
                        })
            except: pass
    return results

async def main():
    # 1. 全量扫描 221.232.0.0/16
    print(f"🚀 开始全量爆破 {TARGET_PREFIX}.x.y (不参考历史记录)...")
    all_ips = [f"{TARGET_PREFIX}.{i}.{j}" for i in range(256) for j in range(256)]
    semaphore = asyncio.Semaphore(CONCURRENCY)
    alive_tasks = [check_host_alive(semaphore, ip) for ip in all_ips]
    alive_ips = [res for res in await asyncio.gather(*alive_tasks) if res]
    
    print(f"📡 探测完成，当前共有 {len(alive_ips)} 个活跃服务器。")

    if alive_ips:
        # 2. 抓取实时频道
        async with aiohttp.ClientSession() as session:
            all_channels = await fetch_data(session, alive_ips)

        if all_channels:
            # 排序
            cat_order = {"央视": 0, "卫视": 1, "地方": 2}
            all_channels.sort(key=lambda x: (cat_order.get(x['cat'], 3), x['weight'], x['name']))

            # 3. 输出文件 (全量覆盖)
            os.makedirs("py", exist_ok=True)
            with open(M3U_FILE, "w", encoding="utf-8") as f:
                f.write("#EXTM3U\n")
                for ch in all_channels:
                    f.write(f"#EXTINF:-1 group-title=\"{ch['cat']}\",{ch['name']}\n{ch['url']}\n")
            
            cat_dict = {}
            for ch in all_channels:
                cat_dict.setdefault(ch['cat'], []).append(f"{ch['name']},{ch['url']}")
            with open(TVBOX_FILE, "w", encoding="utf-8") as f:
                for cat in ["央视", "卫视", "地方"]:
                    if cat in cat_dict:
                        f.write(f"{cat},#genre#\n" + "\n".join(cat_dict[cat]) + "\n")

            # 4. 最后一步：更新发现记录
            current_success_ips = list(set([ch['ip'] for ch in all_channels]))
            update_history_log(current_success_ips)
            
            print(f"✅ 处理完成。M3U/TXT 已生成，条数: {len(all_channels)}")
    else:
        print("❌ 未发现任何活跃源。")

if __name__ == "__main__":
    asyncio.run(main())
