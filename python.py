# python.py
# Streamlit app: Dashboard trực quan hóa Kết luận Thanh tra (KLTT)
# Chạy: streamlit run python.py
# Yêu cầu: pip install streamlit pandas altair openpyxl plotly requests google-genai

import io
import numpy as np
import pandas as pd
import streamlit as st
import altair as alt
import plotly.express as px
import requests # THƯ VIỆN ĐỂ GỌI n8n Webhook
from google import genai
from google.genai.errors import APIError
import time

st.set_page_config(
    page_title="Ngân Hàng Nhà Nước Việt Nam",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Gemini Client Initialization (ĐÃ SỬA LỖI: Thêm khởi tạo client) ---
gemini_client = None
if "GEMINI_API_KEY" in st.secrets:
    try:
        # Khởi tạo Gemini Client
        gemini_client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
    except Exception as e:
        st.sidebar.error(f"Lỗi khởi tạo Gemini Client: Vui lòng kiểm tra GEMINI_API_KEY. Chi tiết: {e}")
# ------------------------------------------------------------------------


# ==============================
# Helpers (ĐÃ SỬA ĐỔI ĐƠN VỊ TIỀN TỆ)
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
    s = series.copy().astype(str)
    null_mask = s.isna() | s.str.strip().eq("") | s.str.lower().eq("nan")
    if null_mask.any():
        raw_index = np.cumsum(null_mask).where(null_mask, 0)
        s.loc[null_mask] = [f"{prefix}{i}" for i in raw_index[null_mask].astype(int)]
    return s

def to_number(x):
    if pd.isna(x): return np.nan
    if isinstance(x, (int, float, np.number)): return float(x)
    try:
        return float(str(x).replace(",", "").replace(" ", ""))
    except:
        digits = "".join(ch for ch in str(x) if (ch.isdigit() or ch=='.' or ch=='-'))
        try: return float(digits)
        except: return np.nan

# --- HÀM MỚI: CHUYỂN ĐỔI SANG TRIỆU ĐỒNG VÀ GIỮ NGUỒN SỐ TỪ EXCEL ---
def to_million_vnd(series: pd.Series):
    """
    Áp dụng to_number để chuyển đổi, sau đó chia cho 1,000,000.
    Mục đích: Giữ nguyên giá trị số từ file Excel (đơn vị gốc thường là VND),
    sau đó hiển thị dưới đơn vị triệu đồng.
    """
    return series.apply(to_number) / 1_000_000

def safe_date(series: pd.Series):
    try: return pd.to_datetime(series, errors="coerce")
    except Exception: return pd.to_datetime(pd.Series([None]*len(series)), errors="coerce")

def format_vnd(n):
    """Định dạng giá trị đã được chia cho 1,000,000 (triệu đồng)."""
    if pd.isna(n): return "—"
    n = float(n)
    # Các giá trị đã là TRIỆU ĐỒNG.
    if abs(n) >= 1_000_000: return f"{n/1_000_000:,.2f} nghìn tỷ ₫" # Đã là triệu đồng, chia tiếp cho 1tr ra nghìn tỷ (10^12)
    if abs(n) >= 1_000: return f"{n/1_000:,.2f} tỷ ₫" # Đã là triệu đồng, chia tiếp cho 1k ra tỷ (10^9)
    return f"{n:,.0f} triệu ₫"

# ===== Plot helpers for Overalls (ĐÃ SỬA ĐỔI) =====
PALETTE = ["#1f6feb", "#16a34a", "#f59e0b", "#ef4444", "#0ea5e9", "#a855f7", "#22c55e", "#a50000", "#6b7280"]

def _format_vnd_text(v):
    """Định dạng nhãn trên biểu đồ, giá trị là TRIỆU ĐỒNG."""
    if pd.isna(v): return "—"
    try:
        v = float(v)
    except:
        return "—"
    if abs(v) < 0.5:
        return "0 triệu ₫"
    # Các giá trị đã là TRIỆU ĐỒNG.
    if abs(v) >= 1_000_000: return f"{v/1_000_000:,.2f} nghìn tỷ"
    if abs(v) >= 1_000: return f"{v/1_000:,.2f} tỷ"
    return f"{v:,.0f} triệu ₫"

def make_bar(df_in, x_col="Chỉ tiêu", y_col="Giá trị", title="", height=260):
    """Bar chart gọn: mỗi cột 1 màu; nhãn in đậm & đổi màu; hiển thị số 0."""
    d = df_in.copy()
    n = len(d)
    colors = PALETTE[:max(1, n)]
    fig = px.bar(
        d, x=x_col, y=y_col,
        text=d[y_col].apply(_format_vnd_text), # Áp dụng định dạng tiền tệ mới
        color=x_col, color_discrete_sequence=colors,
        title=title
    )
    fig.update_traces(
        textposition="outside",
        texttemplate="<b>%{text}</b>",
        marker_line_color="white",
        marker_line_width=0.5,
        textfont=dict(color="#70573e", size=12) # Màu chữ tương ứng với màu chủ đạo
    )
    fig.update_layout(
        height=height, bargap=0.40,
        yaxis_title="Triệu VND", xaxis_title="", legend_title_text="", # Đổi nhãn trục Y
        margin=dict(l=10, r=10, t=60, b=10)
    )
    return fig

def make_pie(labels_vals, title="", height=260):
    d = pd.DataFrame(labels_vals, columns=["Nhóm", "Giá trị"])
    d["Giá trị"] = d["Giá trị"].apply(lambda x: 0 if pd.isna(x) else float(x))
    fig = px.pie(
        d, names="Nhóm", values="Giá trị", hole=.35,
        color="Nhóm", color_discrete_sequence=PALETTE,
        title=title
    )
    fig.update_traces(textinfo="percent+label", textfont=dict(size=12), pull=[0.02]*len(d))
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=60, b=10))
    return fig

# ==============================
# Theme + CSS (ĐÃ SỬA ĐỔI CHO UX/UI NHNN)
# ==============================

st.markdown("""
<style>
:root { 
    --primary-color: #70573e; /* Màu Nâu Vàng từ logo (Chủ đạo) */
    --background-light: #fafaf4; /* Nền kem nhẹ */
}
/* Áp dụng nền kem cho toàn bộ trang */
[data-testid="stAppViewContainer"] {
    background-color: var(--background-light);
}
/* Tiêu đề tổng quát */
h1, h2, h3, h4 {
    color: var(--primary-color);
}
h1 {
    font-size: 2.2rem;
    font-weight: 700;
}
h2 {
    font-size: 1.8rem;
    border-bottom: 2px solid #e6e6e6; /* Đường phân cách nhẹ */
    padding-bottom: 5px;
    margin-top: 1.5rem;
}
/* Thanh phân cách */
hr {
    border-top: 1.8px solid var(--primary-color); /* Màu xanh chủ đạo */
}

/* Dataframe */
[data-testid="stDataFrame"] td, [data-testid="stDataFrame"] th {
    white-space: pre-wrap !important;
    word-break: break-word !important;
}

/* Info Card */
.info-card{
  position: relative;
  display: block;
  padding: 16px 18px 14px 18px; /* đủ thoáng */
  background: #fff;
  border: 3px solid var(--border-color);   /* viền bao quanh */
  border-left: 8px solid var(--primary-color); /* điểm nhấn màu chủ đạo */
  border-radius: 16px;
  min-height: 72px;
  margin-bottom: 12px;
  box-shadow: 0 1px 0 rgba(0,0,0,.02);
}
.info-card .label { 
    font-size: 17px; 
    color: var(--primary-color); 
    font-weight: 700; 
    margin-bottom: 10px; 
}
.info-card .value { 
    font-size: 19px; 
    line-height: 1.3; 
    white-space: pre-wrap; 
    word-break: break-word; 
    font-weight: 600;
}

/* Document Wrap */
.doc-wrap { 
    padding: 15px; 
    border: 1px solid var(--primary-color); 
    border-radius: 12px; 
    background: #fff0f0; /* Nền rất nhạt */
    margin-bottom: 14px; 
}
.doc-title { 
    font-weight: 700; 
    font-size: 18px; 
    color: var(--primary-color);
    margin-bottom: 10px; 
}

/* Căn giữa vùng nội dung chính của dashboard */
.block-container {
    max-width: 1200px;      /* bạn có thể tăng/giảm 1100–1400 */
    margin: 0 auto !important;
}

/* ===== TABS: căn giữa + cỡ chữ to + nhấn trạng thái chọn ===== */

/* Container của tabs */
[data-testid="stTabs"] {
    display: flex;
    justify-content: center;          /* căn giữa toàn bộ thanh tab */
}

/* Dàn các tab nằm giữa, khoảng cách vừa phải và co giãn tốt trên mọi màn hình */
[data-testid="stTabs"] > div {
    display: flex;
    justify-content: center !important;
    gap: 24px;                         /* thay vì 500px gây vỡ layout */
    flex-wrap: wrap;                   /* xuống dòng đẹp trên màn hình hẹp */
    width: 100%;
    max-width: 1200px;                 /* đồng bộ với .block-container */
    margin: 0 auto;
}

/* Nút tab: chữ to, đậm, padding lớn hơn để dễ bấm */
button[data-testid^="stTab"] {
    font-size: 24px;
    font-weight: var(--tab-font-weight) !important;
    padding: 10px 22px !important;
    border-radius: 12px !important;
    transition: all .15s ease-in-out;
    color: #2b2b2b;
    background: transparent;
    border: none;
}

/* Hover: đổi màu chữ nhẹ và thêm nền mờ */
button[data-testid^="stTab"]:hover {
    color: var(--primary-color) !important;
    background: rgba(112, 87, 62, 0.08) !important;
}

/* Tab đang được chọn: tô màu chủ đạo + gạch chân dày và bóng đổ nhẹ */
button[data-testid^="stTab"][aria-selected="true"] {
    color: var(--primary-color) !important;
    position: relative;
    font-weight: 800 !important;
}
button[data-testid^="stTab"][aria-selected="true"]::after {
    content: "";
    position: absolute;
    left: 16px; right: 16px; bottom: -6px;
    height: 4px;
    background: var(--primary-color);
    border-radius: 999px;
    box-shadow: 0 2px 6px rgba(112,87,62,.25);
}

/* Thu gọn khoảng cách dọc trên/dưới thanh tab để cân đối với header */
[data-testid="stTabs"] { margin-top: 4px; margin-bottom: 8px; }
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
# RAG CHATBOT LOGIC (ĐÃ THÊM KEY CHO BUTTON)
# ==============================

def call_n8n_chatbot(prompt: str):
    """Gửi câu hỏi tới n8n RAG Webhook và nhận câu trả lời. Bao gồm logic Chat ID."""
    if "N8N_WEBHOOK_URL" not in st.secrets:
        return "Lỗi cấu hình: Thiếu N8N_WEBHOOK_URL trong secrets.toml. Vui lòng thiết lập để sử dụng chatbot."
    
    webhook_url = st.secrets["N8N_WEBHOOK_URL"]
    
    # Logic tạo/lấy Chat ID để n8n quản lý bộ nhớ (Simple Memory)
    if "chat_session_id" not in st.session_state:
        # Tạo ID duy nhất dựa trên timestamp
        st.session_state.chat_session_id = pd.Timestamp.now().strftime("%Y%m%d%H%M%S%f")

    payload = {
        "query": prompt,
        "chatId": st.session_state.chat_session_id # Truyền Chat ID
    }
    
    try:
        # Tăng timeout lên 90s để tránh lỗi hết thời gian chờ
        response = requests.post(webhook_url, json=payload, timeout=90)
        response.raise_for_status()
        data = response.json()
        
        return data.get("response", "Không tìm thấy trường 'response' trong phản hồi của n8n. Vui lòng kiểm tra lại cấu hình n8n.")

    except requests.exceptions.Timeout:
        return "RAG Chatbot (n8n) hết thời gian chờ (Timeout: 90s). Vui lòng thử lại hoặc rút gọn câu hỏi."
    except requests.exceptions.RequestException as e:
        return f"Lỗi kết nối tới n8n: {e}. Vui lòng kiểm tra URL Webhook và trạng thái n8n."
    except Exception as e:
        return f"Lỗi xử lý phản hồi từ n8n: {e}"

def reset_rag_chat_session():
    """Hàm này sẽ reset toàn bộ lịch sử chat và session ID."""
    st.session_state.rag_chat_history = []
    if "rag_chat_counter" in st.session_state:
        st.session_state.rag_chat_counter = 0
    if "chat_session_id" in st.session_state:
        del st.session_state.chat_session_id
    st.session_state.rag_chat_history.append(
        {"role": "assistant", "content": "Phiên trò chuyện đã được **reset** thành công. Chào bạn, tôi là Trợ lý RAG được kết nối qua n8n. Hãy hỏi tôi về các thông tin KLTT."}
    )
    st.rerun()

def rag_chat_tab():
    """Thêm khung chat RAG kết nối qua n8n Webhook vào tab."""
    st.header("Internal RAG")
    st.write("Sử dụng RAG Bot để hỏi đáp về dữ liệu KLTT")
    if st.button("Bắt đầu phiên Chat mới", type="primary", key="rag_reset_button"):
        reset_rag_chat_session()
        return

    if "rag_chat_history" not in st.session_state:
        st.session_state.rag_chat_history = []
        st.session_state.rag_chat_counter = 0
        st.session_state.rag_chat_history.append(
            {"role": "assistant", "content": "Chào bạn, tôi là Trợ lý RAG được kết nối qua n8n. Hãy hỏi tôi về các thông tin KLTT."}
        )
    current_count = st.session_state.get("rag_chat_counter", 0)
    st.caption(f"Phiên chat hiện tại: **{current_count}** / 5 câu. (Hỏi 5 câu sẽ tự động reset)")
    st.markdown("---")

    if "N8N_WEBHOOK_URL" not in st.secrets:
        st.warning("Vui lòng thiết lập N8N_WEBHOOK_URL trong file .streamlit/secrets.toml để sử dụng Chatbot.")
        return

    for message in st.session_state.rag_chat_history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if user_prompt := st.chat_input("Hỏi Trợ lý RAG...", key="rag_chat_input"):
        if st.session_state.rag_chat_counter >= 5:
            with st.chat_message("assistant"):
                st.info("Phiên trò chuyện đã đạt 5 câu hỏi. **Lịch sử sẽ được xóa.** Vui lòng bắt đầu câu hỏi mới.")
            reset_rag_chat_session()
            return

        st.session_state.rag_chat_history.append({"role": "user", "content": user_prompt})
        with st.chat_message("user"):
            st.markdown(user_prompt)

        with st.chat_message("assistant"):
            with st.spinner("RAG Chatbot (n8n) đang xử lý..."):
                response_text = call_n8n_chatbot(user_prompt)
                st.markdown(response_text)
                st.session_state.rag_chat_history.append({"role": "assistant", "content": response_text})
                st.session_state.rag_chat_counter += 1

# ==============================
# GEMINI CHATBOT LOGIC (ĐÃ THÊM KEY CHO BUTTON)
# ==============================
def reset_gemini_chat_session():
    """Hàm này sẽ reset toàn bộ lịch sử chat và session ID."""
    st.session_state["chat_messages"] = [
        {"role": "assistant", "content": "Phiên trò chuyện đã được **reset** thành công. Xin chào! Tôi là Gemini. Bạn có câu hỏi nào muốn tôi giải đáp không?"}
    ]
    st.session_state["gemini_chat_counter"] = 0
    st.rerun()

def gemini_chat_tab(client: genai.Client):
    """Thêm khung chat Gemini kết nối qua API."""
    st.header("External Gemini")
    st.write("Sử dụng Gemini để hỏi đáp về mọi chủ đề (tài chính, lập trình, kiến thức chung,...)")
    
    # --- LOGIC RESET ---
    if st.button("Bắt đầu phiên Chat mới", type="primary", key="gemini_reset_button"):
        reset_gemini_chat_session()
        return
    
    if not client:
        st.warning("Vui lòng cấu hình Khóa 'GEMINI_API_KEY' trong Streamlit Secrets để sử dụng tính năng chat.")
        return # Dừng luồng nếu không có client
    
    # Thiết lập lịch sử trò chuyện & biến đếm
    if "chat_messages" not in st.session_state:
        st.session_state["chat_messages"] = [
            {"role": "assistant", "content": "Xin chào! Tôi là Gemini. Bạn có câu hỏi nào muốn tôi giải đáp không?"}
        ]
        st.session_state["gemini_chat_counter"] = 0 # Khởi tạo biến đếm
        
    current_count = st.session_state.get("gemini_chat_counter", 0)
    st.caption(f"Phiên chat hiện tại: **{current_count}** / 5 câu. (Hỏi 5 câu sẽ tự động reset)")
    st.markdown("---")
    # -------------------

    # Hiển thị lịch sử trò chuyện
    for message in st.session_state["chat_messages"]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Lấy đầu vào từ người dùng
    if prompt := st.chat_input("Nhập câu hỏi của bạn...", key="gemini_chat_input"):
        
        # --- LOGIC KIỂM TRA GIỚI HẠN ---
        if st.session_state.get("gemini_chat_counter", 0) >= 5:
            with st.chat_message("assistant"):
                st.info("Phiên trò chuyện đã đạt 5 câu hỏi. **Lịch sử sẽ được xóa.** Vui lòng bắt đầu câu hỏi mới.")
            reset_gemini_chat_session()
            return
        # -------------------------------

        # 1. Thêm tin nhắn của người dùng vào lịch sử
        st.session_state.chat_messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # 2. Tạo nội dung cho API
        history_for_api = []
        for m in st.session_state.chat_messages:
            api_role = "model" if m["role"] == "assistant" else m["role"]
            history_for_api.append({"role": api_role, "parts": [{"text": m["content"]}]})
        
        # 3. Gọi API và hiển thị phản hồi
        with st.chat_message("assistant"):
            with st.spinner("Đang gửi và chờ Gemini trả lời..."):
                
                ai_response = "Lỗi: Không nhận được phản hồi."
                for i in range(3):
                    try:
                        response = client.models.generate_content( 
                            model='gemini-2.5-flash',
                            contents=history_for_api
                        )
                        ai_response = response.text
                        break
                    except APIError as e:
                        ai_response = f"Lỗi gọi API ({e.args[0]}): Vui lòng kiểm tra API key hoặc giới hạn sử dụng."
                        if i < 2:
                            time.sleep(2 ** i)
                            continue
                        break
                    except Exception as e:
                        ai_response = f"Đã xảy ra lỗi không xác định: {e}"
                        break

            st.markdown(ai_response)
        
        # 4. Thêm tin nhắn của AI vào lịch sử và TĂNG BIẾN ĐẾM
        st.session_state.chat_messages.append({"role": "assistant", "content": ai_response})
        st.session_state["gemini_chat_counter"] += 1 # Tăng biến đếm
# =================================================================


# ==============================
# Column mappings (GIỮ NGUYÊN)
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

        # Bổ sung theo yêu cầu phần biểu đồ
        "structure_quality_group1_vnd": ["structure_quality_group1_vnd"],
        "structure_quality_group2_vnd": ["structure_quality_group2_vnd"],
        "structure_quality_group3_vnd": ["structure_quality_group3_vnd"],

        "structure_term_short_vnd": ["structure_term_short_vnd"],
        "structure_term_medium_long_vnd": ["structure_term_medium_long_vnd"],

        "structure_currency_vnd_vnd": ["structure_currency_vnd_vnd"],
        "structure_currency_fx_vnd": ["structure_currency_fx_vnd"],

        "structure_purpose_bds_flexible_vnd": ["structure_purpose_bds_flexible_vnd"],
        "strucuture_purpose_securities_vnd": ["strucuture_purpose_securities_vnd"],
        "structure_purpose_consumption_vnd": ["structure_purpose_consumption_vnd"],
        "structure_purpose_trade_vnd": ["structure_purpose_trade_vnd"],
        "structure_purpose_other_vnd": ["structure_purpose_other_vnd"],
        "structure_econ_state_vnd": ["strucuture_econ_state_vnd"], 
        "structure_econ_nonstate_enterprises_vnd": ["structure_econ_nonstate_enterprises_vnd"], 
        "structure_econ_individuals_households_vnd": ["structure_econ_individuals_households_vnd"], 
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
# Sidebar (Upload + Filters) (ĐÃ THÊM LOGO VÀ TIÊU ĐỀ)
# ==============================

with st.sidebar:

    st.header("📤 Tải dữ liệu")
    uploaded = st.file_uploader("Excel (.xlsx): documents, overalls, findings, actions", type=["xlsx"])
    st.caption("Tên sheet & cột không phân biệt hoa/thường.")

# ==============================
# HEADER CHÍNH (ĐÃ THIẾT KẾ LẠI)
# ==============================

col_logo, col_title, col_spacer = st.columns([2, 5, 2])

with col_logo:
    # Gợi ý: Lưu logo NHNN dạng ban đầu vào file logo_nhnn.png
    # Thay thế "logo_nhnn.png" bằng đường dẫn file logo của bạn.
    try:
        st.image("logo-nhnnvn-3.png", width=200) 
    except:
        st.markdown(f'<div style="height: 120px;"></div>', unsafe_allow_html=True)

with col_title:
     # Sử dụng CSS để căn giữa và áp dụng màu Nâu Vàng
    header_style = "text-align: center; color: var(--primary-color); margin-bottom: 0px;"
    
    st.markdown(f'<p style="{header_style} font-size: 1.5rem; font-weight: 500; margin-top: 15px;">DASHBOARD TỔNG HỢP PHÂN TÍCH BÁO CÁO</p>', unsafe_allow_html=True)
    
    # Tiêu đề chính to nhất
    st.markdown(f'<h1 style="{header_style} font-size: 3rem; margin-top: 0px;">NGÂN HÀNG NHÀ NƯỚC VIỆT NAM Khu Vực I</h1>', unsafe_allow_html=True)
    
    # DBND
    st.markdown(f'<p style="{header_style} font-size: 1rem; margin-top: -10px;">Hà Nội</p>', unsafe_allow_html=True)

st.markdown("---") # Đường phân cách sau Header

if not uploaded:
    st.info("Vui lòng tải lên file Excel để bắt đầu.")
    st.stop()

# ... (Tiếp tục xử lý dữ liệu)

data = load_excel(uploaded)

def get_df(sheet_key):
    raw = data.get(sheet_key)
    mapping = COL_MAP.get(sheet_key, {})
    if raw is None: return pd.DataFrame()
    return canonicalize_df(raw.copy(), mapping)

df_docs = get_df("documents")
df_over = get_df("overalls")
df_find = get_df("findings")
df_act = get_df("actions")

if df_docs.empty or df_over.empty or df_find.empty:
    st.error("Thiếu một trong các sheet bắt buộc: documents, overalls, findings.")
    st.stop()

# Dates
for c in ["issue_date","period_start","period_end"]:
    if c in df_docs.columns:
        df_docs[c] = safe_date(df_docs[c])

# Numeric
# Áp dụng to_million_vnd cho các cột tiền tệ (giá trị sẽ là triệu đồng)
currency_cols_over = [c for c in COL_MAP["overalls"].keys() if c.endswith("_vnd")]
for c in currency_cols_over:
    if c in df_over.columns: df_over[c] = to_million_vnd(df_over[c])

numeric_cols_over_other = [c for c in COL_MAP["overalls"].keys() if not c.endswith("_vnd")]
for c in numeric_cols_over_other:
    if c in df_over.columns: df_over[c] = df_over[c].apply(to_number)


currency_cols_find = ["quantified_amount", "impacted_accounts"]
for c in currency_cols_find:
    if c in df_find.columns:
        # Chỉ chia cho 1 triệu đối với "quantified_amount"
        if c == "quantified_amount":
            df_find[c] = to_million_vnd(df_find[c])
        else: # Các cột số lượng (như impacted_accounts) thì giữ nguyên to_number
            df_find[c] = df_find[c].apply(to_number)

# RAW handling
df_find["legal_reference_filter"] = coalesce_series_with_raw(df_find["legal_reference"], prefix="RAW")
df_find["legal_reference_chart"] = df_find["legal_reference_filter"].apply(lambda x: "RAW" if str(x).startswith("RAW") else x)

# Sidebar filter (findings only) (GIỮ NGUYÊN)
with st.sidebar:
    st.header("🔎 Lọc Findings")
    all_refs = sorted(df_find["legal_reference_filter"].astype(str).unique().tolist())
    selected_refs = st.multiselect("Chọn Legal_reference", options=all_refs, default=all_refs)
    f_df = df_find[df_find["legal_reference_filter"].astype(str).isin([str(x) for x in selected_refs])].copy()

    st.markdown("---")
    # SỬ DỤNG info_card trong sidebar để nhất quán (ĐÃ SỬA: Đơn vị tiền tệ)
    info_card("💸 Tổng tiền ảnh hưởng (lọc)", format_vnd(f_df["quantified_amount"].sum()))
    info_card("👥 Tổng hồ sơ ảnh hưởng (lọc)", f"{int(f_df['impacted_accounts'].sum()) if 'impacted_accounts' in f_df.columns and pd.notna(f_df['impacted_accounts'].sum()) else '—'}")


# ==============================
# Tabs (GIỮ NGUYÊN)
# ==============================

tab_docs, tab_over, tab_find, tab_act, tab_chat, tab_gemini = st.tabs(
    ["Documents","Overalls","Findings","Actions", " Internal Chatbot (RAG)", "Extenal Chatbot (Gemini)"]
)

# ---- Chatbot Tab (RAG qua n8n) ----
with tab_chat:
    rag_chat_tab()

# ---- Gemini Tab (ĐÃ SỬA LỖI: Gọi hàm với client) ----
with tab_gemini:
    gemini_chat_tab(gemini_client)

# ---- Documents (GIỮ NGUYÊN) ----
with tab_docs:
    st.header("Báo Cáo Kết Luận Thanh Tra")
    st.markdown("---")
    if len(df_docs) == 0:
        st.info("Không có dữ liệu documents.")
    else:
        for idx, row in df_docs.reset_index(drop=True).iterrows():
            st.markdown(f'<div class="doc-wrap"><div class="doc-title"> Báo cáo kết luận thanh tra — {str(row.get("doc_id","—"))}</div>', unsafe_allow_html=True)
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                info_card("Mã số kết luận thanh tra", str(row.get("doc_id","—")))
                info_card("Đơn vị phát hành", str(row.get("issuing_authority","—")))
                info_card("Nội Dung Thanh Tra", str(row.get("field_coverage","—")))
            with c2:
                d = row.get("issue_date", pd.NaT)
                info_card("Ngày phát hành", d.strftime("%d/%m/%Y") if pd.notna(d) else "—")
                info_card("Đơn vị được kiểm tra", str(row.get("inspected_entity_name","—")))
            with c3:
                info_card("Title", str(row.get("title","—")))
                info_card("Lĩnh vực", str(row.get("sector","—")))
            with c4:
                ps = row.get("period_start", pd.NaT); pe = row.get("period_end", pd.NaT)
                info_card("Thời gian thanh tra bắt đầu", ps.strftime("%d/%m/%Y") if pd.notna(ps) else "—")
                info_card("Thời gian thanh tra kết thúc", pe.strftime("%d/%m/%Y") if pd.notna(pe) else "—")
            st.markdown("</div>", unsafe_allow_html=True)

# ---- Overalls (ĐÃ SỬA DỤNG info_card CHO KPI, ĐÃ CHUYỂN ĐƠN VỊ SANG TRIỆU ĐỒNG) ----
with tab_over:
    st.header("Thông Tin Tổng Quan")
    st.markdown("---")
    over_row = df_over.iloc[-1] if len(df_over) else pd.Series({})

    # KPIs sơ lược
    k1,k2,k3,k4,k5 = st.columns(5)
    
    with k1:
        info_card("Tổng nhân sự", f"{int(over_row.get('staff_total', np.nan)) if pd.notna(over_row.get('staff_total', np.nan)) else '—'}")
        info_card("Mẫu kiểm tra", f"{int(over_row.get('sample_total_files', np.nan)) if pd.notna(over_row.get('sample_total_files', np.nan)) else '—'}")
    with k2:
        info_card("Phòng nghiệp vụ (HQ)", f"{int(over_row.get('departments_at_hq_count', np.nan)) if pd.notna(over_row.get('departments_at_hq_count', np.nan)) else '—'}")
        info_card("Phòng giao dịch", f"{int(over_row.get('transaction_offices_count', np.nan)) if pd.notna(over_row.get('transaction_offices_count', np.nan)) else '—'}")
    with k3:
        # Giá trị đã là TRIỆU ĐỒNG, dùng format_vnd để hiển thị.
        info_card("Nguồn vốn gần nhất", format_vnd(over_row.get("mobilized_capital_vnd", np.nan)))
    with k4:
        # Giá trị đã là TRIỆU ĐỒNG, dùng format_vnd để hiển thị.
        info_card("Dư nợ gần nhất", format_vnd(over_row.get("loans_outstanding_vnd", np.nan)))
    with k5:
        # Giá trị đã là TRIỆU ĐỒNG, dùng format_vnd để hiển thị.
        info_card("Nợ xấu (nhóm 3-5)", format_vnd(over_row.get("npl_total_vnd", np.nan)))
        info_card("Tỷ lệ NPL / Dư nợ", f"{over_row.get('npl_ratio_percent', np.nan):.2f}%" if pd.notna(over_row.get('npl_ratio_percent', np.nan)) else "—")
        info_card("Tổng dư nợ đã kiểm tra", format_vnd(over_row.get("sample_outstanding_checked_vnd", np.nan)))


    st.markdown("---")
    
    # --- Cấu trúc lại Block Chart để dễ nhìn hơn ---

    # 1) Chất lượng tín dụng Nhóm 1–3
    st.subheader("**Chất lượng tín dụng (Nhóm 1–3)**")
    q_items = [
        ("Nhóm 1", "structure_quality_group1_vnd"),
        ("Nhóm 2", "structure_quality_group2_vnd"),
        ("Nhóm 3", "structure_quality_group3_vnd"),
    ]
    q_data = []
    for n, c in q_items:
        val = over_row.get(c, np.nan) if c in df_over.columns else np.nan
        val = 0 if pd.isna(val) else float(val)
        q_data.append({"Chỉ tiêu": n, "Giá trị": val})
    dfq = pd.DataFrame(q_data)
    
    # Dùng 2 cột: 1 cho Bar chart, 1 cho Pie chart (giữ nguyên logic gốc)
    c1, c2 = st.columns([2,1]) 
    with c1:
        fig_q_bar = make_bar(dfq, title="Bar: Quy mô theo nhóm (Đơn vị: Triệu VND)")
        st.plotly_chart(fig_q_bar, use_container_width=True)
    with c2:
        fig_q_pie = make_pie([(r["Chỉ tiêu"], r["Giá trị"]) for _, r in dfq.iterrows()], title="Pie: Cơ cấu tỷ trọng")
        st.plotly_chart(fig_q_pie, use_container_width=True)

    st.markdown("---")


    # Chia 2 nhóm biểu đồ thành 2 cột lớn để tăng không gian hiển thị (Term/Currency) và (Purpose/Economic)
    # Column set 1: Kỳ hạn và Tiền tệ
    col_set1, col_set2 = st.columns(2)

    with col_set1:
        # 2) Kỳ hạn
        st.subheader("**Cơ cấu theo kỳ hạn**")
        term_items = [
            ("Dư nợ ngắn hạn", "structure_term_short_vnd"),
            ("Dư nợ trung & dài hạn", "structure_term_medium_long_vnd"),
        ]
        term_data = []
        for n, c in term_items:
            val = over_row.get(c, np.nan) if c in df_over.columns else np.nan
            term_data.append({"Chỉ tiêu": n, "Giá trị": 0 if pd.isna(val) else float(val)})
        dft = pd.DataFrame(term_data)
        fig_t = make_bar(dft, title="Kỳ hạn (Đơn vị: Triệu VND)", height=280) # Tăng nhẹ chiều cao
        st.plotly_chart(fig_t, use_container_width=True)

        # 3) Tiền tệ
        st.subheader("**Cơ cấu theo tiền tệ**")
        cur_items = [
            ("Dư nợ bằng VND", "structure_currency_vnd_vnd"),
            ("Dư nợ quy đổi ngoại tệ", "structure_currency_fx_vnd"),
        ]
        cur_data = []
        for n, c in cur_items:
            val = over_row.get(c, np.nan) if c in df_over.columns else np.nan
            cur_data.append({"Chỉ tiêu": n, "Giá trị": 0 if pd.isna(val) else float(val)})
        dfc = pd.DataFrame(cur_data)
        fig_c = make_bar(dfc, title="Tiền tệ (Đơn vị: Triệu VND)", height=280) # Tăng nhẹ chiều cao
        st.plotly_chart(fig_c, use_container_width=True)


    with col_set2:
        # 4) Mục đích vay
        st.subheader("**Cơ cấu theo mục đích vay**")
        pur_items = [
            ("BĐS / linh hoạt", "structure_purpose_bds_flexible_vnd"),
            ("Chứng khoán", "strucuture_purpose_securities_vnd"),
            ("Tiêu dùng", "structure_purpose_consumption_vnd"),
            ("Thương mại", "structure_purpose_trade_vnd"),
            ("Mục đích khác", "structure_purpose_other_vnd"),
        ]
        pur_data = []
        for n, c in pur_items:
            val = over_row.get(c, np.nan) if c in df_over.columns else np.nan
            pur_data.append({"Chỉ tiêu": n, "Giá trị": 0 if pd.isna(val) else float(val)})
        dfp = pd.DataFrame(pur_data)
        fig_p = make_bar(dfp, title="Mục đích vay (Đơn vị: Triệu VND)", height=380) # Tăng chiều cao để chứa nhiều mục
        st.plotly_chart(fig_p, use_container_width=True)

        # 5) Thành phần kinh tế
        st.subheader("**Cơ cấu theo thành phần kinh tế**")
        eco_items = [
            ("DN Nhà nước", "structure_econ_state_vnd"), 
            ("DN tổ chức kinh tế", "structure_econ_nonstate_enterprises_vnd"), 
            ("DN tư nhân cá thể", "structure_econ_individuals_households_vnd"), 
        ]
        
        eco_data = []
        for n, c in eco_items:
            val = over_row.get(c, np.nan) if c in df_over.columns else np.nan
            eco_data.append({"Chỉ tiêu": n, "Giá trị": 0 if pd.isna(val) else float(val)})
        dfe = pd.DataFrame(eco_data)
        fig_e = make_bar(dfe, title="Thành phần kinh tế (Đơn vị: Triệu VND)", height=280) # Tăng nhẹ chiều cao
        st.plotly_chart(fig_e, use_container_width=True)


# ---- Findings (GIỮ NGUYÊN - ĐÃ SỬA ĐƠN VỊ TIỀN TỆ) ----
with tab_find:
    st.header("Tổng quan về các Vi phạm đã Phát hiện và Phân tích Nguyên nhân")
    st.subheader(f"Đang lọc theo: {len(selected_refs)}/{len(all_refs)} legal_reference")
    st.markdown("---")
    if f_df.empty:
        st.warning("Không có dữ liệu theo bộ lọc hiện tại.")
    else:
        # Cân đối lại column cho biểu đồ Findings: 2/3 và 1/3
        col1, col2 = st.columns([2, 1]) 
        with col1:
            cat_count = f_df["category"].value_counts().reset_index()
            cat_count.columns = ["Category","Count"]
            fig1 = px.bar(
                cat_count, x="Count", y="Category", orientation='h',
                title="Số lượng Vi phạm theo Phân loại",
                text="Count",
                color="Category", color_discrete_sequence=PALETTE,
                height=350
            )
            fig1.update_traces(textposition='outside')
            fig1.update_layout(yaxis={'categoryorder':'total ascending'}, showlegend=False, margin=dict(l=10, r=10, t=60, b=10))
            st.plotly_chart(fig1, use_container_width=True)

        with col2:
            legal_agg = f_df.groupby("legal_reference_chart")["quantified_amount"].sum().reset_index()
            legal_agg.columns = ["Legal_Reference", "Total_Amount"]
            legal_agg["Total_Amount_Label"] = legal_agg["Total_Amount"].apply(_format_vnd_text)

            fig2 = px.pie(
                legal_agg, names="Legal_Reference", values="Total_Amount",
                title="Cơ cấu Tổng tiền ảnh hưởng theo Tham chiếu Pháp lý",
                hole=.35,
                color="Legal_Reference", color_discrete_sequence=PALETTE,
                height=350
            )
            fig2.update_traces(textinfo="percent+label", textfont=dict(size=12))
            fig2.update_layout(margin=dict(l=10, r=10, t=60, b=10))
            st.plotly_chart(fig2, use_container_width=True)

        st.markdown("---")
        st.subheader("Bảng chi tiết Findings")
        
        # Định dạng lại cột tiền tệ để hiển thị đơn vị triệu đồng
        display_df = f_df.copy()
        display_df["quantified_amount"] = display_df["quantified_amount"].apply(format_vnd)
        display_df["impacted_accounts"] = display_df["impacted_accounts"].apply(lambda x: f"{int(x):,.0f}" if pd.notna(x) else "—")
        
        st.dataframe(display_df[[
            "category", "sub_category", "description", "root_cause", 
            "quantified_amount", "impacted_accounts", "legal_reference"
        ]], use_container_width=True, height=500)

# ---- Actions (GIỮ NGUYÊN) ----
with tab_act:
    st.header("Các Hành Động Khắc Phục và Khuyến Nghị")
    st.markdown("---")
    if df_act.empty:
        st.info("Không có dữ liệu actions.")
    else:
        st.dataframe(df_act, use_container_width=True, height=700)
