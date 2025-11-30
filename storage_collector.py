import pandas as pd
import requests
import json
from datetime import datetime
import os

# === 配置区域 ===
HISTORY_FILE = "history_storage.csv"
URL_EIA = "https://ir.eia.gov/ngs/wngsr.json"


def fetch_eia_data():
    """
    抓取 EIA 最新库存报告。
    增强逻辑：手动查找 Year Ago 数据，防止 API 漏传。
    """
    print(f"   -> 正在连接 EIA 服务器...")
    try:
        response = requests.get(URL_EIA, timeout=30)
        if response.status_code != 200:
            print(f"❌ 连接失败: {response.status_code}")
            return None, None

        raw_data = response.content.decode("utf-8-sig")
        json_data = json.loads(raw_data)

        # 1. 获取关键日期
        report_date = json_data.get("current_week")  # 本周数据日期
        year_ago_date = json_data.get("year_ago")  # 去年对比日期

        print(f"   📅 EIA 报告日期: {report_date}")
        print(f"   🔙 去年对比日期: {year_ago_date}")

        data_bag = {}

        # 2. 遍历区域
        for series in json_data.get("series", []):
            name_raw = series.get("name", "").lower()

            prefix = None
            if name_raw.startswith("total lower 48"):
                prefix = "Total"
            elif name_raw.startswith("east"):
                prefix = "East"
            elif name_raw.startswith("midwest"):
                prefix = "Midwest"
            elif name_raw.startswith("south central"):
                prefix = "SouthCentral"

            if prefix:
                # === 核心修改：手动查找当前值和去年值 ===
                stock_val = None
                year_ago_val = None

                # 遍历该区域的所有历史数据
                for date_str, val in series.get("data", []):
                    if date_str == report_date:
                        stock_val = val
                    elif date_str == year_ago_date:
                        year_ago_val = val

                # 获取计算字段 (Net Change 还是直接用官方算好的比较稳)
                calc = series.get("calculated", {})

                # 如果手动没找到 year_ago (极少情况)，再尝试用 calc 里的补救
                if year_ago_val is None:
                    year_ago_val = calc.get("year_ago")

                data_bag[prefix] = {
                    "Stock": stock_val,
                    "Net_Change": calc.get("net_change"),
                    "Year_Ago": year_ago_val,  # 这里现在应该是实打实的数值了
                    "Avg_5Yr": calc.get("5yr-avg")
                }

        return data_bag, report_date

    except Exception as e:
        print(f"❌ 解析错误: {e}")
        return None, None


def run_collector():
    run_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    run_date_str = datetime.now().strftime('%Y-%m-%d')

    print(f"🚀 [Storage Collector V2] 任务启动: {run_time_str}")

    current_data, report_date = fetch_eia_data()

    if not current_data or not report_date:
        print("❌ 未获取到有效数据")
        return

    # 构造保存行
    new_row = {
        'Run_Date': run_date_str,
        'Report_Date': report_date,
        'Update_Time': run_time_str
    }

    # 填充数据
    for prefix, values in current_data.items():
        new_row[f"{prefix}_Stock"] = values.get("Stock")
        new_row[f"{prefix}_Net_Change"] = values.get("Net_Change")
        new_row[f"{prefix}_Year_Ago"] = values.get("Year_Ago")
        new_row[f"{prefix}_5Yr_Avg"] = values.get("Avg_5Yr")

    print("   📊 数据校验:")
    print(f"      - Total Stock: {new_row.get('Total_Stock')}")
    print(f"      - Total Year Ago: {new_row.get('Total_Year_Ago')} (应有数值)")

    # 存入 CSV
    if os.path.exists(HISTORY_FILE):
        df = pd.read_csv(HISTORY_FILE)
        if run_date_str in df['Run_Date'].values:
            print("   🔄 覆盖今日旧数据...")
            df = df[df['Run_Date'] != run_date_str]
        new_df = pd.DataFrame([new_row])
        df = pd.concat([df, new_df], ignore_index=True)
    else:
        print(f"   ✨ 初始化数据库: {HISTORY_FILE}")
        df = pd.DataFrame([new_row])

    # 排序与保存
    cols = list(df.columns)
    priority = ['Run_Date', 'Report_Date']
    for c in priority:
        if c in cols: cols.remove(c)
    final_cols = priority + cols

    df = df[final_cols].sort_values(by='Run_Date')
    df.to_csv(HISTORY_FILE, index=False)
    print(f"✅ [成功] EIA 数据已保存 (包含 Year Ago)。")


if __name__ == "__main__":
    run_collector()
