import re
import os

# 配置路径
input_file = '/volume1/web/2222.txt'
output_file = '/volume1/web/links.txt'

# 固定模板：ID 锁定为 1000
url_template = "http://{ip_port}/iptv/live/1000.json?key=txipt"

def generate_fixed():
    if not os.path.exists(input_file):
        print(f"找不到文件: {input_file}")
        return

    # 使用 set 自动去重
    unique_links = set()
    
    # 正则表达式：只匹配 http:// 后面到第一个斜杠前的 IP:端口
    ip_pattern = r'http://([\d\.]+:\d+)'
    
    with open(input_file, 'r', encoding='utf-8') as f:
        for line in f:
            match = re.search(ip_pattern, line)
            if match:
                ip_port = match.group(1)
                # 生成固定 ID 为 1000 的链接
                full_link = url_template.format(ip_port=ip_port)
                unique_links.add(full_link)

    # 写入文件
    with open(output_file, 'w', encoding='utf-8') as f:
        # 将去重后的结果转为列表并换行写入
        f.write('\n'.join(sorted(list(unique_links))) + '\n')

    print(f"处理完成！提取并去重后共有 {len(unique_links)} 个唯一服务器地址。")

if __name__ == '__main__':
    generate_fixed()