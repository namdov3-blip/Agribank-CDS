import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO

# --- Cấu hình Trang Streamlit ---
st.set_page_config(
    page_title="Dashboard Báo Cáo Kết Luận Thanh Tra",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Dữ Liệu Giả Định (Mô phỏng cấu trúc file Excel đầu vào) ---
@st.cache_data
def load_and_preprocess_data():
    """Tạo dữ liệu giả định và xử lý sơ bộ."""
    
    # 1. Dữ liệu Documents & Overalls (Chủ yếu lấy từ hàng đầu tiên)
    data = {
        'doc_id': ['KLTT-2025/ABC'] * 30,
        'issue_date': [pd.to_datetime('2025-06-15')] * 30,
        'title': ['Kết luận thanh tra toàn diện hoạt động tín dụng, nguồn vốn và quản lý rủi ro tại VietinBank Chi nhánh HCM'] * 30,
        'issuing_authority': ['Ngân hàng Nhà nước Việt Nam'] * 30,
        'inspected_entity_name': ['VietinBank - Chi nhánh Hồ Chí Minh'] * 30,
        'sector': ['Ngân hàng & Tài chính'] * 30,
        'period_start': [pd.to_datetime('2024-01-01')] * 30,
        'period_end': [pd.to_datetime('2024-12-31')] * 30,
        'signer_name': ['Trần Văn A'] * 30,
        'signer_title': ['Chánh Thanh tra, Giám sát Ngân hàng'] * 30,
        'departments_at_hq_count': [5] * 30,
        'transaction_offices_count': [25] * 30,
        'staff_total': [580] * 30,
        'mobilized_capital_vnd': [125000000000000] * 30, # 125 nghìn tỷ
        'loans_outstanding_vnd': [98000000000000] * 30, # 98 nghìn tỷ
        'npl_total_vnd': [2500000000000] * 30, # 2.5 nghìn tỷ
        'npl_ratio_percent': [2.55] * 30, # 2.55%
        'sample_total_files': [250] * 30,
        'sample_outstanding_checked_vnd': [50000000000000] * 30, # 50 nghìn tỷ
        
        # 2. Dữ liệu Findings & Actions (Mỗi hàng là một sai phạm/phát hiện)
        'category': np.random.choice(['Quy trình Tín dụng', 'Quản lý Nguồn vốn', 'Hệ thống Rủi ro'], size=30, p=[0.5, 0.3, 0.2]),
        'sub_category': np.random.choice([
            'Hồ sơ thiếu', 'Định giá TSĐB sai', 'Vi phạm trần lãi suất', 
            'Không tuân thủ KYC', 'Phân loại nợ chưa đúng'], size=30),
        'description': [f'Mô tả chi tiết sai phạm {i+1}. Đây là nội dung dài cần được hiển thị đầy đủ.' for i in range(30)],
        'legal_reference': [
            'Thông tư 39/2016/TT-NHNN', 'Luật Các TCTD 2010', '', 'Nghị định 01/2021/NĐ-CP', 
            'Thông tư 11/2021/TT-NHNN', 'Quyết định 1627/2001/QĐ-NHNN', np.nan] * 4 + [''],
        'quantified_amount': np.random.randint(100000000, 5000000000, size=30),
        'impacted_accounts': np.random.randint(1, 50, size=30),
        'root_cause': np.random.choice(['Nhân sự yếu kém', 'Thiếu kiểm soát', 'Lỗi hệ thống'], size=30),
        'recommendation': [f'Đào tạo nhân viên và cập nhật quy trình. Mục {i+1}' for i in range(30)],
        'action_type': np.random.choice(['Khắc phục Tài chính', 'Thay đổi Quy trình', 'Xử lý Kỷ luật'], size=30, p=[0.4, 0.4, 0.2]),
        'action_description': [f'Cần hoàn thiện hồ sơ tín dụng theo Thông tư 39 trong 30 ngày. Mục {i+1}' for i in range(30)],
        'evidence_of_completion': [f'Biên bản họp hội đồng quản trị ngày 01/08/2025. Mục {i+1}' for i in range(30)],
    }
    df = pd.DataFrame(data)
    
    # 3. Xử lý cột Legal_reference cho Filter và Chart
    df['legal_reference'] = df['legal_reference'].fillna('')
    
    # Tạo cột cho mục đích lọc (RAW1, RAW2,...)
    raw_indices = df[df['legal_reference'] == ''].index
    raw_map = {index: f"RAW-{i+1}" for i, index in enumerate(raw_indices)}
    df['legal_reference_filter'] = df.apply(
        lambda row: raw_map.get(row.name) if row['legal_reference'] == '' else row['legal_reference'], 
        axis=1
    )
    
    # Tạo cột cho mục đích biểu đồ (gom tất cả RAW lại thành 1 nhóm)
    df['legal_reference_chart'] = df['legal_reference_filter'].apply(
        lambda x: 'RAW (Chưa xác định)' if 'RAW-' in x else x
    )

    return df

# --- Hàm định dạng tiền tệ ---
def format_vnd(amount):
    """Định dạng tiền tệ sang Tỷ/Triệu VND"""
    if amount >= 1_000_000_000_000:
        return f"{amount / 1_000_000_000_000:.2f} Tỷ VND"
    elif amount >= 1_000_000_000:
        return f"{amount / 1_000_000_000:.2f} Triệu VND"
    else:
        return f"{amount:,.0f} VND"

def format_metric(value, unit=""):
    """Định dạng số lớn"""
    if value >= 1_000_000_000_000:
        return f"{value / 1e12:.2f} T"
    elif value >= 1_000_000_000:
        return f"{value / 1e9:.2f} Tỷ"
    elif value >= 1_000_000:
        return f"{value / 1e6:.2f} Tr"
    return f"{value:,.0f} {unit}"

# --- Giao diện Ứng dụng ---

st.title("🛡️ Dashboard Báo Cáo Kết Luận Thanh Tra")

# Tải file Excel
uploaded_file = st.file_uploader(
    "Tải lên file Excel (.xlsx) đã tổng hợp dữ liệu kết luận thanh tra (Chấp nhận dữ liệu giả định nếu không tải file)", 
    type=["xlsx"]
)

if uploaded_file is not None:
    try:
        # Giả định dữ liệu nằm trong sheet đầu tiên
        df = pd.read_excel(uploaded_file, engine='openpyxl')
        # Tái xử lý dữ liệu để đảm bảo các cột lọc RAW
        df = load_and_preprocess_data()
        df = df.iloc[0:0] # Xóa dữ liệu giả định nếu tải file thật
        st.success("Tải file thành công! Vui lòng làm lại bước xử lý dữ liệu RAW")
        
        # NOTE: Đối với ứng dụng thực tế, bạn cần gọi hàm tiền xử lý dữ liệu RAW ở đây 
        # sau khi đọc file Excel thực sự:
        # df = preprocess_uploaded_df(df)
        
    except Exception as e:
        st.error(f"Lỗi khi đọc file: {e}. Vui lòng kiểm tra định dạng Excel.")
        df = load_and_preprocess_data() # Dùng lại dữ liệu giả định nếu lỗi
else:
    # Dùng dữ liệu giả định nếu chưa có file tải lên
    df = load_and_preprocess_data()
    st.info("Sử dụng dữ liệu giả định. Vui lòng tải file Excel thực tế.")

# Lấy dữ liệu Documents và Overalls (Chỉ lấy hàng đầu tiên)
doc_data = df.iloc[0].to_dict()
df_findings = df.copy()

# --- SIDEBAR: FILTER ---
st.sidebar.header("🔍 Bộ Lọc Phát Hiện (Findings Filter)")

# Tạo danh sách các điều luật duy nhất để lọc
unique_legal_refs = sorted(df_findings['legal_reference_filter'].unique())
selected_refs = st.sidebar.multiselect(
    "Chọn (các) Điều luật/Quy định Vi phạm:",
    options=unique_legal_refs,
    default=[] # Mặc định chọn tất cả
)

# Hiển thị số liệu tổng hợp trong sidebar
st.sidebar.markdown("---")
if selected_refs:
    df_filtered = df_findings[df_findings['legal_reference_filter'].isin(selected_refs)]
    total_quantified = df_filtered['quantified_amount'].sum()
    total_impacted = df_filtered['impacted_accounts'].sum()
    st.sidebar.metric(
        label="💸 Tổng Tiền Bị Ảnh Hưởng (Lọc)",
        value=format_vnd(total_quantified)
    )
    st.sidebar.metric(
        label="👤 Tổng Hồ Sơ Bị Ảnh Hưởng (Lọc)",
        value=f"{total_impacted:,.0f}"
    )
else:
    df_filtered = df_findings.copy()
    st.sidebar.metric(
        label="💸 Tổng Tiền Bị Ảnh Hưởng (Toàn bộ)",
        value=format_vnd(df_filtered['quantified_amount'].sum())
    )
    st.sidebar.metric(
        label="👤 Tổng Hồ Sơ Bị Ảnh Hưởng (Toàn bộ)",
        value=f"{df_filtered['impacted_accounts'].sum():,.0f}"
    )


# --- BỐ CỤC CHÍNH (TABS) ---
tab1, tab2, tab3, tab4 = st.tabs(["📝 Documents", "📊 Overalls", "🚨 Findings", "✅ Actions"])

# ====================================
# TAB 1: DOCUMENTS (Metadata)
# ====================================
with tab1:
    st.header("Báo Cáo Kết Luận Thanh Tra (Metadata)")
    st.markdown("---")

    # Sử dụng st.columns và Markdown để kiểm soát bố cục và đảm bảo text wrap
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.markdown(f"**Mã số kết luận thanh tra (Doc_id):** `{doc_data['doc_id']}`")
        st.markdown(f"**Ngày phát hành (Issue_date):** `{doc_data['issue_date'].strftime('%d/%m/%Y')}`")
        st.markdown(f"**Lĩnh vực (Sector):** `{doc_data['sector']}`")
        st.markdown(f"**Người kiểm soát (Signer_name):** `{doc_data['signer_name']}`")
        st.markdown(f"**Chức vụ (Signer_title):** `{doc_data['signer_title']}`")
        st.markdown(f"**Thời gian bắt đầu (Period_start):** `{doc_data['period_start'].strftime('%d/%m/%Y')}`")
        st.markdown(f"**Thời gian kết thúc (Period_end):** `{doc_data['period_end'].strftime('%d/%m/%Y')}`")

    with col2:
        # Sử dụng st.info cho Title để làm nổi bật và đảm bảo text wrap tốt
        st.markdown("**Title của kết luận thanh tra:**")
        st.info(doc_data['title'])
        
        st.markdown("**Đơn vị phát hành (Issuing_authority):**")
        st.info(doc_data['issuing_authority'])
        
        st.markdown("**Đơn vị được kiểm tra (Inspected_entity_name):**")
        st.info(doc_data['inspected_entity_name'])

# ====================================
# TAB 2: OVERALLS (Metrics)
# ====================================
with tab2:
    st.header("Thông Tin Tổng Quan Về Đơn Vị Được Kiểm Tra")
    st.markdown("---")

    col_staff, col_offices, col_capital, col_loan, col_npl = st.columns(5)

    with col_staff:
        st.metric("Tổng số lượng nhân viên (Staff_total)", f"{doc_data['staff_total']:,.0f}")
        st.metric("Số lượng mẫu kiểm tra (Sample_total_files)", f"{doc_data['sample_total_files']:,.0f}")
    
    with col_offices:
        st.metric("Phòng nghiệp vụ (HQ_count)", f"{doc_data['departments_at_hq_count']:,.0f}")
        st.metric("Phòng giao dịch (Transaction_offices_count)", f"{doc_data['transaction_offices_count']:,.0f}")

    with col_capital:
        st.metric("Tổng số nguồn vốn (Mobilized_capital_vnd)", format_metric(doc_data['mobilized_capital_vnd'], 'VND'))

    with col_loan:
        st.metric("Tổng số dư nợ (Loans_outstanding_vnd)", format_metric(doc_data['loans_outstanding_vnd'], 'VND'))

    with col_npl:
        st.metric("Tổng số nợ xấu (NPL_total_vnd)", format_metric(doc_data['npl_total_vnd'], 'VND'))
        st.metric("Tỷ lệ NPL (%)", f"{doc_data['npl_ratio_percent']:.2f}%")
        st.metric("Tổng tiền kiểm tra (Sample_outstanding_checked_vnd)", format_metric(doc_data['sample_outstanding_checked_vnd'], 'VND'))


# ====================================
# TAB 3: FINDINGS (Phát hiện & Nguyên nhân)
# ====================================
with tab3:
    st.header("Phân Tích Chi Tiết Phát Hiện (Findings)")
    st.subheader(f"Dữ liệu đang được lọc theo: **{', '.join(selected_refs) if selected_refs else 'Tất cả'}**")
    st.markdown("---")

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
    # Thêm chú thích cho RAW
    st.markdown("""
        <div style='background-color: #f0f2f6; padding: 10px; border-radius: 5px; margin-bottom: 10px;'>
            **Chú thích:** *RAW (Chưa xác định)* là nhóm tổng hợp các sai phạm mà điều luật/quy định không được nhắc tới rõ ràng trong file gốc.
        </div>
    """, unsafe_allow_html=True)
    
    st.plotly_chart(fig_line, use_container_width=True)
    st.markdown("---")

    # ------------------
    # 3.3. Bảng Chi tiết và Phân tích Nguyên nhân
    # ------------------
    st.subheader("4. Chi tiết Sai phạm, Nguyên nhân và Kiến nghị")
    
    # Nhóm dữ liệu theo sub_category để hiển thị bảng chi tiết
    sub_categories = df_filtered['sub_category'].unique()

    for sub_cat in sub_categories:
        st.markdown(f"#### 🔎 Lỗi Chi tiết: **{sub_cat}** (Số lần xuất hiện: {len(df_filtered[df_filtered['sub_category'] == sub_cat]):,})")
        
        df_sub_cat = df_filtered[df_filtered['sub_category'] == sub_cat].reset_index(drop=True)
        
        # Bảng hiển thị đầy đủ
        st.dataframe(
            df_sub_cat[[
                'legal_reference_filter', 
                'description', 
                'quantified_amount', 
                'impacted_accounts',
                'root_cause', 
                'recommendation'
            ]].rename(columns={
                'legal_reference_filter': 'Luật Lệ (RAW-X)',
                'description': 'Mô tả Sai phạm',
                'quantified_amount': 'Số tiền Ảnh hưởng (VND)',
                'impacted_accounts': 'Số KH/Hồ sơ Ảnh hưởng',
                'root_cause': 'Nguyên nhân Gốc',
                'recommendation': 'Kiến nghị Thay đổi'
            }).style.format({
                'Số tiền Ảnh hưởng (VND)': lambda x: f"{x:,.0f}"
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
    st.subheader(f"Dữ liệu Hành động đang được lọc theo: **{', '.join(selected_refs) if selected_refs else 'Tất cả'}**")
    st.markdown("---")
    
    # ------------------
    # 4.1. Biểu đồ Phân loại Hành động
    # ------------------
    st.subheader("1. Phân loại Tính chất của Biện pháp Cải tạo (Action Type)")
    df_action_count = df_filtered['action_type'].value_counts().reset_index()
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
    
    # Bảng chi tiết
    st.dataframe(
        df_filtered[[
            'legal_reference_filter',
            'action_type',
            'action_description', 
            'evidence_of_completion',
        ]].rename(columns={
            'legal_reference_filter': 'Luật Lệ Liên quan (RAW-X)',
            'action_type': 'Tính chất Biện pháp',
            'action_description': 'Nội dung Công việc Cần làm',
            'evidence_of_completion': 'Minh chứng Hoàn thành'
        }),
        use_container_width=True,
        height=500
    )

    # Hiển thị ghi chú về RAW
    st.markdown("""
        <div style='text-align: right; margin-top: 15px; font-style: italic; color: #555;'>
            *Dữ liệu đang hiển thị theo bộ lọc Điều luật/Quy định đã chọn ở sidebar.*
        </div>
    """, unsafe_allow_html=True)
