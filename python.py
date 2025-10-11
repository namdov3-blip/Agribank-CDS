
# python.py
# Streamlit app: Dashboard trực quan hóa Kết luận Thanh tra (KLTT)
# Chạy: streamlit run python.py
# Yêu cầu: pip install streamlit pandas altair openpyxl

import io
import numpy as np
import pandas as pd
import streamlit as st
import altair as alt

st.set_page_config(page_title="KLTT Dashboard", page_icon="📑", layout="wide")

# ============== Helpers ==============

@st.cache_data(show_spinner=False)
def load_excel(uploaded_file: io.BytesIO) -> dict:
    xls = pd.ExcelFile(uploaded_file, engine="openpyxl")
    sheets = {s.lower().strip(): s for s in xls.sheet_names}
    dfs = {}
    for canon, real in sheets.items():
        df = pd.read_excel(xls, real)
        df.columns = [str(c).strip() for c in df.columns]
        dfs[canon] = df
    return dfs

def canonicalize(df: pd.DataFrame, mapping: dict) -> pd.DataFrame:
    new = {}
    exists = {c.lower(): c for c in df.columns}
    for want, alias in mapping.items():
        if want.lower() in exists:
            new[exists[want.lower()]] = alias
    return df.rename(columns=new)

def coalesce_series_with_raw(series: pd.Series, prefix="RAW"):
    s = series.copy()
    null_mask = s.isna() | (s.astype(str).str.strip().eq("")) | (s.astype(str).str.lower().eq("nan"))
    raw_index = np.cumsum(null_mask).where(null_mask, 0)
    s.loc[null_mask] = [f"{prefix}{i}" for i in raw_index[null_mask].astype(int)]
    mapping = {f"{prefix}{i+1}": None for i in range(int(raw_index.max() if len(raw_index)>0 else 0))}
    return s, mapping

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

def number_format(n, suffix=""):
    if pd.isna(n): return "—"
    try: n = float(n)
    except: return str(n)
    absn = abs(n)
    if absn >= 1_000_000_000_000: return f"{n/1_000_000_000_000:.2f} nghìn tỷ{suffix}"
    if absn >= 1_000_000_000:     return f"{n/1_000_000_000:.2f} tỷ{suffix}"
    if absn >= 1_000_000:         return f"{n/1_000_000:.2f} triệu{suffix}"
    if absn >= 1_000:             return f"{n/1_000:.2f} nghìn{suffix}"
    return f"{n:,.0f}{suffix}"

def text_block(label, value):
    st.markdown(
        f"""
        <div style="padding:10px;border:1px solid #eee;border-radius:10px;min-height:62px">
            <div style="font-size:12px;color:#777;margin-bottom:4px">{label}</div>
            <div style="font-size:15px;white-space:pre-wrap;word-break:break-word">{value}</div>
        </div>
        """, unsafe_allow_html=True
    )

# CSS improve wrapping in dataframes
st.markdown("""
<style>
[data-testid="stDataFrame"] div div div div table {table-layout:auto !important; width:100% !important;}
[data-testid="stDataFrame"] td, [data-testid="stDataFrame"] th {white-space:pre-wrap !important; word-break:break-word !important;}
</style>
""", unsafe_allow_html=True)

# ============== Sidebar / Upload ==============
with st.sidebar:
    st.header("📤 Tải file Excel tổng hợp")
    uploaded = st.file_uploader(
        "Chọn file Excel (.xlsx): documents • overalls • findings • actions (tuỳ chọn)",
        type=["xlsx"], accept_multiple_files=False
    )
    st.caption("Tên sheet không phân biệt hoa/thường.")

st.title("📑 Dashboard Kết luận Thanh tra (KLTT)")

if not uploaded:
    st.info("Vui lòng tải lên file Excel để bắt đầu.")
    st.stop()

data = load_excel(uploaded)
def get_sheet(cands): 
    for c in cands:
        if c in data: return data[c]
    return None

df_docs  = get_sheet(["documents","document","docs"])
df_over  = get_sheet(["overalls","overall"])
df_find  = get_sheet(["findings","finding"])
df_act   = get_sheet(["actions","action"])  # optional

if df_docs is None or df_over is None or df_find is None:
    st.error("Thiếu một trong các sheet bắt buộc: documents, overalls, findings.")
    st.stop()

# ============== Section 1: Documents (FULL TEXT, NO TRUNCATION) ==============
st.subheader("📄 Thông tin văn bản kết luận (documents)")

# Mapping per user spec (cập nhật tên cột)
doc_map = {
    "doc_id": "doc_id",            # giữ nếu có
    "Doc_id": "Doc_id",            # Mã số KLTT (y/c)
    "Issue_date": "Issue_date",    # Ngày phát hành (y/c)
    "title": "title",
    "Issuing_authority": "Issuing_authority",
    "inspected_entity_name": "inspected_entity_name",
    "sector": "sector",
    "period_start": "period_start",
    "period_end": "period_end",
    "Signer_name": "Signer_name",
    "Signer_title": "Signer_title",
}

df_docs = canonicalize(df_docs, doc_map)
for c in ["Issue_date", "period_start", "period_end"]:
    if c in df_docs.columns:
        df_docs[c] = safe_date(df_docs[c])

id_candidates = [c for c in ["Doc_id","doc_id","title"] if c in df_docs.columns]
select_by = id_candidates[0] if id_candidates else None
options = df_docs[select_by].astype(str).tolist() if select_by else []
selected = st.selectbox("Chọn KLTT", options, index=0 if options else None)
doc_row = df_docs[df_docs[select_by].astype(str)==str(selected)].iloc[0] if options else None

if doc_row is not None:
    a,b,c,d = st.columns(4)
    with a:
        text_block("Mã số KLTT (Doc_id)", str(doc_row.get("Doc_id", doc_row.get("doc_id","—"))))
        text_block("Đơn vị phát hành (Issuing_authority)", str(doc_row.get("Issuing_authority","—")))
        text_block("Người kiểm soát (Signer_name)", str(doc_row.get("Signer_name","—")))
    with b:
        issue_date = doc_row.get("Issue_date", pd.NaT)
        text_block("Ngày phát hành (Issue_date)", issue_date.strftime("%d/%m/%Y") if pd.notna(issue_date) else "—")
        text_block("Đơn vị được kiểm tra (inspected_entity_name)", str(doc_row.get("inspected_entity_name","—")))
        text_block("Chức vụ (Signer_title)", str(doc_row.get("Signer_title","—")))
    with c:
        text_block("Title", str(doc_row.get("title","—")))
        text_block("Lĩnh vực (sector)", str(doc_row.get("sector","—")))
    with d:
        ps = doc_row.get("period_start", pd.NaT)
        pe = doc_row.get("period_end", pd.NaT)
        text_block("Thời gian bắt đầu (period_start)", ps.strftime("%d/%m/%Y") if pd.notna(ps) else "—")
        text_block("Thời gian kết thúc (period_end)", pe.strftime("%d/%m/%Y") if pd.notna(pe) else "—")

st.markdown("---")

# ============== Section 2: Overalls ==============
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
for c in over_map.values():
    if c in df_over.columns: df_over[c] = df_over[c].apply(to_number)

over_row = df_over.iloc[-1] if len(df_over)>0 else pd.Series({})
k1,k2,k3,k4,k5,k6 = st.columns(6)
with k1: st.metric("Số phòng nghiệp vụ", f"{int(over_row.get('departments_at_hq_count', np.nan)) if pd.notna(over_row.get('departments_at_hq_count', np.nan)) else '—'}")
with k2: st.metric("Phòng giao dịch", f"{int(over_row.get('transaction_offices_count', np.nan)) if pd.notna(over_row.get('transaction_offices_count', np.nan)) else '—'}")
with k3: st.metric("Tổng nhân sự", f"{int(over_row.get('staff_total', np.nan)) if pd.notna(over_row.get('staff_total', np.nan)) else '—'}")
with k4: st.metric("Nguồn vốn gần nhất", number_format(over_row.get("mobilized_capital_vnd", np.nan), " ₫"))
with k5: st.metric("Dư nợ gần nhất", number_format(over_row.get("loans_outstanding_vnd", np.nan), " ₫"))
with k6: st.metric("Nợ xấu gần nhất", number_format(over_row.get("npl_total_vnd", np.nan), " ₫"))
k7,k8,k9 = st.columns(3)
with k7: st.metric("Tỷ lệ NPL / Dư nợ", f"{over_row.get('npl_ratio_percent', np.nan):.2f} %" if pd.notna(over_row.get('npl_ratio_percent', np.nan)) else "—")
with k8: st.metric("Số lượng mẫu kiểm tra", f"{int(over_row.get('sample_total_files', np.nan)) if pd.notna(over_row.get('sample_total_files', np.nan)) else '—'}")
with k9: st.metric("Tổng dư nợ đã kiểm tra", number_format(over_row.get("sample_outstanding_checked_vnd", np.nan), " ₫"))

st.markdown("---")

# ============== Section 3: Findings (TRỌNG TÂM) ==============
st.subheader("🔎 Phát hiện & vi phạm (findings)")

find_map = {
    "category": "category",
    "sub_category": "sub_category",
    "description": "description",
    "legal_reference": "legal_reference",
    "quantified_amount": "quantified_amount",
    "impacted_accounts": "impacted_accounts",
    "Root_cause": "Root_cause",
    "recommendation": "recommendation",
}
df_find = canonicalize(df_find, find_map)
required = ["category","sub_category","description","legal_reference"]
miss = [c for c in required if c not in df_find.columns]
if miss:
    st.error("Thiếu cột trong 'findings': " + ", ".join(miss))
    st.stop()

for c in ["quantified_amount","impacted_accounts"]:
    if c in df_find.columns: df_find[c] = df_find[c].apply(to_number)

# RAW labeling for filters (RAW1, RAW2...), nhưng biểu đồ line sẽ gộp RAWx -> RAW
df_find["legal_reference"], raw_map = coalesce_series_with_raw(df_find["legal_reference"], prefix="RAW")

# --- Chart 1: Bar (frequency by category)
st.markdown("**📊 Tần suất xuất hiện theo _category_**")
cat_count = df_find.groupby("category", dropna=False).size().reset_index(name="count")
bar_cat = alt.Chart(cat_count).mark_bar().encode(
    x=alt.X("count:Q", title="Số lần xuất hiện"),
    y=alt.Y("category:N", sort='-x', title="Category"),
    tooltip=["category:N","count:Q"]
).properties(height=320)
st.altair_chart(bar_cat, use_container_width=True)

# --- Chart 2: Grouped bar: category x sub_category (count)
st.markdown("**🏷️ Biểu đồ cột: Category × Sub_category (số lần xuất hiện)**")
cat_sub = df_find.groupby(["category","sub_category"], dropna=False).size().reset_index(name="count")
grouped = alt.Chart(cat_sub).mark_bar().encode(
    x=alt.X("sub_category:N", title="Sub_category"),
    y=alt.Y("count:Q", title="Số lần"),
    color=alt.Color("category:N", legend=alt.Legend(title="Category")),
    column=alt.Column("category:N", title=None, header=alt.Header(labelOrient="bottom"))
).resolve_scale(y='independent').properties(height=300)
st.altair_chart(grouped, use_container_width=True)

# --- Chart 3: Line chart Legal_reference frequency (collapse RAWx -> RAW)
st.markdown("**📈 Line chart: Số lần xuất hiện theo _Legal_reference_ (gộp RAWx → RAW)**")
df_find["_legal_for_chart"] = df_find["legal_reference"].astype(str).where(~df_find["legal_reference"].astype(str).str.startswith("RAW"), "RAW")
legal_count = df_find.groupby("_legal_for_chart").size().reset_index(name="count").sort_values("count", ascending=False)
legal_count["order"] = np.arange(1, len(legal_count)+1)
line_legal = alt.Chart(legal_count).mark_line(point=True).encode(
    x=alt.X("order:Q", axis=alt.Axis(title="Legal_reference (thứ tự)")),
    y=alt.Y("count:Q", title="Số lần"),
    tooltip=[alt.Tooltip("_legal_for_chart:N", title="Legal_reference"), "count:Q"]
).properties(height=320)
labels = alt.Chart(legal_count).mark_text(dy=-10).encode(
    x="order:Q", y="count:Q", text="_legal_for_chart:N"
)
st.altair_chart(line_legal + labels, use_container_width=True)
st.caption("RAW = Luật/Quy định không được nhắc rõ; các ô trống đã được gán RAW1, RAW2… và gộp thành RAW cho biểu đồ này.")

st.markdown("---")

# --- Filters by legal_reference (giữ RAW1, RAW2… riêng để lọc chi tiết)
st.markdown("### 🧯 Bộ lọc theo **Legal_reference** (RAW1, RAW2… giữ nguyên để lọc chi tiết)")
all_refs = sorted(df_find["legal_reference"].astype(str).unique().tolist())
selected_refs = st.multiselect("Chọn Legal_reference", options=all_refs, default=all_refs)
f_df = df_find[df_find["legal_reference"].astype(str).isin([str(x) for x in selected_refs])].copy()

# KPIs under filter
c1,c2,c3,c4 = st.columns(4)
with c1:
    st.metric("💰 Tổng tiền bị ảnh hưởng", number_format(f_df.get("quantified_amount", pd.Series(dtype=float)).sum(skipna=True), " ₫"))
with c2:
    tot_imp = f_df.get("impacted_accounts", pd.Series(dtype=float)).sum(skipna=True)
    st.metric("👥 Số KH/Hồ sơ bị ảnh hưởng", f"{int(tot_imp) if pd.notna(tot_imp) else '—'}")
with c3:
    st.metric("📌 Số dòng phát hiện", f"{len(f_df):,}")
with c4:
    ref_freq = f_df.groupby("legal_reference").size().sum()
    st.metric("🔢 Tổng lượt lỗi (theo legal_reference)", f"{int(ref_freq):,}")

# --- Bảng tần suất lỗi theo legal_reference (kể cả phụ lục khác nhau)
st.markdown("#### 📚 Tần suất từng **Legal_reference** (giữ phân biệt các phụ lục/điểm khoản)")
freq_tbl = f_df.groupby("legal_reference", dropna=False).size().reset_index(name="Số lần")
st.dataframe(freq_tbl.sort_values("Số lần", ascending=False), use_container_width=True)

# --- Bảng chi tiết theo sub_category
st.markdown("### 📑 Bảng chi tiết theo từng _sub_category_")
order_sub = f_df["sub_category"].value_counts().index.tolist()
for sub in order_sub:
    st.markdown(f"#### 🔹 {sub}")
    cols_show = [c for c in ["description","legal_reference","quantified_amount","impacted_accounts","Root_cause","recommendation"] if c in f_df.columns]
    sub_df = f_df[f_df["sub_category"]==sub][cols_show].copy()
    if "quantified_amount" in sub_df.columns:
        sub_df["quantified_amount"] = sub_df["quantified_amount"].apply(lambda x: number_format(x," ₫"))
    if "impacted_accounts" in sub_df.columns:
        sub_df["impacted_accounts"] = sub_df["impacted_accounts"].apply(lambda x: f"{int(x):,}" if pd.notna(x) else "—")
    rename = {
        "description":"Mô tả",
        "legal_reference":"Điều luật/Quy định",
        "quantified_amount":"Số tiền ảnh hưởng",
        "impacted_accounts":"Số KH/Hồ sơ",
        "Root_cause":"Nguyên nhân gốc",
        "recommendation":"Khuyến nghị"
    }
    st.dataframe(sub_df.rename(columns=rename), use_container_width=True)

# --- Root cause summary + recommendations
st.markdown("### 🧠 Tổng hợp Nguyên nhân gốc & Khuyến nghị theo **Legal_reference**")
has_root = "Root_cause" in f_df.columns
has_rec  = "recommendation" in f_df.columns
if has_root:
    agg = {"description":"count"}
    if "quantified_amount" in f_df.columns: agg["quantified_amount"]="sum"
    if "impacted_accounts" in f_df.columns: agg["impacted_accounts"]="sum"
    group_cols = ["legal_reference","Root_cause"]
    if has_rec: group_cols.append("recommendation")
    root_tbl = f_df.groupby(group_cols, dropna=False).agg(agg).reset_index().rename(columns={"description":"Số vụ"})
    if "quantified_amount" in root_tbl.columns:
        root_tbl["Tổng tiền ảnh hưởng"] = root_tbl["quantified_amount"].apply(lambda x: number_format(x," ₫"))
        root_tbl = root_tbl.drop(columns=["quantified_amount"])
    if "impacted_accounts" in root_tbl.columns:
        root_tbl["Tổng hồ sơ bị ảnh hưởng"] = root_tbl["impacted_accounts"].apply(lambda x: f"{int(x):,}" if pd.notna(x) else "—")
        root_tbl = root_tbl.drop(columns=["impacted_accounts"])
    show_cols = ["legal_reference","Root_cause"]
    if has_rec: show_cols.append("recommendation")
    show_cols += [c for c in ["Số vụ","Tổng hồ sơ bị ảnh hưởng","Tổng tiền ảnh hưởng"] if c in root_tbl.columns]
    st.dataframe(root_tbl[show_cols], use_container_width=True)
else:
    st.info("Không có cột Root_cause trong findings.")

st.markdown("---")

# ============== Section 4: Actions (optional) ==============
st.subheader("🛠️ Biện pháp khắc phục (actions)")
if df_act is None:
    st.info("Không có sheet actions. (Cần cột: action_type, legal_reference, action_description, evidence_of_completion)")
else:
    act_map = {
        "action_type":"action_type",
        "legal_reference":"legal_reference",
        "action_description":"action_description",
        "evidence_of_completion":"evidence_of_completion",
    }
    df_act = canonicalize(df_act, act_map)

    if "action_type" in df_act.columns:
        st.markdown("**📊 Phân loại biện pháp theo _action_type_**")
        act_count = df_act.groupby("action_type", dropna=False).size().reset_index(name="count")
        bar_act = alt.Chart(act_count).mark_bar().encode(
            x=alt.X("count:Q", title="Số biện pháp"),
            y=alt.Y("action_type:N", sort='-x', title="Action type"),
            tooltip=["action_type:N","count:Q"]
        ).properties(height=320)
        st.altair_chart(bar_act, use_container_width=True)

    st.markdown("**📑 Bảng hành động chi tiết**")
    rename = {
        "legal_reference":"Điều luật/Quy định",
        "action_description":"Nội dung công việc",
        "evidence_of_completion":"Công việc chi tiết/Minh chứng hoàn thành",
        "action_type":"Loại biện pháp"
    }
    show_cols = [c for c in ["action_type","legal_reference","action_description","evidence_of_completion"] if c in df_act.columns]
    st.dataframe(df_act[show_cols].rename(columns=rename), use_container_width=True)

st.caption("© KLTT Dashboard • Streamlit • Altair")
