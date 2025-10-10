
# python.py
# Streamlit app: Dashboard trực quan hóa kết luận thanh tra (KLTT)
# Chạy với: streamlit run python.py
# Yêu cầu: pip install streamlit pandas altair openpyxl plotly

import io
import numpy as np
import pandas as pd
import streamlit as st
import altair as alt
import plotly.express as px

st.set_page_config(
    page_title="KLTT Dashboard",
    page_icon="📑",
    layout="wide"
)

# -----------------------------
# Helpers
# -----------------------------

@st.cache_data(show_spinner=False)
def load_excel(uploaded_file: io.BytesIO) -> dict:
    # Read all sheets; normalize sheet names
    xls = pd.ExcelFile(uploaded_file, engine="openpyxl")
    sheets = {s.lower().strip(): s for s in xls.sheet_names}
    dfs = {}
    for canon, real in sheets.items():
        df = pd.read_excel(xls, real)
        # Normalize columns: strip (giữ nguyên hoa-thường vì đã map theo tên chuẩn)
        df.columns = [str(c).strip() for c in df.columns]
        dfs[canon] = df
    return dfs

def coalesce_series_with_raw(series: pd.Series, prefix="RAW"):
    """
    Thay thế các giá trị rỗng/NaN bằng RAW1, RAW2... ổn định theo thứ tự xuất hiện.
    Trả về (series_mapped, mapping_dict)
    """
    s = series.copy()
    null_mask = s.isna() | (s.astype(str).str.strip().eq("")) | (s.astype(str).str.lower().eq("nan"))
    raw_index = np.cumsum(null_mask).where(null_mask, 0)
    s.loc[null_mask] = [f"{prefix}{i}" for i in raw_index[null_mask].astype(int)]
    mapping = {}
    raw_counter = 0
    for was_null in null_mask:
        if was_null:
            raw_counter += 1
            mapping[f"{prefix}{raw_counter}"] = None
    return s, mapping

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

def number_format(n, suffix=""):
    if pd.isna(n):
        return "—"
    absn = abs(n)
    if absn >= 1_000_000_000_000:
        return f"{n/1_000_000_000_000:.2f} nghìn tỷ{suffix}"
    if absn >= 1_000_000_000:
        return f"{n/1_000_000_000:.2f} tỷ{suffix}"
    if absn >= 1_000_000:
        return f"{n/1_000_000:.2f} triệu{suffix}"
    if absn >= 1_000:
        return f"{n/1_000:.2f} nghìn{suffix}"
    try:
        return f"{float(n):,.0f}{suffix}"
    except:
        return str(n)

# -----------------------------
# Sidebar / Upload
# -----------------------------

with st.sidebar:
    st.header("📤 Tải file Excel tổng hợp")
    uploaded = st.file_uploader(
        "Chọn file Excel (.xlsx) chứa các sheet: documents, overalls, findings",
        type=["xlsx"],
        accept_multiple_files=False,
        help="Tên sheet không phân biệt hoa/thường; app sẽ tự nhận dạng theo 'documents', 'overalls', 'findings'."
    )
    st.markdown("---")
    st.caption("💡 Gợi ý cấu trúc cột:\n\n"
               "**documents**: doc_id, Doc_code, Issues_date, title, Issuing_authority, "
               "inspected_entity_name, sector, period_start, period_end, Signer_name, Signer_title\n\n"
               "**overalls**: departments_at_hq_count, transaction_offices_count, staff_total, "
               "mobilized_capital_vnd, loans_outstanding_vnd, npl_total_vnd, npl_ratio_percent, "
               "sample_total_files, sample_outstanding_checked_vnd\n\n"
               "**findings**: category, sub_category, description, legal_reference, quantified_amount, impacted_accounts, Root_cause")

st.title("📑 Dashboard Kết luận Thanh tra (KLTT)")

if not uploaded:
    st.info("Vui lòng tải lên file Excel để bắt đầu.")
    st.stop()

data = load_excel(uploaded)

# Resolve sheet names flexibly
def get_sheet(name_candidates, data_dict):
    for cand in name_candidates:
        if cand in data_dict:
            return data_dict[cand]
    return None

df_docs = get_sheet(["documents", "document", "docs"], data)
df_over = get_sheet(["overalls", "overall"], data)
df_find = get_sheet(["findings", "finding"], data)

if df_docs is None or df_over is None or df_find is None:
    st.error("Không tìm thấy đủ 3 sheet 'documents', 'overalls', 'findings'. Vui lòng kiểm tra lại.")
    st.stop()

# -----------------------------
# Section 1: Documents
# -----------------------------

st.subheader("📄 Thông tin văn bản kết luận (documents)")

doc_cols_map = {
    "doc_id": "doc_id",
    "Doc_code": "Doc_code",
    "Issues_date": "Issues_date",
    "title": "title",
    "Issuing_authority": "Issuing_authority",
    "inspected_entity_name": "inspected_entity_name",
    "sector": "sector",
    "period_start": "period_start",
    "period_end": "period_end",
    "Signer_name": "Signer_name",
    "Signer_title": "Signer_title",
}

def canonicalize(df, mapping):
    # Match ignoring case
    new = {}
    existing_lower = {c.lower(): c for c in df.columns}
    for want, alias in mapping.items():
        if want.lower() in existing_lower:
            new[existing_lower[want.lower()]] = alias
    return df.rename(columns=new)

df_docs = canonicalize(df_docs, doc_cols_map)

# Parse date-like columns
for c in ["Issues_date", "period_start", "period_end"]:
    if c in df_docs.columns:
        df_docs[c] = safe_date(df_docs[c])

# Select a document to show
id_col = "doc_id" if "doc_id" in df_docs.columns else None
default_title_col = "title" if "title" in df_docs.columns else None
selector_label = "Chọn kết luận thanh tra"

if id_col:
    options = df_docs[id_col].astype(str).tolist()
    doc_row = df_docs[df_docs[id_col].astype(str) == str(st.selectbox(selector_label, options, index=0 if options else None))].iloc[0] if options else None
else:
    options = df_docs[default_title_col].astype(str).tolist() if default_title_col else []
    doc_row = df_docs[df_docs[default_title_col].astype(str) == str(st.selectbox(selector_label, options, index=0 if options else None))].iloc[0] if options else None

if doc_row is not None:
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("📌 Mã KLTT", str(doc_row.get("Doc_code", "—")))
        st.metric("🏛️ Đơn vị phát hành", str(doc_row.get("Issuing_authority", "—")))
        st.metric("🧑‍💼 Người kiểm soát", str(doc_row.get("Signer_name", "—")))
    with col2:
        st.metric("🗓️ Ngày phát hành", doc_row.get("Issues_date", pd.NaT).strftime("%d/%m/%Y") if pd.notna(doc_row.get("Issues_date", pd.NaT)) else "—")
        st.metric("🏢 Đơn vị được kiểm tra", str(doc_row.get("inspected_entity_name", "—")))
        st.metric("🎖️ Chức vụ", str(doc_row.get("Signer_title", "—")))
    with col3:
        st.metric("📚 Title", str(doc_row.get("title", "—")))
        st.metric("🧭 Lĩnh vực", str(doc_row.get("sector", "—")))
    with col4:
        st.metric("⏱️ Bắt đầu", doc_row.get("period_start", pd.NaT).strftime("%d/%m/%Y") if pd.notna(doc_row.get("period_start", pd.NaT)) else "—")
        st.metric("⏱️ Kết thúc", doc_row.get("period_end", pd.NaT).strftime("%d/%m/%Y") if pd.notna(doc_row.get("period_end", pd.NaT)) else "—")

st.markdown("---")

# -----------------------------
# Section 2: Overalls
# -----------------------------

st.subheader("🏁 Tổng quan hoạt động (overalls)")

over_map = {
    "departments_at_hq_count": "departments_at_hq_count",
    "transaction_offices_count": "transaction_offices_count",
    "staff_total": "staff_total",
    "mobilized_capital_vnd": "mobilized_capital_vnd",
    "loans_outstanding_vnd": "loans_outstanding_vnd",
    "npl_total_vnd": "npl_total_vnd",
    "npl_ratio_percent": "npl_ratio_percent",
    "sample_total_files": "sample_total_files",
    "sample_outstanding_checked_vnd": "sample_outstanding_checked_vnd",
}
df_over = canonicalize(df_over, over_map)

# Convert numeric columns
num_cols = list(over_map.values())
for c in num_cols:
    if c in df_over.columns:
        df_over[c] = df_over[c].apply(to_number)

# Aggregate if many rows present: take last non-null per column
if len(df_over) > 1:
    summary = {}
    for c in df_over.columns:
        series = df_over[c].dropna()
        summary[c] = series.iloc[-1] if not series.empty else np.nan
    over_row = pd.Series(summary)
else:
    over_row = df_over.iloc[0]

k1, k2, k3, k4, k5, k6 = st.columns(6)
with k1:
    st.metric("Số phòng nghiệp vụ", f"{int(over_row.get('departments_at_hq_count', np.nan)) if pd.notna(over_row.get('departments_at_hq_count', np.nan)) else '—'}")
with k2:
    st.metric("Phòng giao dịch", f"{int(over_row.get('transaction_offices_count', np.nan)) if pd.notna(over_row.get('transaction_offices_count', np.nan)) else '—'}")
with k3:
    st.metric("Tổng nhân sự", f"{int(over_row.get('staff_total', np.nan)) if pd.notna(over_row.get('staff_total', np.nan)) else '—'}")
with k4:
    st.metric("Nguồn vốn gần nhất", number_format(over_row.get("mobilized_capital_vnd", np.nan), " ₫"))
with k5:
    st.metric("Dư nợ gần nhất", number_format(over_row.get("loans_outstanding_vnd", np.nan), " ₫"))
with k6:
    st.metric("Nợ xấu gần nhất", number_format(over_row.get("npl_total_vnd", np.nan), " ₫"))

k7, k8, k9 = st.columns(3)
with k7:
    st.metric("Tỷ lệ NPL / Dư nợ", f"{over_row.get('npl_ratio_percent', np.nan):.2f} %" if pd.notna(over_row.get('npl_ratio_percent', np.nan)) else "—")
with k8:
    st.metric("Số lượng mẫu kiểm tra", f"{int(over_row.get('sample_total_files', np.nan)) if pd.notna(over_row.get('sample_total_files', np.nan)) else '—'}")
with k9:
    st.metric("Tổng dư nợ đã kiểm tra", number_format(over_row.get("sample_outstanding_checked_vnd", np.nan), " ₫"))

st.markdown("---")

# -----------------------------
# Section 3: Findings (TRỌNG TÂM)
# -----------------------------

st.subheader("🔎 Phát hiện & vi phạm (findings)")

find_map = {
    "category": "category",
    "sub_category": "sub_category",
    "description": "description",
    "legal_reference": "legal_reference",
    "quantified_amount": "quantified_amount",
    "impacted_accounts": "impacted_accounts",
    "Root_cause": "Root_cause",
}
df_find = canonicalize(df_find, find_map)

required = ["category", "sub_category", "description", "legal_reference"]
missing = [c for c in required if c not in df_find.columns]
if missing:
    st.error(f"Thiếu cột bắt buộc trong 'findings': {', '.join(missing)}")
    st.stop()

# Clean numeric
for c in ["quantified_amount", "impacted_accounts"]:
    if c in df_find.columns:
        df_find[c] = df_find[c].apply(to_number)

# Coalesce empty legal_reference to RAW1, RAW2...
df_find["legal_reference"], raw_map = coalesce_series_with_raw(df_find["legal_reference"], prefix="RAW")

# ===== Charts: Category frequency =====
left, right = st.columns([1,1])

with left:
    st.markdown("**📊 Tần suất xuất hiện theo _category_**")
    cat_count = df_find.groupby("category", dropna=False).size().reset_index(name="count")
    chart1 = alt.Chart(cat_count).mark_bar().encode(
        x=alt.X("count:Q", title="Số lần xuất hiện"),
        y=alt.Y("category:N", sort='-x', title="Category"),
        tooltip=["category", "count"]
    ).properties(height=350)
    st.altair_chart(chart1, use_container_width=True)

with right:
    st.markdown("**🍩 Cơ cấu _sub_category_ (Donut)**")
    sub_count = df_find.groupby("sub_category", dropna=False).size().reset_index(name="count")
    if len(sub_count) > 0:
        fig = px.pie(sub_count, names="sub_category", values="count", hole=0.45)
        fig.update_traces(textposition="inside", textinfo="percent+label")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Không có dữ liệu sub_category.")

st.markdown("---")

# ===== Filters by Legal Reference =====
st.markdown("### 🧯 Bộ lọc theo **Legal_reference** (tự động gán RAW1, RAW2 cho ô trống)")

all_refs = sorted(df_find["legal_reference"].astype(str).unique().tolist())
selected_refs = st.multiselect(
    "Chọn điều luật/reference cần lọc",
    options=all_refs,
    default=all_refs,
    help="Các ô trống đã được thay bằng RAW1, RAW2... để tiện lọc."
)

f_df = df_find[df_find["legal_reference"].astype(str).isin([str(x) for x in selected_refs])].copy()

# KPIs under filter
c1, c2, c3 = st.columns(3)
with c1:
    st.metric("💰 Tổng tiền bị ảnh hưởng", number_format(f_df["quantified_amount"].sum(skipna=True), " ₫"))
with c2:
    total_impact = f_df["impacted_accounts"].sum(skipna=True) if "impacted_accounts" in f_df.columns else np.nan
    try:
        total_impact_int = int(total_impact) if pd.notna(total_impact) else None
    except:
        total_impact_int = None
    st.metric("👥 Số KH/hồ sơ bị ảnh hưởng", f"{total_impact_int}" if total_impact_int is not None else "—")
with c3:
    st.metric("📌 Số dòng phát hiện", f"{len(f_df):,}")

st.markdown("---")

# ===== Tables per sub_category with desc + legal_reference =====
st.markdown("### 📑 Bảng chi tiết theo từng _sub_category_")
sub_order = f_df["sub_category"].value_counts().index.tolist()
for sub in sub_order:
    st.markdown(f"#### 🔹 {sub}")
    sub_df = f_df[f_df["sub_category"] == sub][[
        c for c in ["description", "legal_reference", "quantified_amount", "impacted_accounts", "Root_cause"]
        if c in f_df.columns
    ]].copy()
    if "quantified_amount" in sub_df.columns:
        sub_df["quantified_amount"] = sub_df["quantified_amount"].apply(lambda x: number_format(x, " ₫"))
    if "impacted_accounts" in sub_df.columns:
        sub_df["impacted_accounts"] = sub_df["impacted_accounts"].apply(lambda x: f"{int(x):,}" if pd.notna(x) else "—")
    rename_cols = {
        "description": "Mô tả",
        "legal_reference": "Điều luật/Quy định",
        "quantified_amount": "Số tiền ảnh hưởng",
        "impacted_accounts": "Số KH/Hồ sơ",
        "Root_cause": "Nguyên nhân gốc"
    }
    sub_df = sub_df.rename(columns=rename_cols)
    st.dataframe(sub_df, use_container_width=True)

st.markdown("---")
st.markdown("### 🧠 Nguyên nhân gốc theo **Legal_reference** đã lọc")
if "Root_cause" in f_df.columns:
    root_tbl = (
        f_df.groupby(["legal_reference", "Root_cause"], dropna=False)
        .agg(
            so_vu=("description", "count"),
            tong_tien=("quantified_amount", "sum"),
            tong_ho_so=("impacted_accounts", "sum"),
        ).reset_index()
    )
    root_tbl["tong_tien_fmt"] = root_tbl["tong_tien"].apply(lambda x: number_format(x, " ₫"))
    root_tbl["tong_ho_so_fmt"] = root_tbl["tong_ho_so"].apply(lambda x: f"{int(x):,}" if pd.notna(x) else "—")
    root_tbl = root_tbl[["legal_reference", "Root_cause", "so_vu", "tong_ho_so_fmt", "tong_tien_fmt"]]
    root_tbl = root_tbl.rename(columns={
        "legal_reference": "Điều luật/Quy định",
        "Root_cause": "Nguyên nhân gốc",
        "so_vu": "Số vụ",
        "tong_ho_so_fmt": "Tổng HS bị ảnh hưởng",
        "tong_tien_fmt": "Tổng tiền ảnh hưởng"
    })
    st.dataframe(root_tbl, use_container_width=True)
else:
    st.info("Không có cột Root_cause trong dữ liệu.")

st.markdown("---")
st.caption("© KLTT Dashboard • Streamlit • Altair • Plotly")
