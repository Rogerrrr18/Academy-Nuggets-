import requests
import time
from bs4 import BeautifulSoup
import os
import threading
import concurrent.futures
import random
import pandas as pd

# 锁对象，用于多线程安全
lock = threading.Lock()

# 创建 papers 文件夹用于保存文献
path = r"papers/"
if not os.path.exists(path):
    os.mkdir(path)

# 可用的 Sci-Hub 镜像列表
scihub_mirrors = [
    "https://www.sci-hub.ren/",
    "https://sci-hub.se/",
    "https://sci-hub.ru/",
    "https://sci-hub.st/"
]

# 随机 User-Agent 列表
user_agents = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36"
]

# 下载文献的函数
def download_paper(doi, index, retries=3):
    print(f"开始处理 DOI: {doi} (Index: {index})")
    for _ in range(retries):  # 尝试指定次数
        for mirror in scihub_mirrors:
            try:
                url = mirror + doi
                head = {"user-agent": random.choice(user_agents)}
                r = requests.get(url, headers=head, timeout=10)  # 设置超时
                if r.status_code == 200:
                    soup = BeautifulSoup(r.text, "html.parser")
                    if soup.iframe is None:
                        download_url = soup.embed.attrs.get("src")
                    else:
                        download_url = soup.iframe.attrs.get("src")
                    
                    if download_url:
                        if 'http' not in download_url:
                            download_url = 'https:' + download_url
                        download_r = requests.get(download_url, headers=head, timeout=10)
                        if download_r.status_code == 200 and download_r.content:
                            filename = f"{index}.pdf"  # 使用Excel A列的Index值作为文件名
                            with open(path + filename, "wb") as file:
                                file.write(download_r.content)
                            print(f"文献下载完成: {filename} (DOI: {doi})")
                            return  # 成功后直接退出函数
                        else:
                            print(f"下载失败，未获取内容: {doi}")
                    else:
                        print(f"未找到下载链接: {doi}")
                else:
                    print(f"请求失败，状态码: {r.status_code}, 镜像: {mirror}, DOI: {doi}")
            except Exception as e:
                print(f"镜像 {mirror} 出错: {e}, DOI: {doi}")
            time.sleep(random.uniform(2, 5))  # 随机延迟
    # 如果所有尝试均失败，记录错误
    print(f"完全失败，无法下载 DOI: {doi}")
    log_error(doi, index)

# 错误日志记录函数
def log_error(doi, index):
    with lock:
        with open("doi-nofinded-scihub.txt", "a+") as error_file:
            error_file.write(f"{index}: {doi}\n")

# 读取Excel文件中的DOI和Index数据
excel_file_path = "/Users/rogeryang/Desktop/文献数据挖掘/Task7.xlsx"
df = pd.read_excel(excel_file_path)

# Index在第1列（索引0），DOI在第5列（索引4）
index_column = 0  # Index列
doi_column = 4    # DOI列

# 获取Index和DOI数据
data = df[[df.columns[index_column], df.columns[doi_column]]].dropna()
indexes = data.iloc[:, 0].tolist()  # Index列
dois = data.iloc[:, 1].tolist()     # DOI列

print(f"从Excel文件读取到 {len(dois)} 个DOI和对应的Index")

# 使用线程池并打印运行流程
with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
    # 提交任务到线程池，传递DOI和对应的Index
    futures = [executor.submit(download_paper, doi, index) for doi, index in zip(dois, indexes)]

    # 等待任务完成并处理异常
    for future in concurrent.futures.as_completed(futures):
        try:
            result = future.result()
        except Exception as e:
            print(f"线程任务出错: {e}")
