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
import requests  # THƯ VIỆN ĐỂ GỌI n8n Webhook
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
# Helpers (GIỮ NGUYÊN)
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

def safe_date(series: pd.Series):
    try: return pd.to_datetime(series, errors="coerce")
    except Exception: return pd.to_datetime(pd.Series([None]*len(series)), errors="coerce")

def format_vnd(n):
    if pd.isna(n): return "—"
    n = float(n)
    if abs(n) >= 1_000_000_000_000: return f"{n/1_000_000_000_000:.2f} nghìn tỷ ₫"
    if abs(n) >= 1_000_000_000: return f"{n/1_000_000_000:.2f} tỷ ₫"
    if abs(n) >= 1_000_000: return f"{n/1_000_000:.2f} triệu ₫"
    return f"{n:,.0f} ₫"

# ===== Plot helpers for Overalls (GIỮ NGUYÊN) =====
PALETTE = ["#1f6feb", "#16a34a", "#f59e0b", "#ef4444", "#0ea5e9", "#a855f7", "#22c55e", "#a50000", "#6b7280"]

def _format_vnd_text(v):
    if pd.isna(v): return "—"
    try:
        v = float(v)
    except:
        return "—"
    if abs(v) < 0.5:
        return "0 ₫"
    return format_vnd(v)

def make_bar(df_in, x_col="Chỉ tiêu", y_col="Giá trị", title="", height=260):
    """Bar chart gọn: mỗi cột 1 màu; nhãn in đậm & đổi màu; hiển thị số 0."""
    d = df_in.copy()
    n = len(d)
    colors = PALETTE[:max(1, n)]
    fig = px.bar(
        d, x=x_col, y=y_col,
        text=d[y_col].apply(_format_vnd_text),
        color=x_col, color_discrete_sequence=colors,
        title=title
    )
    fig.update_traces(
        textposition="outside",
        texttemplate="<b>%{text}</b>",
        marker_line_color="white",
        marker_line_width=0.5,
        textfont=dict(color="#1f6feb", size=12)
    )
    fig.update_layout(
        height=height, bargap=0.40,
        yaxis_title="VND", xaxis_title="", legend_title_text="",
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
    --tab-font-size: 18px;       /* Cỡ chữ tab mặc định (desktop) */
    --tab-gap: 28px;             /* Khoảng cách giữa các tab */
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
    border-bottom: 2px solid #e6e6e6;
    padding-bottom: 5px;
    margin-top: 1.5rem;
}

/* Thanh phân cách */
hr { border-top: 1px solid var(--primary-color); }

/* Dataframe wrap chữ */
[data-testid="stDataFrame"] td, [data-testid="stDataFrame"] th {
    white-space: pre-wrap !important;
    word-break: break-word !important;
}

/* Info Card */
.info-card{
  position: relative;
  display: block;
  padding: 16px 18px 14px 18px;
  background: #fff;
  border: 3px solid #ece8df;
  border-left: 8px solid var(--primary-color);
  border-radius: 16px;
  min-height: 72px;
  margin-bottom: 12px;
  box-shadow: 0 1px 0 rgba(0,0,0,.02);
}
.info-card .label { 
    font-size: 20px; 
    color: var(--primary-color); 
    font-weight: 700; 
    margin-bottom: 4px; 
}
.info-card .value { 
    font-size: 20px; 
    line-height: 1.4; 
    white-space: pre-wrap; 
    word-break: break-word; 
    font-weight: 600;
}

/* Document Wrap */
.doc-wrap { 
    padding: 15px; 
    border: 1px solid var(--primary-color); 
    border-radius: 12px; 
    background: #fffdf7;
    margin-bottom: 14px; 
}
.doc-title { 
    font-weight: 700; 
    font-size: 18px; 
    color: var(--primary-color);
    margin-bottom: 10px; 
}

/* -------- Tabs – Center & Size (Căn giữa + tăng cỡ chữ) -------- */

/* Bộ chứa tablist: căn giữa + khoảng cách đều */
div[data-testid="stTabs"] > div[role="tablist"] {
    display: flex !important;
    justify-content: center !important;      /* Căn giữa toàn bộ dải menu */
    align-items: center !important;
    gap: var(--tab-gap) !important;          /* Khoảng cách giữa các mục */
    flex-wrap: wrap !important;              /* Xuống dòng nếu hẹp */
    padding: 6px 4px 2px 4px !important;
}

/* Nút tab (menu) */
div[data-testid="stTabs"] button[data-testid^="stTab"] {
    font-size: var(--tab-font-size) !important; /* Tăng cỡ chữ */
    font-weight: 700 !important;                /* Đậm hơn cho cân với header */
    color: #6b4f25 !important;                  /* Nâu vàng nhạt */
    background: transparent !important;
    border: none !important;
    padding: 8px 6px !important;
    border-radius: 6px !important;
    text-transform: none !important;            /* Giữ nguyên kiểu chữ */
}

/* Tab đang chọn (active) */
div[data-testid="stTabs"] button[aria-selected="true"] {
    color: #c19b45 !important;                  /* Vàng gold nhẹ */
    box-shadow: inset 0 -3px 0 0 #c19b45 !important; /* Gạch chân dày */
}

/* Hover nhẹ */
div[data-testid="stTabs"] button[data-testid^="stTab"]:hover {
    color: #a68233 !important;
}

/* Thu nhỏ cỡ chữ trên màn hẹp */
@media (max-width: 1200px) {
  :root { --tab-font-size: 16px; --tab-gap: 22px; }
}
@media (max-width: 768px) {
  :root { --tab-font-size: 15px; --tab-gap: 16px; }
}

/* --------------------------------------------------------------- */

/* Tabs Accent (giữ để tương thích) */
button[data-testid^="stTab"]:focus {
    color: var(--primary-color) !important; 
    border-bottom: 2px solid var(--primary-color) !important; 
}
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
    try:
        st.image("logo_nhnn.png", width=200) 
    except:
        st.markdown(f'<div style="height: 120px;"></div>', unsafe_allow_html=True)

with col_title:
    header_style = "text-align: center; color: var(--primary-color); margin-bottom: 0px;"
    st.markdown(f'<p style="{header_style} font-size: 1.1rem; font-weight: 500; margin-top: 15px;">DASHBOARD TỔNG HỢP PHÂN TÍCH BÁO CÁO</p>', unsafe_allow_html=True)
    st.markdown(f'<h1 style="{header_style} font-size: 2.8rem; margin-top: 0px;">NGÂN HÀNG NHÀ NƯỚC VIỆT NAM</h1>', unsafe_allow_html=True)
    st.markdown(f'<p style="{header_style} font-size: 1rem; margin-top: -10px;">DBND</p>', unsafe_allow_html=True)

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
for c in COL_MAP["overalls"].keys():
    if c in df_over.columns: df_over[c] = df_over[c].apply(to_number)
for c in ["quantified_amount","impacted_accounts"]:
    if c in df_find.columns: df_find[c] = df_find[c].apply(to_number)

# RAW handling
df_find["legal_reference_filter"] = coalesce_series_with_raw(df_find["legal_reference"], prefix="RAW")
df_find["legal_reference_chart"] = df_find["legal_reference_filter"].apply(lambda x: "RAW" if str(x).startswith("RAW") else x)

# Sidebar filter (findings only)
with st.sidebar:
    st.header("🔎 Lọc Findings")
    all_refs = sorted(df_find["legal_reference_filter"].astype(str).unique().tolist())
    selected_refs = st.multiselect("Chọn Legal_reference", options=all_refs, default=all_refs)
    f_df = df_find[df_find["legal_reference_filter"].astype(str).isin([str(x) for x in selected_refs])].copy()

    st.markdown("---")
    info_card("💸 Tổng tiền ảnh hưởng (lọc)", format_vnd(f_df["quantified_amount"].sum()))
    info_card("👥 Tổng hồ sơ ảnh hưởng (lọc)", f"{int(f_df['impacted_accounts'].sum()) if 'impacted_accounts' in f_df.columns and pd.notna(f_df['impacted_accounts'].sum()_]()]()
