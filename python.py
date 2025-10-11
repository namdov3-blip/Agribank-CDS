import io
import numpy as np
import pandas as pd
import streamlit as st
import altair as alt
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO

# --- Cấu hình Trang Streamlit ---
st.set_page_config(
    page_title="Dashboard Kết luận Thanh tra (KLTT)",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -----------------------------
# 1. HELPERS & UTILITIES
# -----------------------------

@st.cache_data(show_spinner=False)
def load_excel(uploaded_file: io.BytesIO) -> dict:
    """Đọc tất cả các sheet từ file Excel và chuẩn hóa tên cột."""
    xls = pd.ExcelFile(uploaded_file, engine="openpyxl")
    # Tên sheet chuẩn hóa (lowercase, strip)
    sheets = {s.lower().strip(): s for s in xls.sheet_names}
    dfs = {}
    
    with st.spinner("Đang tải và chuẩn hóa dữ liệu..."):
        for canon, real in sheets.items():
            df = pd.read_excel(xls, real)
            # Chuẩn hóa tên cột: strip
            df.columns = [str(c).strip() for c in df.columns]
            dfs[canon] = df
    return dfs

def canonicalize_df(df, mapping):
    """Ánh xạ tên cột (kể cả chữ hoa/thường) sang tên chuẩn."""
    new_cols = {}
    # Lấy mapping từ tên cột hiện tại (lowercase) sang tên cột gốc
    existing_lower = {c.lower(): c for c in df.columns}
    
    for want_lower, aliases in mapping.items():
        # Tìm cột khớp với bất kỳ alias nào
        found_col = None
        for alias in aliases:
            if alias.lower() in existing_lower:
                found_col = existing_lower[alias.lower()]
                break
        
        if found_col:
            # Gán lại tên cột chuẩn (ví dụ: 'legal_reference')
            new_cols[found_col] = want_lower
    
    return df.rename(columns=new_cols)

def coalesce_series_with_raw(series: pd.Series, prefix="RAW"):
    """Thay thế các giá trị rỗng/NaN bằng RAW1, RAW2..."""
    s = series.copy().astype(str).str.strip()
    # Mask cho các giá trị rỗng, NaN hoặc chỉ khoảng trắng
    null_mask = s.isna() | s.eq("") | s.str.lower().eq("nan")
    
    if null_mask.any():
        # Gán nhãn RAW duy nhất cho mỗi ô trống
        raw_index = np.cumsum(null_mask).where(null_mask, 0)
        s.loc[null_mask] = [f"{prefix}-{i:02d}" for i in raw_index[null_mask].astype(int)]
    
    return s.replace({f"{prefix}-00": np.nan}) # Loại bỏ index 0 nếu có

def to_number(x):
    """Chuyển đổi giá trị sang số, xử lý các định dạng tiền tệ cơ bản."""
    if pd.isna(x):
        return np.nan
    if isinstance(x, (int, float, np.number)):
        return float(x)
    try:
        # Xóa dấu phẩy, khoảng trắng để chuyển đổi
        return float(str(x).replace(",", "").replace(" ", ""))
    except:
        return np.nan

def format_vnd(amount):
    """Định dạng tiền tệ sang Tỷ/Triệu VND"""
    if pd.isna(amount):
        return "—"
    if abs(amount) >= 1_000_000_000_000:
        return f"{amount / 1_000_000_000_000:.2f} nghìn tỷ ₫"
    elif abs(amount) >= 1_000_000_000:
        return f"{amount / 1_000_000_000:.2f} tỷ ₫"
    elif abs(amount) >= 1_000_000:
        return f"{amount / 1_000_000:.2f} triệu ₫"
    else:
        return f"{amount:,.0f} ₫"

def format_metric(value, unit=""):
    """Định dạng số lớn"""
    if pd.isna(value):
        return "—"
    if abs(value) >= 1_000_000_000_000:
        return f"{value / 1e12:.2f} T"
    elif abs(value) >= 1_000_000_000:
        return f"{value / 1e9:.2f} Tỷ"
    elif abs(value) >= 1_000_000:
        return f"{value / 1e6:.2f} Tr"
    return f"{value:,.0f} {unit}"

# -----------------------------
# 2. DATA MAPPING & LOAD
# -----------------------------

# Tên cột chuẩn hóa và các tên thay thế (alias) có thể chấp nhận
COL_MAPPING = {
    "documents": {
        "doc_id": ["doc_id", "Doc_code", "Maso", "MaKLTT"],
        "issue_date": ["issue_date", "Issues_date", "NgayPH"],
        "title": ["title", "Tieude"],
        "issuing_authority": ["issuing_authority", "DVphanh", "CquanPH"],
        "inspected_entity_name": ["inspected_entity_name", "DVkiemtra", "DonviKT"],
        "sector": ["sector", "Linhvuc"],
        "period_start": ["period_start", "Batdau"],
        "period_end": ["period_end", "Ketthuc"],
        "signer_name": ["signer_name", "Nguoiky", "Signer_name"],
        "signer_title": ["signer_title", "Chucvu", "Signer_title"],
    },
    "overalls": {
        "departments_at_hq_count": ["departments_at_hq_count", "PhongKD", "SoPhong"],
        "transaction_offices_count": ["transaction_offices_count", "PhongGD", "SoGD"],
        "staff_total": ["staff_total", "TongNV", "NV"],
        "mobilized_capital_vnd": ["mobilized_capital_vnd", "Nguonvon", "Vondong"],
        "loans_outstanding_vnd": ["loans_outstanding_vnd", "Soduno", "Duno"],
        "npl_total_vnd": ["npl_total_vnd", "Noxau", "TongNPL"],
        "npl_ratio_percent": ["npl_ratio_percent", "Ty le NPL", "NPLrate"],
        "sample_total_files": ["sample_total_files", "Somau", "MauKT"],
        "sample_outstanding_checked_vnd": ["sample_outstanding_checked_vnd", "DunoKT", "TienmauKT"],
    },
    "findings": {
        "category": ["category", "MucLoi", "PhanLoai"],
        "sub_category": ["sub_category", "LoiCT", "TieuPhanLoai"],
        "description": ["description", "Mota", "Noidung"],
        # Cột legal_reference bắt buộc để liên kết với Actions
        "legal_reference": ["legal_reference", "Dieuluat", "Quy dinh", "Thamchieu"], 
        "quantified_amount": ["quantified_amount", "Sotien", "TienAnhhuong"],
        "impacted_accounts": ["impacted_accounts", "SoHoSo", "SoKH"],
        "root_cause": ["root_cause", "Nguyengoc", "LyDo"],
        "recommendation": ["recommendation", "Kiennghi", "DeXuat"],
        # CÁC CỘT ACTION ĐÃ ĐƯỢC CHUYỂN SANG MAPPING "actions" RIÊNG BIỆT
    },
    "actions": { # MAPPING MỚI CHO SHEET ACTIONS
        "legal_reference": ["legal_reference", "Dieuluat", "Quy dinh", "Thamchieu"], # Dùng để lọc và liên kết
        "action_type": ["action_type", "LoaiAction", "Tinhchat"],
        "action_description": ["action_description", "MotaAction", "NoidungXP"],
        "evidence_of_completion": ["evidence_of_completion", "Minhchung", "Hoanthanh"],
    }
}

# --- Giao diện Ứng dụng ---

st.title("🛡️ Dashboard Báo Cáo Kết Luận Thanh Tra")

# Tải file Excel
uploaded_file = st.file_uploader(
    # Cập nhật mô tả để bao gồm sheet actions
    "Tải lên file Excel (.xlsx) chứa các sheet: **documents, overalls, findings, actions**", 
    type=["xlsx"]
)

if not uploaded_file:
    st.info("Vui lòng tải lên file Excel để bắt đầu. Ứng dụng sẽ tự động cố gắng nhận diện tên các cột.")
    st.stop()

# Load data from Excel
data = load_excel(uploaded_file)

# Lấy dữ liệu từ các sheet và chuẩn hóa tên cột
def get_processed_df(sheet_name):
    df_raw = data.get(sheet_name)
    # Tên sheet chuẩn hóa (ví dụ: 'actions') sẽ được dùng để kiểm tra COL_MAPPING
    mapping = COL_MAPPING.get(sheet_name)
    
    if df_raw is None or mapping is None:
        # Nếu không có sheet hoặc mapping, trả về DF rỗng nhưng không báo lỗi nếu sheet không bắt buộc
        return pd.DataFrame() 
    
    # Chuẩn hóa tên cột bằng mapping đã định nghĩa
    df_canonical = canonicalize_df(df_raw.copy(), mapping)
    
    # Kiểm tra cột bắt buộc
    required_cols = list(mapping.keys())
    missing_cols = [col for col in required_cols if col not in df_canonical.columns]
    
    # Chỉ check nghiêm ngặt các sheet 'documents', 'findings', 'actions'
    if missing_cols and sheet_name in ["documents", "findings", "actions"]:
        st.error(f"Sheet **'{sheet_name}'** thiếu các cột bắt buộc đã được chuẩn hóa: **{', '.join(missing_cols)}**. Vui lòng kiểm tra lại tên cột trong file Excel.")
        st.stop()
        
    return df_canonical

# Tải 4 sheet chính
df_docs = get_processed_df("documents")
df_over = get_processed_df("overalls")
df_findings = get_processed_df("findings")
df_actions = get_processed_df("actions") # Tải sheet Actions riêng biệt

# --- XỬ LÝ DỮ LIỆU CHUNG ---

# Xử lý các cột ngày tháng
date_cols = ["issue_date", "period_start", "period_end"]
for col in date_cols:
    if col in df_docs.columns:
        df_docs[col] = pd.to_datetime(df_docs[col], errors='coerce')
        
# Xử lý cột số trong Overalls
num_over_cols = [c for c in COL_MAPPING['overalls'] if c in df_over.columns]
for col in num_over_cols:
    df_over[col] = df_over[col].apply(to_number)
    
# Xử lý cột số trong Findings
num_find_cols = ["quantified_amount", "impacted_accounts"]
for col in num_find_cols:
    if col in df_findings.columns:
        df_findings[col] = df_findings[col].apply(to_number)

# XỬ LÝ LỖI 'legal_reference' (RAW) cho df_findings
if "legal_reference" in df_findings.columns:
    df_findings["legal_reference_filter"] = coalesce_series_with_raw(df_findings["legal_reference"], prefix="RAW")
    
    # Tạo cột cho mục đích biểu đồ (gom tất cả RAW lại thành 1 nhóm)
    df_findings['legal_reference_chart'] = df_findings['legal_reference_filter'].apply(
        lambda x: 'RAW (Chưa xác định)' if 'RAW' in str(x) and str(x) != x else x
    )
else:
    # Nếu cột legal_reference hoàn toàn không tồn tại
    st.error("Sheet 'findings' không có cột 'legal_reference' (hoặc tên thay thế tương đương) để liên kết. Vui lòng kiểm tra lại.")
    st.stop()


# Lấy dữ liệu Documents và Overalls (Chỉ lấy hàng đầu tiên)
if not df_docs.empty:
    doc_data = df_docs.iloc[0].to_dict()
else:
    doc_data = {c: "Không có dữ liệu" for c in COL_MAPPING["documents"]}
    
if not df_over.empty:
    # Lấy hàng cuối cùng hoặc tổng hợp nếu có nhiều hàng
    over_data = df_over.iloc[-1].to_dict()
else:
    over_data = {c: np.nan for c in COL_MAPPING["overalls"]}


# --- SIDEBAR: FILTER ---
st.sidebar.header("🔍 Bộ Lọc Phát Hiện (Findings Filter)")

unique_legal_refs = sorted(df_findings['legal_reference_filter'].astype(str).unique())
selected_refs = st.sidebar.multiselect(
    "Chọn (các) Điều luật/Quy định Vi phạm:",
    options=unique_legal_refs,
    default=unique_legal_refs # Mặc định chọn tất cả
)

# Lọc DataFrame Findings
df_filtered = df_findings[df_findings['legal_reference_filter'].astype(str).isin([str(x) for x in selected_refs])]

# Lọc DataFrame Actions (Dùng chung bộ lọc legal_reference)
df_actions_filtered = pd.DataFrame()
if not df_actions.empty and "legal_reference" in df_actions.columns:
    df_actions["legal_reference_filter"] = coalesce_series_with_raw(df_actions["legal_reference"], prefix="RAW")
    df_actions_filtered = df_actions[df_actions['legal_reference_filter'].astype(str).isin([str(x) for x in selected_refs])]

# Hiển thị số liệu tổng hợp trong sidebar
st.sidebar.markdown("---")
total_quantified = df_filtered['quantified_amount'].sum() if 'quantified_amount' in df_filtered.columns else 0
total_impacted = df_filtered['impacted_accounts'].sum() if 'impacted_accounts' in df_filtered.columns else 0

st.sidebar.metric(
    label="💸 Tổng Tiền Bị Ảnh Hưởng (Lọc)",
    value=format_vnd(total_quantified)
)
st.sidebar.metric(
    label="👤 Tổng Hồ Sơ Bị Ảnh Hưởng (Lọc)",
    value=f"{total_impacted:,.0f}"
)


# --- BỐ CỤC CHÍNH (TABS) ---
tab1, tab2, tab3, tab4 = st.tabs(["📝 Documents", "📊 Overalls", "🚨 Findings", "✅ Actions"])

# ====================================
# TAB 1: DOCUMENTS (Metadata)
# ====================================
with tab1:
    st.header("Báo Cáo Kết Luận Thanh Tra (Metadata)")
    st.markdown("---")
    
    col1, col2 = st.columns([1, 2])
    
    # Định dạng lại ngày tháng
    def safe_date_format(date_obj):
        return date_obj.strftime('%d/%m/%Y') if pd.notna(date_obj) else "—"

    with col1:
        st.markdown(f"**Mã số kết luận thanh tra:** `{doc_data.get('doc_id', '—')}`")
        st.markdown(f"**Ngày phát hành:** `{safe_date_format(doc_data.get('issue_date'))}`")
        st.markdown(f"**Lĩnh vực:** `{doc_data.get('sector', '—')}`")
        st.markdown(f"**Người kiểm soát:** `{doc_data.get('signer_name', '—')}`")
        st.markdown(f"**Chức vụ:** `{doc_data.get('signer_title', '—')}`")
        st.markdown(f"**Thời gian bắt đầu:** `{safe_date_format(doc_data.get('period_start'))}`")
        st.markdown(f"**Thời gian kết thúc:** `{safe_date_format(doc_data.get('period_end'))}`")

    with col2:
        st.markdown("**Title của kết luận thanh tra:**")
        st.info(doc_data.get('title', '—'))
        
        st.markdown("**Đơn vị phát hành:**")
        st.info(doc_data.get('issuing_authority', '—'))
        
        st.markdown("**Đơn vị được kiểm tra:**")
        st.info(doc_data.get('inspected_entity_name', '—'))

# ====================================
# TAB 2: OVERALLS (Metrics)
# ====================================
with tab2:
    st.header("Thông Tin Tổng Quan Về Đơn Vị Được Kiểm Tra")
    st.markdown("---")

    col_staff, col_offices, col_capital, col_loan, col_npl = st.columns(5)

    with col_staff:
        st.metric("Tổng số lượng nhân viên", f"{over_data.get('staff_total', np.nan):,.0f}" if pd.notna(over_data.get('staff_total')) else "—")
        st.metric("Số lượng mẫu kiểm tra", f"{over_data.get('sample_total_files', np.nan):,.0f}" if pd.notna(over_data.get('sample_total_files')) else "—")
    
    with col_offices:
        st.metric("Phòng nghiệp vụ (HQ_count)", f"{over_data.get('departments_at_hq_count', np.nan):,.0f}" if pd.notna(over_data.get('departments_at_hq_count')) else "—")
        st.metric("Phòng giao dịch (Transaction_offices_count)", f"{over_data.get('transaction_offices_count', np.nan):,.0f}" if pd.notna(over_data.get('transaction_offices_count')) else "—")

    with col_capital:
        st.metric("Tổng số nguồn vốn", format_metric(over_data.get('mobilized_capital_vnd')))

    with col_loan:
        st.metric("Tổng số dư nợ", format_metric(over_data.get('loans_outstanding_vnd')))

    with col_npl:
        st.metric("Tổng số nợ xấu", format_metric(over_data.get('npl_total_vnd')))
        st.metric("Tỷ lệ NPL (%)", f"{over_data.get('npl_ratio_percent', np.nan):.2f}%" if pd.notna(over_data.get('npl_ratio_percent')) else "—")
        st.metric("Tổng tiền kiểm tra", format_metric(over_data.get('sample_outstanding_checked_vnd')))


# ====================================
# TAB 3: FINDINGS (Phát hiện & Nguyên nhân)
# ====================================
with tab3:
    st.header("Phân Tích Chi Tiết Phát Hiện (Findings)")
    st.subheader(f"Dữ liệu đang được lọc theo: **{len(selected_refs)}/{len(unique_legal_refs)} điều luật**")
    st.markdown("---")
    
    if df_filtered.empty:
        st.warning("Không có dữ liệu phát hiện nào khớp với bộ lọc hiện tại.")
    else:
        # ------------------
        # 3.1. Biểu đồ Phân loại
        # ------------------
        col_cat, col_sub_cat = st.columns(2)
        
        # Chart 1: Biểu đồ Bar cho Category
        with col_cat:
            st.subheader("1. Số lần xuất hiện của các Mục Lỗi (Category)")
            df_category_count = df_filtered['category'].value_counts().reset_index()
            df_category_count.columns = ['Category', 'Count']
            
            fig_cat = px.bar(
                df_category_count, 
                x='Category', 
                y='Count', 
                text='Count',
                title='Thống kê lỗi theo Category',
                color='Category'
            )
            fig_cat.update_traces(textposition='outside')
            fig_cat.update_layout(height=400, xaxis_title="", yaxis_title="Số lần xuất hiện")
            st.plotly_chart(fig_cat, use_container_width=True)

        # Chart 2: Biểu đồ Cột (Grouped Bar) cho Sub-category phân theo Category
        with col_sub_cat:
            st.subheader("2. Phân loại Lỗi Chi tiết (Sub-category theo Category)")
            df_grouped = df_filtered.groupby(['category', 'sub_category']).size().reset_index(name='Count')
            
            fig_sub_cat = px.bar(
                df_grouped, 
                x='category', 
                y='Count', 
                color='sub_category',
                title='Sub-category Count trong từng Category',
                labels={'category': 'Mục Lỗi (Category)', 'Count': 'Số lần xuất hiện', 'sub_category': 'Lỗi Chi tiết'}
            )
            fig_sub_cat.update_layout(barmode='group', height=400, xaxis_title="Mục Lỗi")
            st.plotly_chart(fig_sub_cat, use_container_width=True)
            
        st.markdown("---")
        
        # ------------------
        # 3.2. Biểu đồ Line Chart cho Legal Reference
        # ------------------
        st.subheader("3. Xu hướng Lỗi theo Điều Luật/Quy định (Legal Reference)")
        
        # Chuẩn bị dữ liệu cho Line Chart: Sử dụng cột legal_reference_chart đã gom 'RAW'
        df_legal_count = df_filtered['legal_reference_chart'].value_counts().reset_index()
        df_legal_count.columns = ['Legal_Reference', 'Count']

        fig_line = px.line(
            df_legal_count,
            x='Legal_Reference',
            y='Count',
            markers=True,
            title="Số lần xuất hiện của từng điều luật (Gom nhóm RAW)",
            labels={'Legal_Reference': 'Điều Luật/Quy định', 'Count': 'Số lần xuất hiện'}
        )
        
        st.plotly_chart(fig_line, use_container_width=True)
        st.markdown("""
            <div style='background-color: #f0f2f6; padding: 10px; border-radius: 5px; margin-bottom: 10px;'>
                **Chú thích:** *RAW (Chưa xác định)* là nhóm tổng hợp các sai phạm mà điều luật/quy định không được nhắc tới rõ ràng trong file gốc (đã được đánh số từ RAW-01, RAW-02...).
            </div>
        """, unsafe_allow_html=True)
        
        st.markdown("---")

        # ------------------
        # 3.3. Bảng Chi tiết và Phân tích Nguyên nhân
        # ------------------
        st.subheader("4. Chi tiết Sai phạm, Nguyên nhân và Kiến nghị")
        
        # Nhóm dữ liệu theo sub_category để hiển thị bảng chi tiết
        sub_categories = df_filtered['sub_category'].unique()

        for sub_cat in sub_categories:
            st.markdown(f"#### 🔎 Lỗi Chi tiết: **{sub_cat}** (Số lần xuất hiện: {len(df_filtered[df_filtered['sub_category'] == sub_cat]):,})")
            
            # Lựa chọn các cột cần hiển thị (Không còn cột action_type, action_description, evidence_of_completion)
            display_cols = ['legal_reference_filter', 'description', 'quantified_amount', 'impacted_accounts']
            if 'root_cause' in df_filtered.columns:
                display_cols.append('root_cause')
            if 'recommendation' in df_filtered.columns:
                display_cols.append('recommendation')
                
            df_sub_cat = df_filtered[df_filtered['sub_category'] == sub_cat].reset_index(drop=True)[display_cols]
            
            # Đổi tên cột hiển thị
            rename_map = {
                'legal_reference_filter': 'Luật Lệ (RAW-XX)',
                'description': 'Mô tả Sai phạm',
                'quantified_amount': 'Số tiền Ảnh hưởng (VND)',
                'impacted_accounts': 'Số KH/Hồ sơ Ảnh hưởng',
                'root_cause': 'Nguyên nhân Gốc',
                'recommendation': 'Kiến nghị Thay đổi'
            }
            
            # Bảng hiển thị đầy đủ
            st.dataframe(
                df_sub_cat.rename(columns=rename_map).style.format({
                    'Số tiền Ảnh hưởng (VND)': lambda x: format_vnd(x),
                    'Số KH/Hồ sơ Ảnh hưởng': lambda x: f"{x:,.0f}" if pd.notna(x) else "—"
                }),
                use_container_width=True,
                height=300
            )
            st.markdown("---")

# ====================================
# TAB 4: ACTIONS (Biện pháp Khắc phục)
# ====================================
with tab4:
    st.header("Phân Tích Biện Pháp Khắc Phục (Actions)")
    st.subheader(f"Dữ liệu Hành động đang được lọc theo: **{len(selected_refs)}/{len(unique_legal_refs)} điều luật**")
    st.markdown("---")
    
    # SỬ DỤNG DATAFRAME ĐÃ LỌC RIÊNG CHO ACTIONS
    if df_actions_filtered.empty:
        st.warning("Không có dữ liệu hành động nào khớp với bộ lọc hiện tại hoặc sheet 'actions' không tồn tại/bị thiếu cột.")
    else:
        # ------------------
        # 4.1. Biểu đồ Phân loại Hành động
        # ------------------
        if 'action_type' in df_actions_filtered.columns:
            st.subheader("1. Phân loại Tính chất của Biện pháp Cải tạo (Action Type)")
            df_action_count = df_actions_filtered['action_type'].value_counts().reset_index()
            df_action_count.columns = ['Action_Type', 'Count']
            
            fig_action = px.pie(
                df_action_count, 
                values='Count', 
                names='Action_Type', 
                title='Phân loại Biện pháp Cải tạo',
                hole=.3
            )
            fig_action.update_traces(textinfo='percent+label', marker=dict(line=dict(color='#000000', width=1)))
            st.plotly_chart(fig_action, use_container_width=True)
            st.markdown("---")
        
        # ------------------
        # 4.2. Bảng Chi tiết Hành động
        # ------------------
        st.subheader("2. Bảng Chi tiết Kế hoạch Hành động (Action Plan)")
        
        # Lựa chọn các cột hành động cần hiển thị
        action_cols = ['legal_reference_filter', 'action_type', 'action_description', 'evidence_of_completion']
        action_cols = [c for c in action_cols if c in df_actions_filtered.columns] # Chỉ lấy cột có tồn tại
        
        rename_map = {
            'legal_reference_filter': 'Luật Lệ Liên quan (RAW-XX)',
            'action_type': 'Tính chất Biện pháp',
            'action_description': 'Nội dung Công việc Cần làm',
            'evidence_of_completion': 'Minh chứng Hoàn thành'
        }
        
        # Bảng chi tiết
        st.dataframe(
            df_actions_filtered[action_cols].rename(columns=rename_map),
            use_container_width=True,
            height=500
        )

        st.markdown("""
            <div style='text-align: right; margin-top: 15px; font-style: italic; color: #555;'>
                *Dữ liệu đang hiển thị theo bộ lọc Điều luật/Quy định đã chọn ở sidebar.*
            </div>
        """, unsafe_allow_html=True)
