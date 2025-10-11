# python.py
# Streamlit app: Dashboard trực quan hóa Kết luận Thanh tra (KLTT)
# Chạy: streamlit run python.py
# Yêu cầu: pip install streamlit pandas altair openpyxl plotly

import io
import numpy as np
import pandas as pd
import streamlit as st
import altair as alt
import plotly.express as px

st.set_page_config(
    page_title="Dashboard Kết luận Thanh tra (KLTT)",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==============================
# Helpers
# ==============================

@st.cache_data(show_spinner=False)
def load_excel(uploaded_file: io.BytesIO) -> dict:
    xls = pd.ExcelFile(uploaded_file, engine="openpyxl")
    sheets = {s.lower().strip(): s for s in xls.sheet_names}
    out = {}
    for canon, real in sheets.items():
        df = pd.read_excel(xls, real)
        df.columns = [str(c).strip() for c in df.columns]
        out[canon] = df
    return out

def canonicalize_df(df: pd.DataFrame, mapping: dict) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    new_cols = {}
    existing_lower = {c.lower(): c for c in df.columns}
    for want, aliases in mapping.items():
        for alias in aliases:
            if alias.lower() in existing_lower:
                new_cols[existing_lower[alias.lower()]] = want
                break
    return df.rename(columns=new_cols)

def coalesce_series_with_raw(series: pd.Series, prefix="RAW"):
    s = series.copy()
    s = s.astype(str)
    null_mask = s.isna() | s.str.strip().eq("") | s.str.lower().eq("nan")
    if null_mask.any():
        raw_index = np.cumsum(null_mask).where(null_mask, 0)
        s.loc[null_mask] = [f"{prefix}{i}" for i in raw_index[null_mask].astype(int)]
    return s

def to_number(x):
    if pd.isna(x): return np.nan
    if isinstance(x, (int, float, np.number)): return float(x)
    try: return float(str(x).replace(",", "").replace(" ", ""))
    except:
        digits = "".join(ch for ch in str(x) if (ch.isdigit() or ch=='.' or ch=='-'))
        try: return float(digits)
        except: return np.nan

def safe_date(series: pd.Series):
    try: return pd.to_datetime(series, errors="coerce")
    except Exception: return pd.to_datetime(pd.Series([None]*len(series)), errors="coerce")

def format_vnd(n):
    if pd.isna(n): return "—"
    n = float(n)
    if abs(n) >= 1_000_000_000_000: return f"{n/1_000_000_000_000:.2f} nghìn tỷ ₫"
    if abs(n) >= 1_000_000_000:     return f"{n/1_000_000_000:.2f} tỷ ₫"
    if abs(n) >= 1_000_000:         return f"{n/1_000_000:.2f} triệu ₫"
    return f"{n:,.0f} ₫"

# ==============================
# Theme + CSS
# ==============================

st.markdown("""
<style>
:root { --label-color: #1f6feb; }
[data-testid="stDataFrame"] td, [data-testid="stDataFrame"] th {
  white-space: pre-wrap !important;
  word-break: break-word !important;
}
.info-card { padding: 10px 12px; border: 1px solid #e8e8e8; border-radius: 10px; background: #fff; min-height: 72px; }
.info-card .label { font-size: 12px; color: var(--label-color); font-weight: 700; margin-bottom: 4px; }
.info-card .value { font-size: 15px; line-height: 1.4; white-space: pre-wrap; word-break: break-word; }
.doc-wrap { padding: 10px 14px; border: 1px solid #e6e6e6; border-radius: 12px; background: #fafcff; margin-bottom: 14px; }
.doc-title { font-weight: 700; font-size: 16px; margin-bottom: 8px; }
</style>
""", unsafe_allow_html=True)

def info_card(label, value):
    if value in [None, np.nan, "nan", "None"]:
        value = "—"
    st.markdown(
        f"""
        <div class="info-card">
          <div class="label"><b>{label}</b></div>
          <div class="value">{value}</div>
        </div>
        """, unsafe_allow_html=True
    )

# ==============================
# Column mappings
# ==============================

COL_MAP = {
    "documents": {
        "doc_id": ["Doc_id","doc_id","DocID","Maso"],
        "issue_date": ["Issue_date","Issues_date","issue_date"],
        "title": ["title","Title"],
        "issuing_authority": ["Issuing_authority","issuing_authority"],
        "inspected_entity_name": ["inspected_entity_name","Inspected_entity_name"],
        "sector": ["sector","Sector"],
        "period_start": ["period_start","Period_start"],
        "period_end": ["period_end","Period_end"],
        "signer_name": ["Signer_name","signer_name"],
        "signer_title": ["Signer_title","signer_title"],
    },
    "overalls": {
        "departments_at_hq_count": ["departments_at_hq_count"],
        "transaction_offices_count": ["transaction_offices_count"],
        "staff_total": ["staff_total"],
        "mobilized_capital_vnd": ["mobilized_capital_vnd"],
        "loans_outstanding_vnd": ["loans_outstanding_vnd"],
        "npl_total_vnd": ["npl_total_vnd"],
        "npl_ratio_percent": ["npl_ratio_percent"],
        "sample_total_files": ["sample_total_files"],
        "sample_outstanding_checked_vnd": ["sample_outstanding_checked_vnd"],

        # --- Bổ sung theo yêu cầu ---
        "npl_group3_vnd": ["npl_group3_vnd"],
        "npl_group4_vnd": ["npl_group4_vnd"],
        "npl_group5_vnd": ["npl_group5_vnd"],
        "structure_term_short_vnd": ["structure_term_short_vnd"],
        "structure_term_medium_long_vnd": ["structure_term_medium_long_vnd"],
        "structure_currency_vnd_vnd": ["structure_currency_vnd_vnd"],
        "structure_currency_fx_vnd": ["structure_currency_fx_vnd"],
        "structure_purpose_bds_flexible_vnd": ["structure_purpose_bds_flexible_vnd"],
        "strucuture_purpose_securities_vnd": ["strucuture_purpose_securities_vnd"],
        "structure_purpose_consumption_vnd": ["structure_purpose_consumption_vnd"],
        "structure_purpose_trade_vnd": ["structure_purpose_trade_vnd"],
        "structure_purpose_other_vnd": ["structure_purpose_other_vnd"],
        "strucuture_econ_state_vnd": ["strucuture_econ_state_vnd"],
        "strucuture_econ_nonstate_enterprises_vnd": ["strucuture_econ_nonstate_enterprises_vnd"],
        "strucuture_econ_individuals_households_vnd": ["strucuture_econ_individuals_households_vnd"]
    },
    "findings": {
        "category": ["category"],
        "sub_category": ["sub_category"],
        "description": ["description"],
        "legal_reference": ["legal_reference"],
        "quantified_amount": ["quantified_amount"],
        "impacted_accounts": ["impacted_accounts"],
        "root_cause": ["Root_cause","root_cause"],
        "recommendation": ["recommendation"],
    },
    "actions": {
        "action_type": ["action_type"],
        "legal_reference": ["legal_reference"],
        "action_description": ["action_description"],
        "evidence_of_completion": ["evidence_of_completion"],
    }
}

# ==============================
# Sidebar (Upload + Filters)
# ==============================

with st.sidebar:
    st.header("📤 Tải dữ liệu")
    uploaded = st.file_uploader("Excel (.xlsx): documents, overalls, findings, (actions tuỳ chọn)", type=["xlsx"])
    st.caption("Tên sheet & cột không phân biệt hoa/thường.")

st.title("🛡️ Dashboard Báo Cáo Kết Luận Thanh Tra")

if not uploaded:
    st.info("Vui lòng tải lên file Excel để bắt đầu.")
    st.stop()

data = load_excel(uploaded)

def get_df(sheet_key):
    raw = data.get(sheet_key)
    mapping = COL_MAP.get(sheet_key, {})
    if raw is None: return pd.DataFrame()
    return canonicalize_df(raw.copy(), mapping)

df_docs = get_df("documents")
df_over = get_df("overalls")
df_find = get_df("findings")
df_act  = get_df("actions")

if df_docs.empty or df_over.empty or df_find.empty:
    st.error("Thiếu một trong các sheet bắt buộc: documents, overalls, findings.")
    st.stop()

# Dates
for c in ["issue_date","period_start","period_end"]:
    if c in df_docs.columns:
        df_docs[c] = safe_date(df_docs[c])

# Numeric
for c in COL_MAP["overalls"].keys():
    if c in df_over.columns: df_over[c] = df_over[c].apply(to_number)
for c in ["quantified_amount","impacted_accounts"]:
    if c in df_find.columns: df_find[c] = df_find[c].apply(to_number)

# RAW handling
df_find["legal_reference_filter"] = coalesce_series_with_raw(df_find["legal_reference"], prefix="RAW")
df_find["legal_reference_chart"] = df_find["legal_reference_filter"].apply(lambda x: "RAW" if str(x).startswith("RAW") else x)

# Sidebar filter (findings only)
st.sidebar.header("🔎 Lọc Findings")
all_refs = sorted(df_find["legal_reference_filter"].astype(str).unique().tolist())
selected_refs = st.sidebar.multiselect("Chọn Legal_reference", options=all_refs, default=all_refs)
f_df = df_find[df_find["legal_reference_filter"].astype(str).isin([str(x) for x in selected_refs])].copy()

st.sidebar.markdown("---")
st.sidebar.metric("💸 Tổng tiền ảnh hưởng (lọc)", format_vnd(f_df["quantified_amount"].sum()))
st.sidebar.metric("👥 Tổng hồ sơ ảnh hưởng (lọc)", f"{int(f_df['impacted_accounts'].sum()) if 'impacted_accounts' in f_df.columns and pd.notna(f_df['impacted_accounts'].sum()) else '—'}")

# ==============================
# Tabs
# ==============================

tab_docs, tab_over, tab_find, tab_act = st.tabs(["📝 Documents","📊 Overalls","🚨 Findings","✅ Actions"])

# ---- Documents ----
with tab_docs:
    st.header("Báo Cáo Kết Luận Thanh Tra (Metadata)")
    st.markdown("---")
    for _, row in df_docs.iterrows():
        st.markdown(f"### 📝 {row.get('doc_id','—')}")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            info_card("Đơn vị phát hành", row.get("issuing_authority"))
        with c2:
            info_card("Ngày phát hành", row.get("issue_date"))
        with c3:
            info_card("Người ký", row.get("signer_name"))
        with c4:
            info_card("Chức vụ", row.get("signer_title"))

# ---- Overalls ----
with tab_over:
    st.header("Thông Tin Tổng Quan")
    st.markdown("---")
    over_row = df_over.iloc[-1] if len(df_over) else pd.Series({})

    k1,k2,k3,k4,k5 = st.columns(5)
    with k1:
        st.metric("Tổng nhân sự", f"{int(over_row.get('staff_total', np.nan)) if pd.notna(over_row.get('staff_total', np.nan)) else '—'}")
        st.metric("Mẫu kiểm tra", f"{int(over_row.get('sample_total_files', np.nan)) if pd.notna(over_row.get('sample_total_files', np.nan)) else '—'}")
    with k2:
        st.metric("Phòng nghiệp vụ", f"{int(over_row.get('departments_at_hq_count', np.nan)) if pd.notna(over_row.get('departments_at_hq_count', np.nan)) else '—'}")
        st.metric("Phòng giao dịch", f"{int(over_row.get('transaction_offices_count', np.nan)) if pd.notna(over_row.get('transaction_offices_count', np.nan)) else '—'}")
    with k3:
        st.metric("Nguồn vốn", format_vnd(over_row.get("mobilized_capital_vnd", np.nan)))
    with k4:
        st.metric("Dư nợ", format_vnd(over_row.get("loans_outstanding_vnd", np.nan)))
    with k5:
        st.metric("Nợ xấu", format_vnd(over_row.get("npl_total_vnd", np.nan)))
        st.metric("Tỷ lệ NPL/Dư nợ", f"{over_row.get('npl_ratio_percent', np.nan):.2f}%" if pd.notna(over_row.get('npl_ratio_percent', np.nan)) else "—")

    st.markdown("### 📌 Nợ xấu theo nhóm (nếu có)")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Nợ xấu nhóm 3", format_vnd(over_row.get("npl_group3_vnd", np.nan)))
    with c2:
        st.metric("Nợ xấu nhóm 4", format_vnd(over_row.get("npl_group4_vnd", np.nan)))
    with c3:
        st.metric("Nợ xấu nhóm 5", format_vnd(over_row.get("npl_group5_vnd", np.nan)))

    st.markdown("### 🧭 Cơ cấu theo kỳ hạn")
    t1, t2 = st.columns(2)
    with t1:
        st.metric("Dư nợ ngắn hạn", format_vnd(over_row.get("structure_term_short_vnd", np.nan)))
    with t2:
        st.metric("Dư nợ trung & dài hạn", format_vnd(over_row.get("structure_term_medium_long_vnd", np.nan)))

    st.markdown("### 💱 Cơ cấu theo tiền tệ")
    cur1, cur2 = st.columns(2)
    with cur1:
        st.metric("Dư nợ bằng VND", format_vnd(over_row.get("structure_currency_vnd_vnd", np.nan)))
    with cur2:
        st.metric("Dư nợ quy đổi ngoại tệ", format_vnd(over_row.get("structure_currency_fx_vnd", np.nan)))

    st.markdown("### 🎯 Cơ cấu theo mục đích vay")
    g1, g2, g3 = st.columns(3)
    with g1:
        st.metric("BĐS / linh hoạt", format_vnd(over_row.get("structure_purpose_bds_flexible_vnd", np.nan)))
        st.metric("Chứng khoán", format_vnd(over_row.get("strucuture_purpose_securities_vnd", np.nan)))
    with g2:
        st.metric("Tiêu dùng", format_vnd(over_row.get("structure_purpose_consumption_vnd", np.nan)))
        st.metric("Thương mại", format_vnd(over_row.get("structure_purpose_trade_vnd", np.nan)))
    with g3:
        st.metric("Mục đích khác", format_vnd(over_row.get("structure_purpose_other_vnd", np.nan)))

    st.markdown("### 🧩 Cơ cấu theo thành phần kinh tế")
    e1, e2, e3 = st.columns(3)
    with e1:
        st.metric("DN Nhà nước", format_vnd(over_row.get("strucuture_econ_state_vnd", np.nan)))
    with e2:
        st.metric("DN ngoài QD", format_vnd(over_row.get("strucuture_econ_nonstate_enterprises_vnd", np.nan)))
    with e3:
        st.metric("Cá nhân/Hộ gia đình", format_vnd(over_row.get("strucuture_econ_individuals_households_vnd", np.nan)))

st.caption("© KLTT Dashboard • Streamlit • Altair • Plotly")
