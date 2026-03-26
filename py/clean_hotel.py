import requests
import concurrent.futures
import os
import re

# --- 配置 ---
SOURCE_M3U = "py/all_channels.m3u"
CLEAN_M3U = "py/hotel_only.m3u"
TIMEOUT = 3
MAX_WORKERS = 100

def is_hotel_source(url):
    # 只允许包含这些关键词的酒店源格式
    hotel_keywords = ['iptv/live', 'tsfile/live', '1000.json', 'key=txipt']
    # 彻底屏蔽非酒店源关键字
    blacklist = ['udp://', 'vip1.', '484947', 'rtp://', 'xinketongxun', '55555.io']
    
    url_l = url.lower()
    if any(word in url_l for word in blacklist):
        return False
    return any(word in url_l for word in hotel_keywords)

def check_url(name, url, group):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Viera; rv:34.0) Gecko/20100101 Firefox/34.0'}
        # 先用 HEAD 快扫
        r = requests.head(url, timeout=TIMEOUT, headers=headers, verify=False)
        if r.status_code == 200:
            return {"name": name, "url": url, "group": group}
    except:
        pass
    return None

def main():
    if not os.path.exists(SOURCE_M3U): return
    tasks = []
    with open(SOURCE_M3U, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    for i in range(len(lines)):
        if lines[i].startswith('#EXTINF') and i+1 < len(lines):
            info, url = lines[i], lines[i+1].strip()
            if is_hotel_source(url):
                name = re.search(r',(.+)$', info).group(1).strip() if ',' in info else "Unknown"
                group = re.search(r'group-title="([^"]+)"', info).group(1).strip() if 'group-title' in info else "Hotel"
                tasks.append((name, url, group))

    valid = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(check_url, *t) for t in tasks]
        for f in concurrent.futures.as_completed(futures):
            res = f.result()
            if res: valid.append(res)

    with open(CLEAN_M3U, 'w', encoding='utf-8') as f:
        f.write("#EXTM3U\n")
        for ch in valid:
            f.write(f'#EXTINF:-1 tvg-name="{ch["name"]}" group-title="{ch["group"]}",{ch["name"]}\n{ch["url"]}\n')
    print(f"清洗完成，存活酒店源: {len(valid)}")

if __name__ == "__main__":
    main()
