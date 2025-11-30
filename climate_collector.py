import pandas as pd
from datetime import datetime
import os

# === 配置区域 ===
HISTORY_FILE = "history_weather.csv"

# 数据源字典 (全部使用 GEFS 集合预报源)
DATA_SOURCES = {
    "AO": "https://ftp.cpc.ncep.noaa.gov/cwlinks/norm.daily.ao.gefs.z1000.120days.csv",
    "NAO": "https://ftp.cpc.ncep.noaa.gov/cwlinks/norm.daily.nao.gefs.z500.120days.csv",
    "PNA": "https://ftp.cpc.ncep.noaa.gov/cwlinks/norm.daily.pna.gefs.z500.120days.csv"
}


def fetch_index_data(name, url):
    """
    通用抓取函数：传入指标名称和 URL
    返回：该指标当天的 {Obs, Day7, Day10, Day14}
    """
    print(f"   -> 正在下载 {name} 数据 (GEFS)...")
    try:
        df = pd.read_csv(url)
        df['time'] = pd.to_datetime(df['time'])

        # 1. 锁定最新日期
        latest_date = df['time'].max()

        # 2. 提取今日数据
        today_df = df[df['time'] == latest_date]

        if today_df.empty:
            print(f"      ⚠️ 警告: {name} 今日数据尚未生成")
            return None

        # 3. 计算所有成员的平均值 (Ensemble Mean)
        col_name = f"{name.lower()}_index"
        daily_means = today_df.groupby('lead')[col_name].mean()

        return {
            "date": latest_date,
            "obs": daily_means.get(0),  # 历史观测
            "d7": daily_means.get(7),  # 短期预测
            "d10": daily_means.get(10),  # [新增] 中期预测
            "d14": daily_means.get(14)  # 长期预测
        }
    except Exception as e:
        print(f"❌ {name} 下载失败: {e}")
        return None


def run_collector():
    print(f"🚀 [Climate Collector] 启动任务: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    results = {}
    target_date = None

    # 1. 分别抓取 AO, NAO, PNA
    for index_name, url in DATA_SOURCES.items():
        data = fetch_index_data(index_name, url)
        if data:
            results[index_name] = data
            if target_date is None:
                target_date = data['date']

    if not results:
        print("❌ 所有数据源均下载失败，任务终止。")
        return

    # 2. 构造数据行
    date_str = target_date.strftime('%Y-%m-%d')
    print(f"   📅 锁定入库日期: {date_str}")

    new_row = {
        'Date': date_str,
        'Update_Time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }

    # 动态填充数据 (Obs, Day7, Day10, Day14)
    for name in ["AO", "NAO", "PNA"]:
        data = results.get(name)
        if data and data['date'] == target_date:
            new_row[f'{name}_Obs'] = round(data['obs'], 4)
            new_row[f'{name}_Day7'] = round(data['d7'], 4)
            new_row[f'{name}_Day10'] = round(data['d10'], 4)  # [新增]
            new_row[f'{name}_Day14'] = round(data['d14'], 4)

            print(
                f"      ✅ {name:<3} | Obs:{new_row[f'{name}_Obs']:>6} | D7:{new_row[f'{name}_Day7']:>6} | D10:{new_row[f'{name}_Day10']:>6} | D14:{new_row[f'{name}_Day14']:>6}")
        else:
            print(f"      ⚠️ {name} 数据缺失")
            for suffix in ['_Obs', '_Day7', '_Day10', '_Day14']:
                new_row[f'{name}{suffix}'] = None

    # 3. 存入 CSV
    if os.path.exists(HISTORY_FILE):
        history_df = pd.read_csv(HISTORY_FILE)
        # 覆盖今日旧数据
        if new_row['Date'] in history_df['Date'].astype(str).values:
            print("   🔄 覆盖今日旧数据...")
            history_df = history_df[history_df['Date'] != new_row['Date']]

        new_df = pd.DataFrame([new_row])
        history_df = pd.concat([history_df, new_df], ignore_index=True)
    else:
        print(f"   ✨ 初始化数据库: {HISTORY_FILE}")
        history_df = pd.DataFrame([new_row])

    # 排序并调整列顺序
    history_df = history_df.sort_values(by='Date')

    # 智能调整列顺序: Date在前, Update_Time在后, 其他中间
    cols = ['Date'] + [c for c in history_df.columns if c not in ['Date', 'Update_Time']] + ['Update_Time']
    history_df = history_df[cols]

    history_df.to_csv(HISTORY_FILE, index=False)
    print(f"✅ [成功] 数据库已更新: {HISTORY_FILE}")


if __name__ == "__main__":
    run_collector()
