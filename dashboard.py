import streamlit as st
from datetime import datetime
import requests
import io
import re
from pypdf import PdfReader
import pandas as pd
import json
from streamlit_autorefresh import st_autorefresh

# === 1. 页面全局配置 ===
st.set_page_config(
    page_title="Climate–Natural Gas Analytics",
    page_icon="⚛️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# === [配置] 自动刷新 (5分钟) ===
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

    /* [修改] 标签样式：字体变大，内边距增加 */
    .tag-minus {
        background-color: #ffebee; color: #c62828; 
        padding: 4px 12px; border-radius: 6px; font-weight: 700; font-size: 1.1em; /* 变大 */
        border: 1px solid #ffcdd2; display: inline-block; margin: 4px 0;
    }
    .tag-plus {
        background-color: #e8f5e9; color: #2e7d32; 
        padding: 4px 12px; border-radius: 6px; font-weight: 700; font-size: 1.1em; /* 变大 */
        border: 1px solid #c8e6c9; display: inline-block; margin: 4px 0;
    }
    .tag-neutral {
        background-color: #f5f5f5; color: #616161; 
        padding: 4px 12px; border-radius: 6px; font-weight: 700; font-size: 1.1em; /* 变大 */
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


# === 辅助函数 ===
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


# === HDD 数据抓取函数 (NOAA) ===
@st.cache(ttl=3600, suppress_st_warning=True)
def get_gas_hdd():
    url = "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/cdus/degree_days/wsahddy.txt"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200: return None
        lines = response.text.split('\n')
        data_bag = {}
        in_gas_section = False
        targets = {
            "NEW ENGLAND": "New England",
            "MIDDLE ATLANTIC": "Middle Atlantic",
            "E N CENTRAL": "Midwest",
            "UNITED STATES": "US Total"
        }
        for line in lines:
            if "GAS HOME HEATING CUSTOMER WEIGHTED" in line:
                in_gas_section = True
                continue
            if in_gas_section:
                for keyword, clean_name in targets.items():
                    if keyword in line:
                        numbers = re.findall(r'-?\d+', line)
                        if len(numbers) >= 3:
                            data_bag[clean_name] = {
                                "actual": int(numbers[0]),
                                "dev_normal": int(numbers[1]),
                                "dev_last_year": int(numbers[2])
                            }
                if len(data_bag) == 4: break
        return data_bag
    except Exception as e:
        return None


# === ENSO 报告解析 ===
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


# === EIA 数据解析 ===
@st.cache(ttl=3600, suppress_st_warning=True)
def load_eia_total():
    url = "https://ir.eia.gov/ngs/wngsr.json"
    try:
        resp = requests.get(url, timeout=15)
        raw = resp.content.decode("utf-8-sig")
        obj = json.loads(raw)
        current_week = obj.get("current_week")
        week_ago = obj.get("week_ago")
        year_ago = obj.get("year_ago")

        def fmt_date(d):
            try:
                return datetime.strptime(d, "%Y-%m-%d").strftime("%m/%d/%y")
            except:
                return d

        labels = [fmt_date(current_week), fmt_date(week_ago), "Net change (Bcf)",
                  f"Year ago {fmt_date(year_ago)} (Bcf)", "Year-ago % change",
                  "5-yr avg (Bcf)", "5-yr % change"]

        def extract_region(prefix, display_name):
            target = next((s for s in obj.get("series", []) if str(s.get("name", "")).lower().startswith(prefix)), None)
            if not target: return None
            data_map = {d[0]: d[1] for d in target.get("data", [])}
            calc = target.get("calculated", {})
            return {
                "Region": display_name,
                labels[0]: data_map.get(current_week),
                labels[1]: data_map.get(week_ago),
                labels[2]: calc.get("net_change"),
                labels[3]: data_map.get(year_ago),
                labels[4]: calc.get("pct-change_yrago"),
                labels[5]: calc.get("5yr-avg"),
                labels[6]: calc.get("pct-chg_5yr-avg"),
            }

        rows = []
        r1 = extract_region("total lower 48", "Total")
        if r1: rows.append(r1)
        r2 = extract_region("east", "East")
        if r2: rows.append(r2)
        if not rows: return None
        df = pd.DataFrame(rows).set_index("Region")
        for col in df.columns: df[col] = pd.to_numeric(df[col], errors="coerce")
        return df
    except:
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


            # [修改] 强制所有单元格字体加粗
            def highlight_style(df):
                # 默认所有单元格加上 font-weight: bold
                styles = pd.DataFrame('font-weight: bold;', index=df.index, columns=df.columns)

                for idx in df.index:
                    if idx in highlight_rows:
                        for col in df.columns:
                            val = df.loc[idx, col]
                            # 在 font-weight: bold 基础上追加背景色和颜色
                            base = 'font-weight: bold; background-color: #fff3cd;'
                            if val < 0:
                                styles.loc[idx, col] = base + 'color: #c62828;'
                            elif val > 0:
                                styles.loc[idx, col] = base + 'color: #2e7d32;'
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

# === 6. 核心气象板块 (4 Tabs) ===
st.subheader("📡 大气遥相关机制 (Atmospheric Teleconnections)")
st.caption("注：图表展示 GEFS 集合预报发散度。红线 (Mean) 代表主流趋势。")

tab_nao, tab_ao, tab_pna, tab_enso = st.tabs([
    "1. 北大西洋涛动 (NAO)", "2. 北极涛动 (AO)", "3. 太平洋-北美模式 (PNA)", "🌊 NOAA ENSO 周报"
])

with tab_nao:
    c1, c2 = st.columns([1, 1.5])
    with c1: clickable_image_html(IMG_URLS["NAO"], "NAO")
    with c2:
        st.markdown("<div class='tag-minus'>📉 负相位 / Negative (-)</div>", unsafe_allow_html=True)
        signal_card("阻塞效应 (Blocking)", "西风急流弯曲，格陵兰高压形成。", "冷气团在美东<b>停滞不前</b>。",
                    "极强利多 (寒潮持续)")

with tab_ao:
    c1, c2 = st.columns([1, 1.5])
    with c1: clickable_image_html(IMG_URLS["AO"], "AO")
    with c2:
        st.markdown("<div class='tag-minus'>📉 负相位 / Negative (-)</div>", unsafe_allow_html=True)
        signal_card("极涡崩溃 (Vortex Collapse)", "极地高压控制，冷空气南下。", "广泛的<b>冷空气爆发</b>。",
                    "利多 (冷源充足)")

with tab_pna:
    c1, c2 = st.columns([1, 1.5])
    with c1: clickable_image_html(IMG_URLS["PNA"], "PNA")
    with c2:
        st.markdown("<div class='tag-plus'>📈 正相位 / Positive (+)</div>", unsafe_allow_html=True)
        signal_card("西脊东槽 (Ridge-Trough)", "北美西部高压脊隆起。", "建立<b>经向环流</b>输送冷空气。",
                    "利多 (通道打开)")

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
    st.error("🔥 **极寒模式 (Strong Buy)**")
    st.markdown("""<div class='decision-content'>
    <span class='decision-label'>信号组合:</span>
    <span class='tag-minus'>NAO (-)</span> + <span class='tag-minus'>AO (-)</span> + <span class='tag-plus'>PNA (+)</span>
    <span class='decision-label'>🥶 天气后果:</span>
    阻寒高压 + 极涡崩溃 + 通道打开。宾州/东北部遭遇持续性暴雪与极寒。
    <span class='decision-label'>💰 操作建议:</span>
    <b>押注上涨:</b> 买入 EQT / NG Futures。
</div>""", unsafe_allow_html=True)

with m2:
    st.success("🟢 **暖冬模式 (Strong Sell)**")
    st.markdown("""<div class='decision-content'>
    <span class='decision-label'>信号组合:</span>
    <span class='tag-plus'>NAO (+)</span> + <span class='tag-plus'>AO (+)</span> + <span class='tag-minus'>PNA (-)</span>
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
