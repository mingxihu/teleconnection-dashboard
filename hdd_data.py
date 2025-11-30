import requests
import re


def get_gas_hdd():
    """
    功能：从 NOAA 抓取【New England】, 【Middle Atlantic】, 【Midwest】, 【US Total】
    返回：包含 [实际值], [正常偏差], [去年偏差] 的字典
    """
    url = "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/cdus/degree_days/wsahddy.txt"
    # print(f"📡 正在连接 NOAA 数据库...")

    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200: return None

        lines = response.text.split('\n')
        data_bag = {}
        in_gas_section = False

        # 定义目标区域
        targets = {
            "NEW ENGLAND": "New England",
            "MIDDLE ATLANTIC": "Middle Atlantic",
            "E N CENTRAL": "Midwest (Chicago)",
            "UNITED STATES": "National (US Total)"
        }

        for line in lines:
            if "GAS HOME HEATING CUSTOMER WEIGHTED" in line:
                in_gas_section = True
                continue

            if in_gas_section:
                for keyword, clean_name in targets.items():
                    if keyword in line:
                        # 提取所有数字
                        numbers = re.findall(r'-?\d+', line)

                        # 我们需要前3个数字，所以确保至少抓到了3个
                        if len(numbers) >= 3:
                            data_bag[clean_name] = {
                                "actual": int(numbers[0]),  # 第1列: 本周实际值
                                "dev_normal": int(numbers[1]),  # 第2列: 比正常冷多少 (核心!)
                                "dev_last_year": int(numbers[2])  # 第3列: 比去年冷多少 (趋势!)
                            }

                # 抓齐4个就收工
                if len(data_bag) == 4:
                    break

        return data_bag

    except Exception as e:
        print(f"❌ 出错: {e}")
        return None


# --- 测试区 ---
if __name__ == "__main__":
    print("👨‍💻 正在测试 hdd_data.py ...")
    result = get_gas_hdd()

    if result:
        print("\n✅ 抓取成功！数据预览：")
        print(f"{'地区':<20} | {'实际 HDD':<10} | {'比正常':<10} | {'比去年':<10}")
        print("-" * 60)
        for region, data in result.items():
            print(f"{region:<20} | {data['actual']:<10} | {data['dev_normal']:<10} | {data['dev_last_year']:<10}")
    else:
        print("⚠️ 抓取失败")
