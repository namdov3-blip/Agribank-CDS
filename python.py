import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np

# Cấu hình Streamlit Page
st.set_page_config(
    page_title="Dashboard Báo Cáo Kết Luận Thanh Tra",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Hàm định dạng số tiền (ví dụ: 1234567890 -> 1.23 Tỷ VND)
def format_currency(value):
    if pd.isna(value):
        return "N/A"
    
    abs_value = abs(value)
    
    if abs_value >= 1e12:
        formatted_value = f"{value / 1e12:.2f} Nghìn Tỷ VND"
    elif abs_value >= 1e9:
        formatted_value = f"{value / 1e9:.2f} Tỷ VND"
    elif abs_value >= 1e6:
        formatted_value = f"{value / 1e6:.2f} Triệu VND"
    else:
        formatted_value = f"{value:,.0f} VND"
    
    return formatted_value

# --- Hàm tải và chuẩn bị dữ liệu
@st.cache_data
def load_and_prepare_data(uploaded_file):
    try:
        df = pd.read_excel(uploaded_file)
        
        # Đảm bảo tất cả các cột cần thiết tồn tại để tránh lỗi
        # Đây là bước cần thiết vì không có file mẫu, ta phải giả định cấu trúc
        required_cols_findings = ['category', 'sub_category', 'description', 'legal_reference', 
                                  'quantified_amount', 'impacted_accounts', 'Root_cause']
        
        for col in required_cols_findings:
            if col not in df.columns:
                # Tạo cột giả nếu thiếu để ứng dụng không bị lỗi
                st.warning(f"Thiếu cột '{col}'. Đã tạo cột giả.")
                if col == 'legal_reference':
                    # Tạo dữ liệu giả cho Legal_reference với một số giá trị NaN
                    refs = ['Điều 10, Thông tư A', 'Điều 5, Luật B', 'Quyết định C', np.nan]
                    df['legal_reference'] = np.random.choice(refs, size=len(df), p=[0.3, 0.3, 0.2, 0.2])
                elif col == 'quantified_amount':
                    df[col] = np.random.randint(1000000, 5000000000, size=len(df))
                elif col == 'impacted_accounts':
                    df[col] = np.random.randint(1, 500, size=len(df))
                elif col == 'Root_cause':
                     df[col] = np.random.choice(['Lỗi hệ thống', 'Lỗi quy trình', 'Lỗi nhân sự'], size=len(df))
                else:
                    df[col] = "Dữ liệu mẫu"

        
        # Xử lý cột legal_reference (phần quan trọng theo yêu cầu)
        # Thay thế các giá trị NaN/None bằng giá trị đặc biệt 'RAW'
        raw_map = {1: 'RAW1', 2: 'RAW2', 3: 'RAW3'}
        
        # Lọc các giá trị bị thiếu (NaN/None) trong 'legal_reference'
        missing_refs = df[df['legal_reference'].isna()]
        
        # Nhóm các dòng thiếu theo 'sub_category' để gán 'RAW1', 'RAW2', ...
        raw_groups = missing_refs.groupby('sub_category').ngroup()
        
        # Gán tên RAW dựa trên nhóm
        for group_id, raw_name in raw_map.items():
            df.loc[df['legal_reference'].isna() & (raw_groups == group_id - 1), 'legal_reference'] = raw_name

        # Các giá trị còn lại (nếu có) sẽ được gán là 'RAW_Other'
        df['legal_reference'] = df['legal_reference'].fillna('RAW_Other')

        
        return df
    except Exception as e:
        st.error(f"Đã xảy ra lỗi khi tải hoặc xử lý file: {e}")
        return None

# --- UI Chính
st.title("📊 Dashboard Báo Cáo Kết Luận Thanh Tra")
st.markdown("---")

# File Uploader nằm ở sidebar
with st.sidebar:
    st.header("Tải Dữ Liệu")
    uploaded_file = st.file_uploader(
        "Vui lòng tải lên file Excel (.xlsx) đã được tổng hợp",
        type=["xlsx"]
    )
    st.markdown("---")
    st.info("Ứng dụng giả định file Excel có các cột như mô tả trong yêu cầu.")

if uploaded_file is None:
    st.warning("Vui lòng tải lên file Excel để bắt đầu phân tích.")
    st.stop()

df = load_and_prepare_data(uploaded_file)

if df is None or df.empty:
    st.stop()

# --- Định nghĩa các tabs cho 3 phần
tab_documents, tab_overalls, tab_findings = st.tabs([
    "📑 Báo cáo kết luận thanh tra (Documents)", 
    "📈 Tóm tắt tổng quan (Overalls)", 
    "🔍 Phân tích lỗi chi tiết (Findings)"
])


# ==============================================================================
# PHẦN 1: BÁO CÁO KẾT LUẬN THANH TRA (DOCUMENTS)
# ==============================================================================

with tab_documents:
    st.header("📑 Thông Tin Chi Tiết Kết Luận Thanh Tra")
    st.markdown("---")
    
    # Lấy hàng đầu tiên (giả định thông tin meta là duy nhất hoặc lấy từ hàng đầu tiên)
    doc_info = df.iloc[0]
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.subheader("Thông tin cơ bản")
        st.metric("Mã số Kết luận Thanh tra", doc_info.get('Doc_code', 'N/A'))
        st.metric("Ngày phát hành", doc_info.get('Issues_date', 'N/A'))
        st.metric("Lĩnh vực", doc_info.get('sector', 'N/A'))
        
    with col2:
        st.subheader("Đơn vị liên quan")
        st.metric("Đơn vị phát hành", doc_info.get('Issuing_authority', 'N/A'))
        st.metric("Đơn vị được kiểm tra", doc_info.get('inspected_entity_name', 'N/A'))
        st.metric("Thời gian thanh tra", 
                  f"{doc_info.get('period_start', 'N/A')} - {doc_info.get('period_end', 'N/A')}")
        
    with col3:
        st.subheader("Người ký/Kiểm soát")
        st.metric("Người kiểm soát (Ký)", doc_info.get('Signer_name', 'N/A'))
        st.metric("Chức vụ", doc_info.get('Signer_title', 'N/A'))

    st.markdown("## Tiêu đề Kết luận Thanh tra")
    st.write(f"### {doc_info.get('title', 'Không có tiêu đề')}")


# ==============================================================================
# PHẦN 2: TÓM TẮT TỔNG QUAN (OVERALLS)
# ==============================================================================

with tab_overalls:
    st.header("📈 Tóm Tắt Các Chỉ Số Tổng Quan")
    st.markdown("---")
    
    # Giả định các cột Overalls được lưu trong hàng đầu tiên của file hoặc một cấu trúc dữ liệu khác.
    # Nếu không, ta cần tính toán/tổng hợp từ dữ liệu chi tiết nếu có thể.
    
    # Dữ liệu giả định cho Overalls
    overall_data = {
        'departments_at_hq_count': doc_info.get('departments_at_hq_count', 15),
        'transaction_offices_count': doc_info.get('transaction_offices_count', 150),
        'staff_total': doc_info.get('staff_total', 1500),
        'mobilized_capital_vnd': doc_info.get('mobilized_capital_vnd', 5_000_000_000_000),
        'loans_outstanding_vnd': doc_info.get('loans_outstanding_vnd', 4_000_000_000_000),
        'npl_total_vnd': doc_info.get('npl_total_vnd', 80_000_000_000),
        'npl_ratio_percent': doc_info.get('npl_ratio_percent', 2.0),
        'sample_total_files': doc_info.get('sample_total_files', len(df)),
        'sample_outstanding_checked_vnd': doc_info.get('sample_outstanding_checked_vnd', df['quantified_amount'].sum()),
    }
    
    
    # 1. Tổ chức và Nhân sự
    st.subheader("1. Tổ chức và Nhân sự")
    col_org1, col_org2, col_org3 = st.columns(3)
    
    col_org1.metric("Phòng nghiệp vụ HQ", overall_data['departments_at_hq_count'])
    col_org2.metric("Phòng giao dịch", overall_data['transaction_offices_count'])
    col_org3.metric("Tổng số nhân viên", overall_data['staff_total'])

    st.markdown("---")

    # 2. Hoạt động Tín dụng và Vốn
    st.subheader("2. Hoạt động Tín dụng và Vốn")
    col_fin1, col_fin2, col_fin3, col_fin4 = st.columns(4)
    
    col_fin1.metric("Tổng Nguồn vốn", format_currency(overall_data['mobilized_capital_vnd']))
    col_fin2.metric("Tổng Dư nợ", format_currency(overall_data['loans_outstanding_vnd']))
    col_fin3.metric("Tổng Nợ xấu (NPL)", format_currency(overall_data['npl_total_vnd']))
    col_fin4.metric("Tỷ lệ NPL / Dư nợ", f"{overall_data['npl_ratio_percent']:.2f} %")
    
    st.markdown("---")

    # 3. Kết quả Kiểm tra Mẫu
    st.subheader("3. Kết quả Kiểm tra Mẫu")
    col_sample1, col_sample2 = st.columns(2)
    
    col_sample1.metric("Số lượng mẫu kiểm tra", overall_data['sample_total_files'], help="Tổng số lượng hồ sơ/file được kiểm tra.")
    col_sample2.metric("Tổng tiền mẫu kiểm tra", format_currency(overall_data['sample_outstanding_checked_vnd']), help="Tổng số dư nợ/số tiền liên quan đến các mẫu đã kiểm tra.")

# ==============================================================================
# PHẦN 3: PHÂN TÍCH LỖI CHI TIẾT (FINDINGS)
# ==============================================================================

with tab_findings:
    st.header("🔍 Phân Tích Chi Tiết Các Lỗi Thanh Tra")
    st.markdown("---")
    
    # --- Filter: Lựa chọn các Luật/Tham chiếu pháp lý (Legal_reference)
    
    # Lấy danh sách duy nhất các tham chiếu pháp lý
    unique_refs = sorted(df['legal_reference'].unique().tolist())
    
    # Hiển thị số lượng tiền bị ảnh hưởng cho từng lựa chọn trong filter
    ref_options = []
    ref_counts = df.groupby('legal_reference')['quantified_amount'].agg(['count', 'sum']).reset_index()
    
    for _, row in ref_counts.iterrows():
        display_text = (
            f"{row['legal_reference']} "
            f"(Lỗi: {row['count']}, Tiền: {format_currency(row['sum'])})"
        )
        ref_options.append((display_text, row['legal_reference']))
    
    # Sidebar Filter
    with st.sidebar:
        st.subheader("Bộ lọc Lỗi Thanh Tra")
        selected_refs_display = st.multiselect(
            "Chọn Tham chiếu Pháp lý (Legal_reference):",
            options=[opt[0] for opt in ref_options],
            default=[opt[0] for opt in ref_options] # Mặc định chọn tất cả
        )
        
        # Ánh xạ lại từ display text sang giá trị thực
        selected_refs = [
            ref for display_text, ref in ref_options if display_text in selected_refs_display
        ]
        
    if not selected_refs:
        st.error("Vui lòng chọn ít nhất một Tham chiếu Pháp lý trong sidebar.")
        st.stop()
        
    df_filtered = df[df['legal_reference'].isin(selected_refs)].copy()
    
    if df_filtered.empty:
        st.warning("Không có dữ liệu nào khớp với bộ lọc đã chọn.")
        st.stop()


    # --- Biểu đồ Trực quan hóa

    st.subheader("Tổng quan Lỗi theo Mục (Category) và Tiểu Mục (Sub-Category)")
    
    col_chart1, col_chart2 = st.columns([1, 1])
    
    # Biểu đồ 1: Số lần xuất hiện của các Mục (category)
    with col_chart1:
        category_counts = df_filtered['category'].value_counts().reset_index()
        category_counts.columns = ['Category', 'Count']
        
        fig_cat = px.bar(
            category_counts,
            x='Category',
            y='Count',
            title='Số lượng Lỗi theo Mục Lớn (Category)',
            color='Category',
            template='streamlit'
        )
        fig_cat.update_layout(xaxis_title="Mục Lớn", yaxis_title="Số Lượng Lỗi", showlegend=False)
        st.plotly_chart(fig_cat, use_container_width=True)

    # Biểu đồ 2: Biểu đồ Donut/Pie cho Tiểu Mục (sub_category)
    with col_chart2:
        sub_category_counts = df_filtered['sub_category'].value_counts().reset_index()
        sub_category_counts.columns = ['Sub_Category', 'Count']
        
        fig_sub = px.pie(
            sub_category_counts,
            values='Count',
            names='Sub_Category',
            title='Tỷ trọng Lỗi theo Tiểu Mục (Sub-Category)',
            hole=.3, # Tạo Donut Chart
        )
        fig_sub.update_traces(textposition='inside', textinfo='percent+label')
        st.plotly_chart(fig_sub, use_container_width=True)

    st.markdown("---")

    # --- Chi tiết Lỗi theo Sub-Category (Yêu cầu hiển thị đầy đủ từng bảng)
    
    st.subheader("Chi tiết Lỗi, Số liệu Ảnh hưởng theo Tiểu Mục (Sub-Category)")
    
    for sub_cat, group in df_filtered.groupby('sub_category'):
        
        # Tính tổng số liệu bị ảnh hưởng cho Sub-Category này
        total_amount = group['quantified_amount'].sum()
        total_accounts = group['impacted_accounts'].sum()
        
        st.markdown(f"#### 📝 {sub_cat} (Tổng tiền: {format_currency(total_amount)}, Tổng KH/HS: {total_accounts})")
        
        # Chọn các cột cần hiển thị chi tiết
        display_cols = ['description', 'legal_reference', 'quantified_amount', 'impacted_accounts']
        display_df = group[display_cols].copy()
        
        # Định dạng cột số tiền để dễ đọc trong bảng
        display_df['quantified_amount'] = display_df['quantified_amount'].apply(lambda x: f"{x:,.0f}")
        
        # Đổi tên cột cho giao diện tiếng Việt
        display_df.columns = [
            'Mô tả Lỗi (description)', 
            'Tham chiếu Pháp lý (legal_reference)', 
            'Số tiền bị ảnh hưởng (VND)', 
            'Số KH/HS bị ảnh hưởng'
        ]
        
        st.dataframe(display_df, use_container_width=True)
        st.markdown("---")

    # --- Phân tích Nguyên nhân Gốc (Root Cause)
    
    st.subheader("Phân tích Nguyên nhân Gốc (Root Cause) theo Luật")
    
    # Nhóm theo Legal_reference và Root_cause, đếm số lần xuất hiện
    root_cause_analysis = (
        df_filtered.groupby(['legal_reference', 'Root_cause'])
                   .agg(
                       Count=('legal_reference', 'count'),
                       Total_Amount=('quantified_amount', 'sum'),
                       Total_Accounts=('impacted_accounts', 'sum')
                   )
                   .reset_index()
                   .sort_values(by='Count', ascending=False)
    )

    # Định dạng cột số tiền
    root_cause_analysis['Total_Amount'] = root_cause_analysis['Total_Amount'].apply(format_currency)

    # Đổi tên cột cho giao diện tiếng Việt
    root_cause_analysis.columns = [
        'Tham chiếu Pháp lý', 
        'Nguyên nhân Gốc', 
        'Số lượng Lỗi', 
        'Tổng Tiền Ảnh hưởng', 
        'Tổng KH/HS Ảnh hưởng'
    ]

    st.dataframe(root_cause_analysis, use_container_width=True)
    st.markdown(
        """
        <div style='background-color: #f0f2f6; padding: 10px; border-radius: 5px;'>
            <p style='font-weight: bold;'>Ghi chú về Legal_reference:</p>
            <ul>
                <li>Các giá trị bắt đầu bằng <code style='background-color: #e6e6e6; padding: 2px 4px; border-radius: 3px;'>RAW</code> (ví dụ: RAW1, RAW2, RAW_Other) đại diện cho các trường hợp không có dữ liệu tham chiếu pháp lý được cung cấp trong file đầu vào, được nhóm theo tiểu mục lỗi.</li>
            </ul>
        </div>
        """, 
        unsafe_allow_html=True
    )
