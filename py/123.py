import requests
import time
import random
import re
import os
import json
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor

# --- 配置 ---
SOURCE_M3U_URL = "https://raw.githubusercontent.com/yubo211/fabak/refs/heads/main/py/hotel_only.m3u"
OUTPUT_TXT = "/volume1/web/iptv/traffic_report.txt"
OUTPUT_JSON = "/volume1/web/iptv/traffic_summary.json"
TEST_DURATION = 30  # 每个 ID 测试 30 秒
SAMPLES_PER_IP = 3  # 每个 IP 随机抽 3 个 ID 
MAX_WORKERS = 10    # 并行线程数 (GitHub 环境不宜过大)

# 确保目录存在
os.makedirs("py", exist_ok=True)

def test_stream_traffic(name, url):
    """模拟播放并统计流量，计算 Mbps"""
    ip_port = urlparse(url).netloc
    print(f"[开始测试] {name} ({ip_port})")
    start_time = time.time()
    total_bytes = 0
    speeds_mbps = []
    
    headers = {'User-Agent': 'Mozilla/5.0 (Viera; rv:34.0) Gecko/20100101 Firefox/34.0'}
    
    try:
        # 1. 获取 m3u8 索引
        r = requests.get(url, timeout=5, headers=headers, verify=False)
        if r.status_code != 200: return None
        
        # 简单提取 .ts 切片 (兼容相对和绝对路径)
        base_dir = url.rsplit('/', 1)[0]
        ts_lines = [line.strip() for line in r.text.split('\n') if line.strip() and not line.startswith('#')]
        if not ts_lines: return None

        # 2. 循环下载切片直到超时
        while time.time() - start_time < TEST_DURATION:
            # 模拟播放器行为：顺序下载最新的几个切片
            target_ts = ts_lines[-2:] if len(ts_lines) > 2 else ts_lines
            
            for ts_path in target_ts:
                if time.time() - start_time > TEST_DURATION: break
                
                # 拼接完整 TS URL
                ts_url = ts_path if ts_path.startswith('http') else f"{base_dir}/{ts_path}"
                
                # 开始下载切片
                ts_start = time.time()
                try:
                    ts_r = requests.get(ts_url, timeout=5, headers=headers, stream=True, verify=False)
                    chunk_bytes = 0
                    for chunk in ts_r.iter_content(chunk_size=1024*128): # 128KB 块
                        if chunk:
                            chunk_bytes += len(chunk)
                            total_bytes += len(chunk)
                            if time.time() - start_time > TEST_DURATION: break
                    
                    # 计算这个切片的瞬时速度 (Mbps)
                    ts_duration = time.time() - ts_start
                    if ts_duration > 0 and chunk_bytes > 1024*10: # 过滤太小的片
                        mbps = (chunk_bytes * 8) / (ts_duration * 1024 * 1024)
                        speeds_mbps.append(mbps)
                except:
                    continue
                    
            # 模拟切片播放间隔，防止请求过频
            time.sleep(2) 

    except Exception as e:
        print(f"[测试中断] {name}: {e}")
        return None

    # 3. 计算结果
    test_time = time.time() - start_time
    if test_time > 0 and speeds_mbps:
        avg_speed = (total_bytes * 8) / (test_time * 1024 * 1024)
        max_speed = max(speeds_mbps)
        min_speed = min(speeds_mbps)
        
        # 稳定性评估：(峰值-谷值)/平均值
        stability = 1 - ((max_speed - min_speed) / avg_speed) if avg_speed > 0 else 0
        stability = max(0, min(1, stability)) # 归一化到 0-1
        
        print(f"[报告] {name} | 平均: {avg_speed:.2f}Mbps | 峰值: {max_speed:.2f}Mbps")
        return {
            "name": name, 
            "ip_port": ip_port,
            "avg_mbps": round(avg_speed, 2), 
            "max_mbps": round(max_speed, 2),
            "stability": round(stability, 2)
        }
    return None

def save_reports(results, group_summary):
    """保存文本和 JSON 报告"""
    # 1. 保存详细文本报告 (TXT)
    with open(OUTPUT_TXT, 'w', encoding='utf-8') as f:
        f.write("="*70 + "\n")
        f.write(f"IPTV 酒店源 ID 流量与波动测试报告 ({time.strftime('%Y-%m-%d %H:%M:%S')})\n")
        f.write(f"测试时长: {TEST_DURATION}秒/ID | 抽样数: {SAMPLES_PER_IP} ID/IP\n")
        f.write("="*70 + "\n")
        f.write(f"{'服务器 (IP:Port)':<25} | {'频道名称':<20} | {'平均码率':<10} | {'峰值码率':<10} | {'稳定性'}\n")
        f.write("-" * 70 + "\n")
        
        for res in results:
            if res:
                stab_str = f"{res['stability']*100:.0f}%"
                f.write(f"{res['ip_port']:<25} | {res['name'][:18]:<20} | {res['avg_mbps']:<7}Mbps | {res['max_mbps']:<7}Mbps | {stab_str}\n")
        
        f.write("\n" + "="*70 + "\n")
        f.write("服务器综合评估 (Summary)\n")
        f.write("-" * 70 + "\n")
        f.write(f"{'服务器 (IP:Port)':<25} | {'存活ID数':<8} | {'综合均值':<10} | {'最高峰值':<10}\n")
        for ip, summ in group_summary.items():
            f.write(f"{ip:<25} | {summ['alive_count']:<8} | {summ['avg_mbps']:<7}Mbps | {summ['max_mbps']:<7}Mbps\n")
            
    # 2. 保存 JSON 报告
    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump({
            "meta": {
                "time": time.strftime('%Y-%m-%d %H:%M:%S'),
                "duration_per_id": TEST_DURATION,
                "samples_per_ip": SAMPLES_PER_IP
            },
            "summary": group_summary,
            "details": [r for r in results if r]
        }, f, ensure_ascii=False, indent=2)

def main():
    print(f"正在从 GitHub 获取 M3U 并解析...")
    try:
        r = requests.get(SOURCE_M3U_URL, timeout=10)
        content = r.text
    except:
        print(f"错误: 无法下载源 M3U 文件")
        return

    # 1. 分类 IP:Port
    groups = {}
    lines = content.split('\n')
    for i in range(len(lines)):
        if lines[i].startswith('#EXTINF') and i+1 < len(lines):
            url = lines[i+1].strip()
            if url.startswith('http') and 'txiptv' in url:
                ip_port = urlparse(url).netloc
                if ip_port not in groups: groups[ip_port] = []
                name = re.search(r',(.+)$', lines[i]).group(1).strip() if ',' in lines[i] else "Unknown"
                groups[ip_port].append((name, url))

    # 2. 抽样
    tasks = []
    for ip_port, urls in groups.items():
        if len(urls) >= SAMPLES_PER_IP:
            samples = random.sample(urls, SAMPLES_PER_IP)
        else:
            samples = urls # ID 数量少于 3 个则全测
        tasks.extend(samples)

    print(f"分析完成: 共检测到 {len(groups)} 个独立服务器。")
    print(f"决策: 随机抽取 {len(tasks)} 个 ID 进行高带宽流量压测 (预计耗时 {(len(tasks)/MAX_WORKERS*TEST_DURATION/60):.1f} 分钟)...")

    # 3. 并行测试
    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # 构造任务列表
        test_futures = [executor.submit(test_stream_traffic, n, u) for n, u in tasks]
        # 收集结果
        for future in test_futures:
            res = future.result()
            if res: results.append(res)

    # 4. 生成服务器综合评估 (Summary)
    group_summary = {}
    for res in results:
        if not res: continue
        ip = res['ip_port']
        if ip not in group_summary:
            group_summary[ip] = {"alive_count": 0, "avg_mbps_list": [], "max_mbps": 0}
        
        summary = group_summary[ip]
        summary["alive_count"] += 1
        summary["avg_mbps_list"].append(res['avg_mbps'])
        if res['max_mbps'] > summary["max_mbps"]:
            summary["max_mbps"] = res['max_mbps']

    # 计算最终均值
    for ip, data in group_summary.items():
        if data["avg_mbps_list"]:
            data["avg_mbps"] = round(sum(data["avg_mbps_list"]) / len(data["avg_mbps_list"]), 2)
        else:
            data["avg_mbps"] = 0
        del data["avg_mbps_list"] # 删除临时列表

    # 5. 保存报告
    save_reports(results, group_summary)
    print(f"\n--- 流量测试任务完成 ---")
    print(f"报告已保存至:")
    print(f"1. {OUTPUT_TXT} (易读文本)")
    print(f"2. {OUTPUT_JSON} (JSON 数据)")

if __name__ == "__main__":
    main()