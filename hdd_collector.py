import pandas as pd
import requests
import io
from datetime import datetime
import os
import re

# ==========================================
# 1. 配置区域 (Configuration)
# ==========================================

HISTORY_FILE = "history_hdd.csv"
URL_HDD = "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/cdus/degree_days/wsahddy.txt"

# 地区映射表
TARGET_REGIONS = {
    "NEW ENGLAND": "NE",
    "MIDDLE ATLANTIC": "MA",
    "E N CENTRAL": "MW",
    "UNITED STATES": "US"
}


# ==========================================
# 2. 功能函数 (Functions)
# ==========================================

def get_source_date(text_content):
    """
    【关键修改】精准提取文件中的截止日期。
    目标句式: "LAST DATE OF DATA COLLECTION PERIOD IS NOV 22, 2025"
    """
    try:
        # 正则逻辑：
        # LAST DATE... IS  -> 固定前缀
        # (\w+)            -> 捕获月份 (NOV)
        # (\d+)            -> 捕获日期 (22)
        # ,                -> 匹配逗号
        # (\d{4})          -> 捕获年份 (2025)
        pattern = r"LAST DATE OF DATA COLLECTION PERIOD IS\s+(\w+)\s+(\d+),\s+(\d{4})"

        match = re.search(pattern, text_content, re.IGNORECASE)
        if match:
            month_str = match.group(1)
            day_str = match.group(2)
            year_str = match.group(3)

            # 拼接成标准格式字符串: "NOV 22 2025"
            full_date_str = f"{month_str} {day_str} {year_str}"

            # 转换为日期对象
            date_obj = datetime.strptime(full_date_str, "%b %d %Y")
            return date_obj.strftime("%Y-%m-%d")

    except Exception as e:
        print(f"⚠️ 警告: 无法解析源数据日期，错误: {e}")

    return "Unknown"


def fetch_hdd_data():
    print(f"   -> 正在连接 NOAA 服务器...")
    try:
        response = requests.get(URL_HDD, timeout=30)
        if response.status_code != 200:
            print("❌ 下载失败")
            return None, None

        text_content = response.text

        # 1. 获取数据的“出厂日期” (Source Date)
        source_date = get_source_date(text_content)
        print(f"   📅 识别到数据截止日期 (Source Date): {source_date}")

        # 2. 逐行扫描文本，提取数据
        lines = text_content.split('\n')
        data_bag = {}
        in_gas_section = False

        for line in lines:
            if "GAS HOME HEATING CUSTOMER WEIGHTED" in line:
                in_gas_section = True
                continue

            if in_gas_section:
                for raw_name, prefix in TARGET_REGIONS.items():
                    if raw_name in line:
                        # 提取这一行所有的数字
                        numbers = re.findall(r'-?\d+', line)

                        if len(numbers) >= 4:
                            data_bag[prefix] = {
                                "Actual": int(numbers[0]),
                                "Dev_Norm": int(numbers[1]),
                                "Dev_Year": int(numbers[2]),
                                "Seas_Total": int(numbers[3])
                            }

                if len(data_bag) == len(TARGET_REGIONS):
                    break

        return data_bag, source_date

    except Exception as e:
        print(f"❌ 解析过程出错: {e}")
        return None, None


def run_collector():
    # 获取当前运行脚本的时间
    run_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    run_date_str = datetime.now().strftime('%Y-%m-%d')

    print(f"🚀 [hdd_collector.py] 任务启动: {run_time_str}")

    # 1. 执行抓取
    current_data, source_date = fetch_hdd_data()

    if not current_data:
        print("❌ 未获取到有效数据，任务终止。")
        return

    # 2. 构造保存行
    new_row = {
        'Run_Date': run_date_str,
        'Source_Date': source_date,  # 这里的日期应该是根据您文件里读到的 NOV 22, 2025 生成的
        'Update_Time': run_time_str
    }

    for prefix, values in current_data.items():
        new_row[f"{prefix}_Actual"] = values['Actual']
        new_row[f"{prefix}_Dev_Norm"] = values['Dev_Norm']
        new_row[f"{prefix}_Dev_Year"] = values['Dev_Year']
        new_row[f"{prefix}_Seas_Total"] = values['Seas_Total']

    print("   📊 抓取样本 (New England):")
    print(f"      - Actual: {new_row.get('NE_Actual')}")
    print(f"      - Source Date: {new_row.get('Source_Date')}")

    # 3. 保存到 CSV
    if os.path.exists(HISTORY_FILE):
        df = pd.read_csv(HISTORY_FILE)
        # 如果今天跑过，覆盖今天的记录
        if run_date_str in df['Run_Date'].values:
            print("   🔄 今天已运行过，正在覆盖旧记录...")
            df = df[df['Run_Date'] != run_date_str]

        new_df = pd.DataFrame([new_row])
        df = pd.concat([df, new_df], ignore_index=True)

    else:
        print(f"   ✨ 第一次运行，创建文件: {HISTORY_FILE}")
        df = pd.DataFrame([new_row])

    # 4. 整理列顺序
    cols = list(df.columns)
    if 'Run_Date' in cols: cols.remove('Run_Date')
    if 'Source_Date' in cols: cols.remove('Source_Date')
    final_cols = ['Run_Date', 'Source_Date'] + cols

    df = df[final_cols].sort_values(by='Run_Date')

    df.to_csv(HISTORY_FILE, index=False)
    print(f"✅ [成功] 数据已保存至 {HISTORY_FILE}")


if __name__ == "__main__":
    run_collector()
