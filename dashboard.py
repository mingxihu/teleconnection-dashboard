import streamlit as st
from datetime import datetime, timedelta
import requests
import io
import re
from pypdf import PdfReader
import pandas as pd
import json
import os
from streamlit_autorefresh import st_autorefresh

# === 1. 页面全局配置 ===
st.set_page_config(
    page_title="Climate–Natural Gas Analytics",
    page_icon="⚛️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# === [配置] 自动刷新 (1小时) ===
st_autorefresh(interval=3600000, key="data_refresh_key")

# === 2. 样式优化 (CSS) ===
st.markdown("""
    <style>
    [data-testid="stSidebar"] { background-color: #f8f9fa; }

    /* 侧边栏顶部紧凑模式 */
    section[data-testid="stSidebar"] .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }

    /* Tabs 样式 */
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] {
        height: 45px; white-space: pre-wrap; padding: 8px 16px; 
        background-color: #fff; border-radius: 4px; border: 1px solid #e0e0e0;
    }
    .stTabs [aria-selected="true"] {
        background-color: #e3f2fd; border-left: 4px solid #1565c0; color: #1565c0;
    }

    /* [核心颜色统一] Bullish (Negative/Cold) = Green; Bearish (Positive/Warm) = Red */
    .tag-minus {
        background-color: #e8f5e9; color: #2e7d32; /* 绿色: 负相位/寒冷/利多 */
        padding: 4px 12px; border-radius: 6px; font-weight: 700; font-size: 1.1em; 
        border: 1px solid #c8e6c9; display: inline-block; margin: 4px 0;
    }
    .tag-plus {
        background-color: #e8f5e9; color: #2e7d32; /* [FIXED] 绿色: 正相位/PNA/利多 */
        padding: 4px 12px; border-radius: 6px; font-weight: 700; font-size: 1.1em;
        border: 1px solid #c8e6c9; display: inline-block; margin: 4px 0;
    }

        .tag-bear {
        background-color: #ffebee; 
        color: #c62828;               /* 红色：暖冬/利空 */
        padding: 4px 12px; 
        border-radius: 6px; 
        font-weight: 700; 
        font-size: 1.1em;
        border: 1px solid #ffcdd2; 
        display: inline-block; 
        margin: 4px 0;
    }

    .tag-neutral {
        background-color: #f5f5f5; color: #616161; 
        padding: 4px 12px; border-radius: 6px; font-weight: 700; font-size: 1.1em;
        border: 1px solid #e0e0e0; display: inline-block; margin: 4px 0;
    }

    /* 信号框样式 */
    .signal-box-bull {
        background-color: #fff; border-left: 4px solid #c62828;
        padding: 16px; border-radius: 8px; margin-top: 10px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
        border: 1px solid #f0f0f0;
    }

    /* 决策矩阵排版样式 */
    .decision-content {
        margin-top: 10px;
        font-size: 0.95em;
        line-height: 1.6;
    }
    .decision-label {
        font-weight: 700; 
        color: #212121;
        display: block; 
        margin-top: 10px;
        margin-bottom: 4px;
    }

    .zoom-img:hover { opacity: 0.9; cursor: zoom-in; transition: 0.3s; }
    </style>
""", unsafe_allow_html=True)

# === 3. 核心数据源 ===
IMG_URLS = {
    "AO": "https://www.cpc.ncep.noaa.gov/products/precip/CWlink/daily_ao_index/ao.gefs.sprd2.png",
    "NAO": "https://www.cpc.ncep.noaa.gov/products/precip/CWlink/pna/nao.gefs.sprd2.png",
    "PNA": "https://www.cpc.ncep.noaa.gov/products/precip/CWlink/pna/pna.gefs.sprd2.png",
    "LANINA": "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/lanina/enso_evolution-status-fcsts-web.pdf"
}

LINKS = {
    "NOAA_HOME": "https://www.cpc.ncep.noaa.gov/",
    "YAHOO_NG": "https://finance.yahoo.com/quote/NG=F",
    "YAHOO_EQT": "https://finance.yahoo.com/quote/EQT",
    "YAHOO_BOIL": "https://finance.yahoo.com/quote/BOIL",
    "YAHOO_CSX": "https://finance.yahoo.com/quote/CSX",
    "YAHOO_UNP": "https://finance.yahoo.com/quote/UNP",
    "YAHOO_UAL": "https://finance.yahoo.com/quote/UAL",
}


# === 辅助函数定义 (必须在调用前) ===

def clickable_image_html(img_url, alt_text):
    html_code = f'''
    <a href="{img_url}" target="_blank">
        <img src="{img_url}" class="zoom-img" style="width:100%; border-radius:5px; border:1px solid #ddd;" alt="{alt_text}">
    </a>
    '''
    st.markdown(html_code, unsafe_allow_html=True)


def signal_card(title, dynamics, impact, signal_text):
    html = f"""
<div class="signal-box-bull">
    <div style="font-size: 1.15em; font-weight: bold; margin-bottom: 12px; color: #212121;">{title}</div>
    <div style="margin-bottom: 8px; color: #424242;">
        🌪️ <b>动力学:</b> {dynamics}
    </div>
    <div style="margin-bottom: 12px; color: #424242;">
        🥶 <b>影响:</b> {impact.replace('**', '')} 
    </div>
    <div style="background-color: #ffebee; padding: 8px; border-radius: 4px; color: #c62828; font-weight: bold;">
        🔥 信号: {signal_text}
    </div>
</div>
"""
    st.markdown(html, unsafe_allow_html=True)


# === [保留] 提取本地历史数据最新行 (供 NCRI 和 Tab 展示使用) ===
def load_latest_climate_data():
    """从本地 CSV 文件读取最新一行的 AO/NAO/PNA 数据。"""
    HISTORY_FILE = "history_weather.csv"
    try:
        if not os.path.exists(HISTORY_FILE):
            return None
        df = pd.read_csv(HISTORY_FILE)
        # 返回 DataFrame 的最后一行（即最新的数据）
        return df.iloc[-1].to_dict()
    except Exception as e:
        return None


# === [保留] 辅助函数 - 显示当前气象指标的值 (供 Tab 使用) ===
def display_current_index_value(index_name):
    global latest_data

    if latest_data:
        # 获取 CSV 中的值
        obs_val = latest_data.get(f'{index_name}_Obs')
        d7_val = latest_data.get(f'{index_name}_Day7')
        d10_val = latest_data.get(f'{index_name}_Day10')

        # === 核心颜色逻辑：根据指标确定 Bullish/Bearish (Green/Red) ===
        is_nao_ao = index_name in ["NAO", "AO"]

        def get_style(value):
            if value is None: return "color: #888;", "-"
            is_positive = value > 0
            # AO/NAO: 负值是利多 (Green)
            if is_nao_ao:
                is_bullish = not is_positive
            # PNA: 正值是利多 (Green)
            else:
                is_bullish = is_positive
            color = "#2e7d32" if is_bullish else "#c62828"  # Green or Red
            arrow = "▲" if is_bullish else "▼"
            return f"color: {color};", arrow

        obs_style, obs_arrow = get_style(obs_val)
        d7_style, d7_arrow = get_style(d7_val)
        d10_style, d10_arrow = get_style(d10_val)

        col1, col2, col3 = st.columns(3)

        # 1. 今日观测
        with col1:
            st.markdown(f"**今日实况 (Observed):**")
            st.markdown(
                f"<span style='font-size: 1.8em; font-weight: bold; {obs_style}'>{obs_arrow} {obs_val:.3f}</span>",
                unsafe_allow_html=True)

        # 2. 7天预测
        with col2:
            st.markdown(f"**7天预测 (Forecast Day 7):**")
            st.markdown(f"<span style='font-size: 1.8em; font-weight: bold; {d7_style}'>{d7_arrow} {d7_val:.3f}</span>",
                        unsafe_allow_html=True)

        # 3. 10天预测
        with col3:
            st.markdown(f"**10天预测 (Forecast Day 10):**")
            st.markdown(
                f"<span style='font-size: 1.8em; font-weight: bold; {d10_style}'>{d10_arrow} {d10_val:.3f}</span>",
                unsafe_allow_html=True)

        st.markdown("---")
    else:
        st.warning("⚠️ 数据库尚未更新，请运行 'climate_collector.py' 获取数据。")


# === HDD 数据抓取函数 (改为读取 CSV) ===
# [修改说明] 恢复使用 @st.cache 以兼容旧版本
@st.cache(ttl=60, suppress_st_warning=True)
def get_gas_hdd():
    csv_file = "history_hdd.csv"
    try:
        if not os.path.exists(csv_file):
            return None

        df = pd.read_csv(csv_file)
        if df.empty: return None

        # 取最新一行
        latest = df.iloc[-1]

        data_bag = {
            "New England": {
                "actual": latest.get("NE_Actual", 0),
                "dev_normal": latest.get("NE_Dev_Norm", 0),
                "dev_last_year": latest.get("NE_Dev_Year", 0)
            },
            "Middle Atlantic": {
                "actual": latest.get("MA_Actual", 0),
                "dev_normal": latest.get("MA_Dev_Norm", 0),
                "dev_last_year": latest.get("MA_Dev_Year", 0)
            },
            "Midwest": {
                "actual": latest.get("MW_Actual", 0),
                "dev_normal": latest.get("MW_Dev_Norm", 0),
                "dev_last_year": latest.get("MW_Dev_Year", 0)
            },
            "US Total": {
                "actual": latest.get("US_Actual", 0),
                "dev_normal": latest.get("US_Dev_Norm", 0),
                "dev_last_year": latest.get("US_Dev_Year", 0)
            }
        }
        return data_bag
    except Exception as e:
        return None


# === ENSO 报告解析 (保持爬虫) ===
# [修改说明] 恢复使用 @st.cache
@st.cache(ttl=3600, suppress_st_warning=True)
def get_enso_summary(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=15, verify=False)
        if response.status_code == 200:
            f = io.BytesIO(response.content)
            reader = PdfReader(f)
            raw_text = ""
            for i in range(min(5, len(reader.pages))):
                page_text = reader.pages[i].extract_text()
                if "ENSO Alert System Status" in page_text:
                    raw_text = page_text
                    break
            if not raw_text: return {"status": "未找到 Summary", "body": []}

            status_line = "Unknown"
            if "ENSO Alert System Status:" in raw_text:
                parts = raw_text.split("ENSO Alert System Status:", 1)
                temp = parts[1].strip()
                status_line = temp.split("\n")[0]
                raw_text = parts[1].replace(status_line, "", 1)

            if "* Note" in raw_text:
                raw_text = raw_text.split("* Note", 1)[0]
            elif "Note:" in raw_text:
                raw_text = raw_text.split("Note:", 1)[0]

            clean_text = raw_text.replace("\n", " ")
            clean_text = re.sub(' +', ' ', clean_text).strip()
            sentences = clean_text.split('. ')
            formatted_sentences = [s.strip() + "." for s in sentences if len(s) > 5]
            return {"status": status_line, "body": formatted_sentences}
    except Exception as e:
        return {"status": "Error", "body": [str(e)]}
    return {"status": "Error", "body": []}


# === EIA 数据解析 (改为读取 CSV) ===
# [修改说明] 恢复使用 @st.cache
@st.cache(ttl=60, suppress_st_warning=True)
def load_eia_total():
    csv_file = "history_storage.csv"
    try:
        if not os.path.exists(csv_file):
            return None

        df_csv = pd.read_csv(csv_file)
        if df_csv.empty: return None

        # 取最新一行
        latest = df_csv.iloc[-1]

        # 1. 恢复列名格式 (日期)
        report_date_str = latest.get("Report_Date", "")

        try:
            current_date_obj = datetime.strptime(report_date_str, "%Y-%m-%d")
            week_ago_obj = current_date_obj - timedelta(days=7)
            curr_fmt = current_date_obj.strftime("%m/%d/%y")
            prev_fmt = week_ago_obj.strftime("%m/%d/%y")
        except:
            curr_fmt = "Current"
            prev_fmt = "Prev Week"

        # 2. 构造列名列表
        labels = [curr_fmt, prev_fmt, "Net change (Bcf)",
                  "Year ago (Bcf)", "Year-ago % change",
                  "5-yr avg (Bcf)", "5-yr % change"]

        # 3. 辅助计算函数
        def calc_pct(curr, base):
            try:
                if base is None or base == 0: return None
                return ((curr - base) / base) * 100
            except:
                return None

        rows = []

        # --- Total Lower 48 ---
        t_stock = latest.get("Total_Stock")
        t_net = latest.get("Total_Net_Change")
        t_yr = latest.get("Total_Year_Ago")
        t_avg = latest.get("Total_5Yr_Avg")

        t_prev = t_stock - t_net if (t_stock is not None and t_net is not None) else None

        r1 = {
            "Region": "Total",
            labels[0]: t_stock,
            labels[1]: t_prev,
            labels[2]: t_net,
            labels[3]: t_yr,
            labels[4]: calc_pct(t_stock, t_yr),
            labels[5]: t_avg,
            labels[6]: calc_pct(t_stock, t_avg)
        }
        rows.append(r1)

        # --- East ---
        e_stock = latest.get("East_Stock")
        e_net = latest.get("East_Net_Change")
        e_yr = latest.get("East_Year_Ago")
        e_avg = latest.get("East_5Yr_Avg")

        e_prev = e_stock - e_net if (e_stock is not None and e_net is not None) else None

        r2 = {
            "Region": "East",
            labels[0]: e_stock,
            labels[1]: e_prev,
            labels[2]: e_net,
            labels[3]: e_yr,
            labels[4]: calc_pct(e_stock, e_yr),
            labels[5]: e_avg,
            labels[6]: calc_pct(e_stock, e_avg)
        }
        rows.append(r2)

        df_display = pd.DataFrame(rows).set_index("Region")

        return df_display

    except Exception as e:
        return None


# === 4. 侧边栏导航 ===
with st.sidebar:
    st.markdown("## ⚛️ 核心监控数据")

    # ---- HDD 数据板块 ----
    st.subheader("🔥 实际燃烧需求 (HDD)")

    hdd_data = get_gas_hdd()

    if hdd_data:
        def show_dual_metric(col, label, data):
            actual = data.get('actual', '-')
            dev_norm = data.get('dev_normal', 0)
            dev_year = data.get('dev_last_year', 0)

            with col:
                st.metric(
                    label=label,
                    value=f"{actual}",
                    delta=f"{dev_norm} (Norm)",
                    delta_color="normal"
                )
                color = "#2e7d32" if dev_year > 0 else "#c62828"
                arrow = "▲" if dev_year > 0 else "▼"
                if dev_year == 0:
                    color = "#666"
                    arrow = "-"

                st.markdown(
                    f"""<div style="margin-top: -15px; font-size: 0.85em; color: #555;">vs Year: <span style="color: {color}; font-weight: bold;">{arrow} {dev_year}</span></div>""",
                    unsafe_allow_html=True)


        hd_col1, hd_col2 = st.columns(2)
        show_dual_metric(hd_col1, "New England", hdd_data.get('New England', {}))
        show_dual_metric(hd_col2, "Mid-Atlantic", hdd_data.get('Middle Atlantic', {}))
        show_dual_metric(hd_col1, "Midwest", hdd_data.get('Midwest', {}))
        show_dual_metric(hd_col2, "US Total", hdd_data.get('US Total', {}))

        st.caption("[NOAA HDD Data](https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/cdus/degree_days/)")

    else:
        st.warning("HDD 数据暂不可用")

    st.markdown("---")

    # ---- EIA 模块 ----
    st.markdown("### 🏦 EIA 天然气库存")
    try:
        eia_df = load_eia_total()
        if eia_df is not None:
            tdf = eia_df.T


            def num_fmt(x):
                if pd.isna(x): return ""
                v = float(x)
                if abs(v - round(v)) < 1e-6: return f"{int(round(v)):,d}"
                return f"{v:.1f}".rstrip("0").rstrip(".")


            highlight_rows = ["Net change (Bcf)", "Year-ago % change", "5-yr % change"]


            def highlight_style(df):
                styles = pd.DataFrame('font-weight: bold;', index=df.index, columns=df.columns)
                for idx in df.index:
                    if idx in highlight_rows:
                        for col in df.columns:
                            val = df.loc[idx, col]
                            base = 'font-weight: bold; background-color: #fff3cd;'
                            # 下降（负值）= 库存减少 = 利多 = 绿色
                            # 上升（正值）= 库存增加 = 利空 = 红色
                            if pd.notna(val):
                                if val < 0:
                                    styles.loc[idx, col] = base + 'color: #2e7d32;'
                                elif val > 0:
                                    styles.loc[idx, col] = base + 'color: #c62828;'
                                else:
                                    styles.loc[idx, col] = base + 'color: black;'
                            else:
                                styles.loc[idx, col] = base + 'color: black;'
                return styles


            st.dataframe(tdf.style.format(num_fmt).apply(highlight_style, axis=None))
        else:
            st.write("未找到 EIA 数据。")
    except Exception as e:
        st.warning(f"EIA Error: {e}")

    st.caption("[EIA Weekly Report](https://ir.eia.gov/ngs/ngs.html)")
    st.markdown("---")

    # ---- 其它导航 ----
    st.markdown("### 🏛️ 官方数据源")
    st.markdown(f"- [NOAA CPC 气候预测]({LINKS['NOAA_HOME']})")
    st.markdown(f"- [**ENSO / 拉尼娜周报**]({IMG_URLS['LANINA']})")

    st.markdown("### ⚡ 能源行情")
    st.markdown(f"- [**NG=F** (天然气期货)]({LINKS['YAHOO_NG']})")
    st.markdown(f"- [**EQT** (生产商股价)]({LINKS['YAHOO_EQT']})")
    st.markdown(f"- [**BOIL** (2倍做多ETF)]({LINKS['YAHOO_BOIL']})")

    st.markdown("### 🚂 交通运输")
    st.markdown(f"- [**CSX** (美东铁路)]({LINKS['YAHOO_CSX']})")
    st.markdown(f"- [**UNP** (联合太平洋)]({LINKS['YAHOO_UNP']})")
    st.markdown(f"- [**UAL** (联合航空)]({LINKS['YAHOO_UAL']})")

    st.caption("Geoscience & Financial Analytics MH")

# === 5. 主界面 ===
st.title("⚛️ 天然气气象分析终端 (Climate–Natural Gas Analytics)")
st.caption(
    f"**数据更新 (Last Updated):** `{datetime.now().astimezone().strftime('%Y-%m-%d %H:%M %Z')}`")
st.markdown("---")

# [新增] 辅助函数调用：在主界面头部调用一次，供 Tabs 读取 CSV
latest_data = load_latest_climate_data()


# [新增] 辅助函数 - 显示当前气象指标的值
def display_current_index_value(index_name):
    if latest_data:
        # 获取 CSV 中的值
        obs_val = latest_data.get(f'{index_name}_Obs')
        d7_val = latest_data.get(f'{index_name}_Day7')
        d10_val = latest_data.get(f'{index_name}_Day10')

        # === 核心颜色逻辑：根据指标确定 Bullish/Bearish (Green/Red) ===
        is_nao_ao = index_name in ["NAO", "AO"]

        def get_style(value):
            if value is None: return "color: #888;", "-"

            is_positive = value > 0

            # AO/NAO: 负值是利多 (Green)
            if is_nao_ao:
                is_bullish = not is_positive
                # PNA: 正值是利多 (Green)
            else:
                is_bullish = is_positive

            color = "#2e7d32" if is_bullish else "#c62828"  # Green or Red
            arrow = "▲" if is_bullish else "▼"

            return f"color: {color};", arrow

        obs_style, obs_arrow = get_style(obs_val)
        d7_style, d7_arrow = get_style(d7_val)
        d10_style, d10_arrow = get_style(d10_val)

        # [修改] 布局从 st.markdown 迁移到自定义 HTML 卡片
        html_card = f"""
        <div style='
            margin-top: 15px; 
            border: 1px solid #e0e0e0; 
            border-radius: 6px; 
            padding: 8px; 
            background-color: #f8f8f8;
            display: flex; 
            justify-content: space-around;
            text-align: center;
            font-size: 0.95em;
        '>
            <div style='flex:1; border-right: 1px solid #eee;'>
                <span style='font-weight: bold; color: #555;'>OBSERVED (Today)</span><br>
                <span style='font-size: 1.3em; {obs_style}; font-weight: bold;'>{obs_val:.3f}</span>
            </div>
            <div style='flex:1; border-right: 1px solid #eee;'>
                <span style='font-weight: bold; color: #555;'>DAY 7 FORECAST</span><br>
                <span style='font-size: 1.3em; {d7_style}; font-weight: bold;'>{d7_val:.3f}</span>
            </div>
            <div style='flex:1;'>
                <span style='font-weight: bold; color: #555;'>DAY 10 FORECAST</span><br>
                <span style='font-size: 1.3em; {d10_style}; font-weight: bold;'>{d10_val:.3f}</span>
            </div>
        </div>
        """
        st.markdown(html_card, unsafe_allow_html=True)
    else:
        st.warning("⚠️ 数据库尚未更新，请运行 'climate_collector.py' 获取数据。")


# === 6. 核心气象板块 (4 Tabs) ===
st.subheader("📡 大气遥相关机制 (Atmospheric Teleconnections)")
st.caption("注：图表展示 GEFS 集合预报发散度。红线 (Mean) 代表主流趋势。")

tab_nao, tab_ao, tab_pna, tab_enso = st.tabs([
    "1. 北大西洋涛动 (NAO)", "2. 北极涛动 (AO)", "3. 太平洋-北美模式 (PNA)", "🌊 NOAA ENSO 周报"
])

with tab_nao:
    col_img, col_content = st.columns([1, 1.5])
    with col_img: clickable_image_html(IMG_URLS["NAO"], "NAO")
    with col_content:
        st.markdown("<div class='tag-minus'>📉 负相位 / Negative (-)</div>", unsafe_allow_html=True)
        signal_card("阻塞效应 (Blocking)", "西风急流弯曲，格陵兰高压形成。", "冷气团在美东<b>停滞不前</b>。",
                    "极强利多 (寒潮持续)")

        # [NEW] NAO 数据卡片 - 放置在信号卡片下方
        display_current_index_value("NAO")

with tab_ao:
    col_img, col_content = st.columns([1, 1.5])
    with col_img: clickable_image_html(IMG_URLS["AO"], "AO")
    with col_content:
        st.markdown("<div class='tag-minus'>📉 负相位 / Negative (-)</div>", unsafe_allow_html=True)
        signal_card("极涡崩溃 (Vortex Collapse)", "极地高压控制，冷空气南下。", "广泛的<b>冷空气爆发</b>。",
                    "利多 (冷源充足)")

        # [NEW] AO 数据卡片 - 放置在信号卡片下方
        display_current_index_value("AO")

with tab_pna:
    col_img, col_content = st.columns([1, 1.5])
    with col_img: clickable_image_html(IMG_URLS["PNA"], "PNA")
    with col_content:
        st.markdown("<div class='tag-plus'>📈 正相位 / Positive (+)</div>", unsafe_allow_html=True)
        signal_card("西脊东槽 (Ridge-Trough)", "北美西部高压脊隆起。", "建立<b>经向环流</b>输送冷空气。",
                    "利多 (通道打开)")

        # [NEW] PNA 数据卡片 - 放置在信号卡片下方
        display_current_index_value("PNA")

with tab_enso:
    with st.spinner("正在解析 NOAA 最新周报..."):
        enso_data = get_enso_summary(IMG_URLS["LANINA"])
    st.info(f"**Current Status:** {enso_data['status']}")
    if enso_data['body']:
        for s in enso_data['body']: st.markdown(f"- {s}")
    else:
        st.warning("未提取到内容，请检查 PDF。")

# === 7. 决策矩阵 ===
st.markdown("---")
st.subheader("🎯 宏观交易决策矩阵 (Decision Matrix)")
m1, m2, m3 = st.columns(3)

with m1:
    st.success("🔥 **极寒模式 (Strong Buy)**")  # 颜色对调：利多 (Buy) = 绿色 (Success)
    st.markdown("""<div class='decision-content'>
    <span class='decision-label'>信号组合:</span>
    <span class='tag-minus'>NAO (-)</span> + <span class='tag-minus'>AO (-)</span> + <span class='tag-plus'>PNA (+)</span>
    <span class='decision-label'>🥶 天气后果:</span>
    阻寒高压 + 极涡崩溃 + 通道打开。宾州/东北部遭遇持续性暴雪与极寒。
    <span class='decision-label'>💰 操作建议:</span>
    <b>押注上涨:</b> 买入 EQT / NG Futures。
</div>""", unsafe_allow_html=True)

with m2:
    st.error("🟢 **暖冬模式 (Strong Sell)**")  # 颜色对调：利空 (Sell) = 红色 (Error)
    st.markdown("""<div class='decision-content'>
    <span class='decision-label'>信号组合:</span>
    <span class='tag-bear'>NAO (+)</span> + <span class='tag-bear'>AO (+)</span> + <span class='tag-bear'>PNA (-)</span>
    <span class='decision-label'>☀️ 天气后果:</span>
    强劲西风急流 + 东南高压脊。暖湿气流主导美东，不下雪只下雨。
    <span class='decision-label'>💰 操作建议:</span>
    <b>押注下跌:</b> 卖出资产 / 观望。
</div>""", unsafe_allow_html=True)

with m3:
    st.warning("⚖️ **震荡模式 (Neutral)**")
    st.markdown("""<div class='decision-content'>
    <span class='decision-label'>信号组合:</span>
    <span class='tag-neutral'>信号背离 (Mixed)</span>
    <span class='decision-label'>💨 天气后果:</span>
    冷源充足但缺乏阻塞。寒潮来去匆匆，气温忽冷忽热。
    <span class='decision-label'>💰 操作建议:</span>
    <b>波段操作:</b> 不要长期持有。
</div>""", unsafe_allow_html=True)

# === 8. 地学原理 ===
st.markdown("---")
st.subheader("📚 Geophysical Fluid Dynamics & Market Mapping")
with st.expander("📖 点击展开：详细逻辑链条推演 (Logic Chain Analysis)", expanded=True):
    st.markdown("#### 1. North Atlantic Oscillation (NAO)")
    st.markdown(
        "* **Phenomenon:** Significant **Positive Geopotential Height Anomalies** over Greenland.\n"
        "* **Logic Chain:** <span class='tag-minus'>Negative (-)</span> NAO $\\rightarrow$ Traffic Jam for Weather Systems $\\rightarrow$ **Cold Air Stagnation**.",
        unsafe_allow_html=True)
    st.markdown("#### 2. Arctic Oscillation (AO)")
    st.markdown(
        "* **Phenomenon:** Rise in Sea Level Pressure (SLP) over the Arctic Cap.\n"
        "* **Logic Chain:** <span class='tag-minus'>Negative (-)</span> AO $\\rightarrow$ **Meridional Spillover** of Arctic Air $\\rightarrow$ High Heating Demand.",
        unsafe_allow_html=True)
    st.markdown("#### 3. Pacific-North American (PNA)")
    st.markdown(
        "* **Phenomenon:** Quadripole pressure anomaly pattern.\n"
        "* **Logic Chain:** <span class='tag-plus'>Positive (+)</span> PNA $\\rightarrow$ NW-to-SE Flow Vector $\\rightarrow$ **Targeted Delivery** of cold air.",
        unsafe_allow_html=True)
