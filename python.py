
# python.py
# Streamlit app: Dashboard trực quan hóa Kết luận Thanh tra (KLTT)
# Chạy: streamlit run python.py
# Yêu cầu: pip install streamlit pandas altair openpyxl plotly

import io
from io import BytesIO
import numpy as np
import pandas as pd
import streamlit as st
import altair as alt
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(
    page_title="Dashboard Kết luận Thanh tra (KLTT)",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==============================
# 1) HELPERS & UTILITIES
# ==============================

@st.cache_data(show_spinner=False)
def load_excel(uploaded_file: io.BytesIO) -> dict:
    """Đọc tất cả sheet, chuẩn hóa tên sheet (lower, strip), strip tên cột."""
    xls = pd.ExcelFile(uploaded_file, engine="openpyxl")
    sheets = {s.lower().strip(): s for s in xls.sheet_names}
    dfs = {}
    for canon, real in sheets.items():
        df = pd.read_excel(xls, real)
        df.columns = [str(c).strip() for c in df.columns]
        dfs[canon] = df
    return dfs

def canonicalize_df(df: pd.DataFrame, mapping: dict) -> pd.DataFrame:
    """Ánh xạ tên cột (case-insensitive) sang tên chuẩn đã định nghĩa trong mapping."""
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
    """Thay thế ô trống/NaN thành RAW1, RAW2... để lọc chi tiết."""
    s = series.copy()
    s = s.astype(str)
    null_mask = s.isna() | s.str.strip().eq("") | s.str.lower().eq("nan")
    if null_mask.any():
        raw_index = np.cumsum(null_mask).where(null_mask, 0)
        s.loc[null_mask] = [f"{prefix}{i}" for i in raw_index[null_mask].astype(int)]
    return s

def to_number(x):
    if pd.isna(x):
        return np.nan
    if isinstance(x, (int, float, np.number)):
        return float(x)
    try:
        return float(str(x).replace(",", "").replace(" ", ""))
    except:
        digits = "".join(ch for ch in str(x) if (ch.isdigit() or ch=='.' or ch=='-'))
        try:
            return float(digits)
        except:
            return np.nan

def safe_date(series: pd.Series):
    try:
        return pd.to_datetime(series, errors="coerce")
    except Exception:
        return pd.to_datetime(pd.Series([None]*len(series)), errors="coerce")

def format_vnd(n):
    if pd.isna(n):
        return "—"
    n = float(n)
    if abs(n) >= 1_000_000_000_000:
        return f"{n/1_000_000_000_000:.2f} nghìn tỷ ₫"
    if abs(n) >= 1_000_000_000:
        return f"{n/1_000_000_000:.2f} tỷ ₫"
    if abs(n) >= 1_000_000:
        return f"{n/1_000_000:.2f} triệu ₫"
    return f"{n:,.0f} ₫"

# CSS: wrap text & style
st.markdown("""
<style>
[data-testid="stDataFrame"] td, [data-testid="stDataFrame"] th {
  white-space: pre-wrap !important;
  word-break: break-word !important;
}
.info-card { padding: 10px 12px; border: 1px solid #e8e8e8; border-radius: 10px; background: #fff; min-height: 72px; }
.info-card .label { font-size: 12px; color: #666; margin-bottom: 2px; }
.info-card .value { font-size: 15px; line-height: 1.35; white-space: pre-wrap; word-break: break-word; }
</style>
""", unsafe_allow_html=True)

def info_card(label, value):
    st.markdown(
        f"""
        <div class="info-card">
          <div class="label">{label}</div>
          <div class="value">{value if value not in [None, np.nan, 'nan'] else '—'}</div>
        </div>
        """, unsafe_allow_html=True
    )

# ==============================
# 2) COLUMN MAPPINGS
# ==============================
COL_MAP = {
    "documents": {
        "doc_id": ["Doc_id","doc_id","DocID"],
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
# 3) SIDEBAR (Upload & Filters)
# ==============================
with st.sidebar:
    st.header("📤 Tải dữ liệu")
    uploaded = st.file_uploader("Excel (.xlsx): documents, overalls, findings, (actions tuỳ chọn)", type=["xlsx"])
    st.caption("App tự nhận alias tên cột, không phân biệt hoa/thường.")

st.title("🛡️ Dashboard Báo Cáo Kết Luận Thanh Tra")

if not uploaded:
    st.info("Vui lòng tải lên file Excel để bắt đầu.")
    st.stop()

data = load_excel(uploaded)

def get_df(sheet_key):
    raw = data.get(sheet_key)
    mapping = COL_MAP.get(sheet_key, {})
    if raw is None:
        return pd.DataFrame()
    return canonicalize_df(raw.copy(), mapping)

df_docs = get_df("documents")
df_over = get_df("overalls")
df_find = get_df("findings")
df_act  = get_df("actions")

if df_docs.empty or df_over.empty or df_find.empty:
    st.error("Thiếu một trong các sheet bắt buộc: documents, overalls, findings.")
    st.stop()

for c in ["issue_date","period_start","period_end"]:
    if c in df_docs.columns:
        df_docs[c] = safe_date(df_docs[c])

for c in COL_MAP["overalls"].keys():
    if c in df_over.columns:
        df_over[c] = df_over[c].apply(to_number)

for c in ["quantified_amount","impacted_accounts"]:
    if c in df_find.columns:
        df_find[c] = df_find[c].apply(to_number)

df_find["legal_reference_filter"] = coalesce_series_with_raw(df_find["legal_reference"], prefix="RAW")
df_find["legal_reference_chart"] = df_find["legal_reference_filter"].apply(lambda x: "RAW" if str(x).startswith("RAW") else x)

st.sidebar.header("🔎 Lọc Findings")
all_refs = sorted(df_find["legal_reference_filter"].astype(str).unique().tolist())
selected_refs = st.sidebar.multiselect("Chọn Legal_reference", options=all_refs, default=all_refs)
f_df = df_find[df_find["legal_reference_filter"].astype(str).isin([str(x) for x in selected_refs])].copy()

st.sidebar.markdown("---")
st.sidebar.metric("💸 Tổng tiền ảnh hưởng (lọc)", format_vnd(f_df["quantified_amount"].sum()))
st.sidebar.metric("👥 Tổng hồ sơ ảnh hưởng (lọc)", f"{int(f_df['impacted_accounts'].sum()) if 'impacted_accounts' in f_df.columns and pd.notna(f_df['impacted_accounts'].sum()) else '—'}")

# ==============================
# 4) TABS
# ==============================
tab_docs, tab_over, tab_find, tab_act = st.tabs(["📝 Documents","📊 Overalls","🚨 Findings","✅ Actions"])

with tab_docs:
    st.header("Báo Cáo Kết Luận Thanh Tra (Metadata)")
    st.markdown("---")
    # Chọn theo doc_id hoặc title
    select_col = "doc_id" if "doc_id" in df_docs.columns else ("title" if "title" in df_docs.columns else None)
    options = df_docs[select_col].astype(str).tolist() if select_col else []
    chosen = st.selectbox("Chọn KLTT", options, index=0 if options else None)
    row = df_docs[df_docs[select_col].astype(str)==str(chosen)].iloc[0] if options else None

    c1,c2,c3,c4 = st.columns(4)
    if row is not None:
        with c1:
            info_card("Mã số KLTT (Doc_id)", str(row.get("doc_id","—")))
            info_card("Đơn vị phát hành", str(row.get("issuing_authority","—")))
            info_card("Người kiểm soát", str(row.get("signer_name","—")))
        with c2:
            d = row.get("issue_date", pd.NaT)
            info_card("Ngày phát hành", d.strftime("%d/%m/%Y") if pd.notna(d) else "—")
            info_card("Đơn vị được kiểm tra", str(row.get("inspected_entity_name","—")))
            info_card("Chức vụ", str(row.get("signer_title","—")))
        with c3:
            info_card("Title", str(row.get("title","—")))
            info_card("Lĩnh vực", str(row.get("sector","—")))
        with c4:
            ps = row.get("period_start", pd.NaT); pe = row.get("period_end", pd.NaT)
            info_card("Thời gian bắt đầu", ps.strftime("%d/%m/%Y") if pd.notna(ps) else "—")
            info_card("Thời gian kết thúc", pe.strftime("%d/%m/%Y") if pd.notna(pe) else "—")

with tab_over:
    st.header("Thông Tin Tổng Quan")
    st.markdown("---")
    over_row = df_over.iloc[-1] if len(df_over) else pd.Series({})

    k1,k2,k3,k4,k5 = st.columns(5)
    with k1:
        st.metric("Tổng nhân sự", f"{int(over_row.get('staff_total', np.nan)) if pd.notna(over_row.get('staff_total', np.nan)) else '—'}")
        st.metric("Mẫu kiểm tra", f"{int(over_row.get('sample_total_files', np.nan)) if pd.notna(over_row.get('sample_total_files', np.nan)) else '—'}")
    with k2:
        st.metric("Phòng nghiệp vụ (HQ)", f"{int(over_row.get('departments_at_hq_count', np.nan)) if pd.notna(over_row.get('departments_at_hq_count', np.nan)) else '—'}")
        st.metric("Phòng giao dịch", f"{int(over_row.get('transaction_offices_count', np.nan)) if pd.notna(over_row.get('transaction_offices_count', np.nan)) else '—'}")
    with k3:
        st.metric("Nguồn vốn gần nhất", format_vnd(over_row.get("mobilized_capital_vnd", np.nan)))
    with k4:
        st.metric("Dư nợ gần nhất", format_vnd(over_row.get("loans_outstanding_vnd", np.nan)))
    with k5:
        st.metric("Nợ xấu gần nhất", format_vnd(over_row.get("npl_total_vnd", np.nan)))
        st.metric("Tỷ lệ NPL / Dư nợ", f"{over_row.get('npl_ratio_percent', np.nan):.2f}%" if pd.notna(over_row.get('npl_ratio_percent', np.nan)) else "—")
        st.metric("Tổng dư nợ đã kiểm tra", format_vnd(over_row.get("sample_outstanding_checked_vnd", np.nan)))

with tab_find:
    st.header("Phát hiện & Nguyên nhân (Findings)")
    st.subheader(f"Đang lọc theo: {len(selected_refs)}/{len(all_refs)} legal_reference")
    st.markdown("---")
    if f_df.empty:
        st.warning("Không có dữ liệu theo bộ lọc hiện tại.")
    else:
        col1,col2 = st.columns(2)
        with col1:
            cat_count = f_df["category"].value_counts().reset_index()
            cat_count.columns = ["Category","Count"]
            fig1 = px.bar(cat_count, x="Category", y="Count", text="Count", color="Category",
                          title="Số lần xuất hiện theo Category")
            fig1.update_traces(textposition="outside")
            fig1.update_layout(height=380, xaxis_title="", yaxis_title="Số lần")
            st.plotly_chart(fig1, use_container_width=True)
        with col2:
            cat_sub = f_df.groupby(["category","sub_category"]).size().reset_index(name="Count")
            fig2 = px.bar(cat_sub, x="category", y="Count", color="sub_category",
                          title="Category × Sub_category (số lần)", barmode="group",
                          labels={"category":"Category","sub_category":"Sub_category","Count":"Số lần"})
            fig2.update_layout(height=380)
            st.plotly_chart(fig2, use_container_width=True)

        st.markdown("---")
        st.subheader("Line chart: Legal_reference (gộp RAWx→RAW)")
        legal_count = f_df["legal_reference_chart"].value_counts().reset_index()
        legal_count.columns = ["Legal_reference","Count"]
        fig3 = px.line(legal_count, x="Legal_reference", y="Count", markers=True,
                       title="Số lần xuất hiện theo Legal_reference (gộp RAWx→RAW)")
        st.plotly_chart(fig3, use_container_width=True)
        st.info("RAW = luật/quy định không được nhắc rõ; ô trống đã gán RAW1, RAW2… và gộp thành RAW trong biểu đồ.")

        st.markdown("---")
        st.subheader("Tần suất từng Legal_reference (không gộp phụ lục)")
        freq_tbl = f_df["legal_reference_filter"].value_counts().reset_index()
        freq_tbl.columns = ["Legal_reference","Số lần"]
        st.dataframe(freq_tbl, use_container_width=True, height=320)

        st.markdown("---")
        st.subheader("Chi tiết theo Sub_category")
        order_sub = f_df["sub_category"].value_counts().index.tolist()
        for sub in order_sub:
            st.markdown(f"#### 🔹 {sub}")
            cols_show = [c for c in ["description","legal_reference","legal_reference_filter","quantified_amount","impacted_accounts","root_cause","recommendation"] if c in f_df.columns]
            sub_df = f_df[f_df["sub_category"]==sub][cols_show].copy()
            if "quantified_amount" in sub_df.columns:
                sub_df["quantified_amount"] = sub_df["quantified_amount"].apply(format_vnd)
            if "impacted_accounts" in sub_df.columns:
                sub_df["impacted_accounts"] = sub_df["impacted_accounts"].apply(lambda x: f"{int(x):,}" if pd.notna(x) else "—")
            rename = {
                "description":"Mô tả",
                "legal_reference":"Điều luật (gốc)",
                "legal_reference_filter":"Điều luật (lọc RAWx)",
                "quantified_amount":"Số tiền ảnh hưởng",
                "impacted_accounts":"Số KH/Hồ sơ",
                "root_cause":"Nguyên nhân gốc",
                "recommendation":"Khuyến nghị"
            }
            st.dataframe(sub_df.rename(columns=rename), use_container_width=True)

        st.markdown("---")
        st.subheader("Tổng hợp Root_cause & Recommendation theo Legal_reference")
        group_cols = ["legal_reference"]
        if "root_cause" in f_df.columns: group_cols.append("root_cause")
        if "recommendation" in f_df.columns: group_cols.append("recommendation")
        agg = {"description":"count"}
        if "quantified_amount" in f_df.columns: agg["quantified_amount"]="sum"
        if "impacted_accounts" in f_df.columns: agg["impacted_accounts"]="sum"
        root_tbl = f_df.groupby(group_cols, dropna=False).agg(agg).reset_index().rename(columns={"description":"Số vụ"})
        if "quantified_amount" in root_tbl.columns:
            root_tbl["Tổng tiền ảnh hưởng"] = root_tbl["quantified_amount"].apply(format_vnd)
            root_tbl = root_tbl.drop(columns=["quantified_amount"])
        if "impacted_accounts" in root_tbl.columns:
            root_tbl["Tổng hồ sơ ảnh hưởng"] = root_tbl["impacted_accounts"].apply(lambda x: f"{int(x):,}" if pd.notna(x) else "—")
            root_tbl = root_tbl.drop(columns=["impacted_accounts"])
        show_cols = [c for c in ["legal_reference","root_cause","recommendation","Số vụ","Tổng hồ sơ ảnh hưởng","Tổng tiền ảnh hưởng"] if c in root_tbl.columns]
        st.dataframe(root_tbl[show_cols], use_container_width=True)

with tab_act:
    st.header("Biện pháp khắc phục (Actions)")
    st.markdown("---")
    if df_act is None or df_act.empty:
        st.info("Không có sheet actions hoặc thiếu cột. Cần: action_type, legal_reference, action_description, evidence_of_completion.")
    else:
        df_act["legal_reference_filter"] = coalesce_series_with_raw(df_act["legal_reference"], prefix="RAW")
        a_df = df_act[df_act["legal_reference_filter"].astype(str).isin([str(x) for x in selected_refs])].copy()
        if a_df.empty:
            st.warning("Không có hành động phù hợp với bộ lọc legal_reference hiện tại.")
        else:
            if "action_type" in a_df.columns:
                act_count = a_df["action_type"].value_counts().reset_index()
                act_count.columns = ["Action_type","Count"]
                fig = px.pie(act_count, values="Count", names="Action_type", title="Phân loại tính chất biện pháp", hole=.35)
                fig.update_traces(textinfo="percent+label")
                st.plotly_chart(fig, use_container_width=True)
            st.markdown("---")
            cols = [c for c in ["legal_reference_filter","action_type","action_description","evidence_of_completion"] if c in a_df.columns]
            rename = {
                "legal_reference_filter":"Luật lệ (lọc RAWx)",
                "action_type":"Tính chất biện pháp",
                "action_description":"Nội dung công việc phải làm",
                "evidence_of_completion":"Công việc chi tiết / Minh chứng"
            }
            st.dataframe(a_df[cols].rename(columns=rename), use_container_width=True, height=420)

st.caption("© KLTT Dashboard • Streamlit • Altair • Plotly")
