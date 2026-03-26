import requests
import concurrent.futures
import os
import re

# --- 配置区 ---
SOURCE_M3U = "py/all_channels.m3u"
CLEAN_M3U = "py/hotel_only.m3u"
TIMEOUT = 3       # 酒店源响应快，3秒足够
MAX_WORKERS = 100 # GitHub Actions 环境建议 100 左右

def is_hotel_source(url):
    """关键逻辑：只允许特定的酒店源路径格式"""
    hotel_keywords = ['iptv/live', 'tsfile/live', 'hotel', '1000.json']
    # 剔除组播代理和已知的非酒店大流量源
    blacklist = ['udp://', 'vip1.', '484947', 'rtp://']
    
    if any(word in url.lower() for word in blacklist):
        return False
    return any(word in url.lower() for word in hotel_keywords)

def check_url(name, url, group):
    """测试链接是否真实可用"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Viera; rv:34.0) Gecko/20100101 Firefox/34.0'}
        # 使用 HEAD 请求提速，如果服务器不支持再用 GET
        response = requests.head(url, timeout=TIMEOUT, headers=headers, verify=False)
        if response.status_code == 200:
            return {"name": name, "url": url, "group": group}
    except:
        try:
            response = requests.get(url, timeout=TIMEOUT, headers=headers, verify=False, stream=True)
            if response.status_code == 200:
                return {"name": name, "url": url, "group": group}
        except:
            pass
    return None

def main():
    if not os.path.exists(SOURCE_M3U):
        print(f"错误：未找到源文件 {SOURCE_M3U}")
        return

    extracted_tasks = []
    
    # 1. 解析 M3U 提取潜在酒店源
    with open(SOURCE_M3U, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    for i in range(len(lines)):
        if lines[i].startswith('#EXTINF'):
            info = lines[i]
            url = lines[i+1].strip() if i+1 < len(lines) else ""
            
            if url and is_hotel_source(url):
                # 提取频道名和组名
                name_match = re.search(r',(.+)$', info)
                group_match = re.search(r'group-title="([^"]+)"', info)
                name = name_match.group(1).strip() if name_match else "Unknown"
                group = group_match.group(1).strip() if group_match else "Hotel"
                extracted_tasks.append((name, url, group))

    print(f"【筛选】从全量库中筛选出潜在酒店源: {len(extracted_tasks)} 条")

    # 2. 多线程测试存活
    valid_channels = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(check_url, n, u, g) for n, u, g in extracted_tasks]
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res:
                valid_channels.append(res)
                if len(valid_channels) % 10 == 0:
                    print(f"已找到存活酒店频道: {len(valid_channels)} 个...")

    # 3. 写入纯净 M3U
    with open(CLEAN_M3U, 'w', encoding='utf-8') as f:
        f.write("#EXTM3U\n")
        for ch in valid_channels:
            f.write(f'#EXTINF:-1 tvg-name="{ch["name"]}" group-title="{ch["group"]}",{ch["name"]}\n')
            f.write(f"{ch['url']}\n")

    print(f"\n--- 清洗完成 ---")
    print(f"最终保留存活酒店源: {len(valid_channels)} 条")
    print(f"结果保存至: {CLEAN_M3U}")

if __name__ == "__main__":
    main()
