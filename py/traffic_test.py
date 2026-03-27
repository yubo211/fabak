import requests
import time
import random
import re
import os
import json
import urllib3
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor

# 禁用 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 配置 ---
# 如果文件在仓库里，直接写相对路径。建议加上绝对路径判断
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCE_M3U = os.path.join(BASE_DIR, "hotel_only.m3u") 
OUTPUT_TXT = os.path.join(BASE_DIR, "traffic_report.txt")
OUTPUT_JSON = os.path.join(BASE_DIR, "traffic_summary.json")

TEST_DURATION = 15  # 建议缩短到 15 秒，加快 GitHub 运行速度
SAMPLES_PER_IP = 3  
MAX_WORKERS = 10    

def test_stream_traffic(name, url):
    # ... (保持你之前的 test_stream_traffic 函数逻辑不变) ...
    # 确保函数内部使用的是你原本的逻辑
    pass 

# ... (保持其他辅助函数 save_reports 等不变) ...

def main():
    print(f"正在检查源文件: {SOURCE_M3U}")
    if not os.path.exists(SOURCE_M3U):
        print(f"错误: 找不到文件 {SOURCE_M3U}。请确保仓库中存在该文件。")
        # 尝试输出当前目录结构调试
        print(f"当前目录内容: {os.listdir(BASE_DIR)}")
        return

    with open(SOURCE_M3U, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. 解析逻辑 (保持不变)
    # ...
