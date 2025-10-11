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
import requests 

# MỚI: Thư viện cho Gemini API
try:
    from google import genai 
except ImportError:
    genai = None # Xử lý trường hợp người dùng chưa cài đặt thư viện

st.set_page_config(
    page_title="Dashboard Kết luận Thanh tra (KLTT)",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

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
PALETTE = ["#2563eb", "#16a34a", "#f59e0b", "#ef4444", "#0ea5e9", "#a855f7", "#22c55e", "#e11d48", "#6b7280"]

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
        textfont=dict(color="#0ea5e9", size=12)
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
# Theme + CSS (GIỮ NGUYÊN)
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
# RAG CHATBOT LOGIC (GIỮ NGUYÊN)
# ==============================

def call_n8n_rag_chatbot(prompt: str):
    """Gửi câu hỏi tới n8n RAG Webhook và nhận câu trả lời. Bao gồm logic Chat ID."""
    if "N8N_RAG_WEBHOOK_URL" not in st.secrets:
        return "Lỗi cấu hình: Thiếu N8N_RAG_WEBHOOK_URL trong secrets.toml. Vui lòng thiết lập để sử dụng chatbot."
    
    webhook_url = st.secrets["N8N_RAG_WEBHOOK_URL"]
    
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
    
    # 1. Reset lịch sử chat
    st.session_state.rag_chat_history = []
    
    # 2. Reset biến đếm
    if "rag_chat_counter" in st.session_state:
        st.session_state.rag_chat_counter = 0

    # 3. Reset ID phiên chat (quan trọng để n8n cũng quên lịch sử)
    if "chat_session_id" in st.session_state:
        del st.session_state.chat_session_id
    
    # 4. Thêm tin nhắn chào mừng mới
    st.session_state.rag_chat_history.append(
        {"role": "assistant", "content": "Phiên trò chuyện đã được **reset** thành công. Chào bạn, tôi là Trợ lý RAG được kết nối qua n8n. Hãy hỏi tôi về các thông tin KLTT."}
    )
    
    # Dùng st.rerun() để làm mới giao diện ngay lập lập tức
    st.rerun()


def rag_chat_tab():
    """Thêm khung chat RAG kết nối qua n8n Webhook vào tab."""
    st.header("🤖 Trợ lý RAG (Hỏi & Đáp Dữ liệu KLTT)")
    
    # Đặt nút Reset thủ công
    if st.button("🔄 Bắt đầu phiên Chat mới (Reset Lịch sử)", type="primary"):
        reset_rag_chat_session()
        return 

    # 1. KHỞI TẠO BIẾN ĐẾM & LỊCH SỬ CHAT
    if "rag_chat_history" not in st.session_state:
        st.session_state.rag_chat_history = []
        st.session_state.rag_chat_counter = 0
        st.session_state.rag_chat_history.append(
            {"role": "assistant", "content": "Chào bạn, tôi là Trợ lý RAG được kết nối qua n8n. Hãy hỏi tôi về các thông tin KLTT."}
        )
    
    current_count = st.session_state.get("rag_chat_counter", 0)
    st.caption(f"Phiên chat hiện tại: **{current_count}** / 5 câu. (Hỏi 5 câu sẽ tự động reset)")

    st.markdown("---")

    # Kiểm tra URL Webhook
    if "N8N_RAG_WEBHOOK_URL" not in st.secrets:
        st.warning("Vui lòng thiết lập N8N_RAG_WEBHOOK_URL trong file .streamlit/secrets.toml để sử dụng Chatbot.")
        return

    # Hiển thị lịch sử chat
    for message in st.session_state.rag_chat_history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # 2. XỬ LÝ INPUT VÀ LOGIC RESET TỰ ĐỘNG
    if user_prompt := st.chat_input("Hỏi Trợ lý RAG...", key="rag_chat_input"):
        
        # KIỂM TRA VÀ RESET PHIÊN CHAT (Tự động sau 5 câu)
        if st.session_state.rag_chat_counter >= 5:
            # Gửi thông báo reset (hiển thị trong phiên cũ trước khi reset)
            with st.chat_message("assistant"):
                st.info("Phiên trò chuyện đã đạt 5 câu hỏi. **Lịch sử sẽ được xóa.** Vui lòng bắt đầu câu hỏi mới.")
            
            # Thực hiện reset và st.rerun()
            reset_rag_chat_session()
            return

        # 1. Thêm prompt người dùng vào lịch sử và hiển thị ngay lập tức
        st.session_state.rag_chat_history.append({"role": "user", "content": user_prompt})
        with st.chat_message("user"):
            st.markdown(user_prompt)

        # 2. Gọi API n8n
        with st.chat_message("assistant"):
            with st.spinner("RAG Chatbot (n8n) đang xử lý..."):
                
                response_text = call_n8n_rag_chatbot(user_prompt)
                
                st.markdown(response_text)
                
                # 3. Cập nhật lịch sử chat với câu trả lời VÀ TĂNG BIẾN ĐẾM
                st.session_state.rag_chat_history.append({"role": "assistant", "content": response_text})
                st.session_state.rag_chat_counter += 1

# ==============================
# GEMINI CHATBOT LOGIC (MỚI)
# ==============================

def gemini_sidebar_chat():
    """Khung chat Gemini tích hợp vào Sidebar. Sử dụng st.text_input và st.button."""
    st.markdown("---")
    st.header("✨ Chatbot Gemini (Tổng quát)")
    st.caption("Sử dụng `gemini-2.5-flash`.")
    
    # 0. Kiểm tra API Key và thư viện
    if genai is None:
        st.error("Thiếu thư viện `google-genai`.")
        return
    if "GEMINI_API_KEY" not in st.secrets:
        st.error("Thiếu GEMINI_API_KEY. Vui lòng thêm key vào file .streamlit/secrets.toml")
        return

    # 1. Khởi tạo client và session
    try:
        client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
        model = "gemini-2.5-flash"
        
        # Tạo session chat và lịch sử nếu chưa có
        if "gemini_chat_session" not in st.session_state:
            st.session_state.gemini_chat_session = client.chats.create(model=model)
            st.session_state.gemini_chat_history = []
            st.session_state.gemini_chat_history.append(
                {"role": "assistant", "content": "Chào bạn, tôi là Gemini. Bạn có câu hỏi nào về Streamlit, Python, hay bất kỳ chủ đề nào khác không?"}
            )
    except Exception as e:
        st.error(f"Lỗi khởi tạo Gemini: {e}")
        return

    # 2. Hiển thị lịch sử chat trong container cố định chiều cao
    chat_container = st.container(height=300) 
    with chat_container:
        for message in st.session_state.gemini_chat_history:
            # Dùng markdown custom cho sidebar để hiển thị gọn gàng hơn
            if message["role"] == "user":
                 st.markdown(f"**👤 Bạn:** {message['content']}")
            else:
                 st.markdown(f"**✨ Gemini:** {message['content']}")


    # 3. Xử lý input
    col_input, col_btn = st.columns([3, 1])
    with col_input:
        user_prompt = st.text_input("Hỏi Gemini...", key="gemini_sidebar_input_box", label_visibility="collapsed", placeholder="Gõ câu hỏi của bạn...")

    with col_btn:
        # Nút Reset (đặt riêng)
        if st.button("Reset", key="gemini_reset_btn", use_container_width=True):
            st.session_state.gemini_chat_session = client.chats.create(model=model)
            st.session_state.gemini_chat_history = []
            st.session_state.gemini_chat_history.append(
                {"role": "assistant", "content": "Phiên chat Gemini đã được **reset** thành công. Hãy bắt đầu hỏi nhé!"}
            )
            st.rerun()
            
    # Xử lý khi nhấn Enter (hoặc click nút Gửi, nhưng ở đây ta dùng logic text_input thay đổi)
    if user_prompt:
        if "last_gemini_input" not in st.session_state or st.session_state.last_gemini_input != user_prompt:
            
            st.session_state.last_gemini_input = user_prompt 
            
            # Thêm prompt người dùng
            st.session_state.gemini_chat_history.append({"role": "user", "content": user_prompt})
            
            # Gọi API và hiển thị phản hồi
            with st.spinner("Gemini đang trả lời..."):
                try:
                    response = st.session_state.gemini_chat_session.send_message(user_prompt)
                    response_text = response.text
                except Exception as e:
                    response_text = f"Lỗi gọi API Gemini: {e}"
                
                st.session_state.gemini_chat_history.append({"role": "assistant", "content": response_text})
                st.rerun()


# ==============================
# Column mappings (GIỮ NGUYÊN)
# ==============================
# ... (COL_MAP definitions)
# ...

# ==============================
# Sidebar (Upload + Filters) (CẬP NHẬT)
# ==============================

with st.sidebar:
    st.header("📤 Tải dữ liệu")
    uploaded = st.file_uploader("Excel (.xlsx): documents, overalls, findings, (actions tuỳ chọn)", type=["xlsx"])
    st.caption("Tên sheet & cột không phân biệt hoa/thường.")

st.title("🛡️ Dashboard Báo Cáo Kết Luận Thanh Tra")

if not uploaded:
    st.info("Vui lòng tải lên file Excel để bắt đầu.")
    st.stop()

# ... (Tiếp tục xử lý dữ liệu)
# ... (Data loading and processing code)
# ...

# Sidebar filter (findings only) (CẬP NHẬT)
with st.sidebar:
    st.header("🔎 Lọc Findings")
    all_refs = sorted(df_find["legal_reference_filter"].astype(str).unique().tolist())
    selected_refs = st.multiselect("Chọn Legal_reference", options=all_refs, default=all_refs)
    f_df = df_find[df_find["legal_reference_filter"].astype(str).isin([str(x) for x in selected_refs])].copy()

    st.markdown("---")
    st.metric("💸 Tổng tiền ảnh hưởng (lọc)", format_vnd(f_df["quantified_amount"].sum()))
    st.metric("👥 Tổng hồ sơ ảnh hưởng (lọc)", f"{int(f_df['impacted_accounts'].sum()) if 'impacted_accounts' in f_df.columns and pd.notna(f_df['impacted_accounts'].sum()) else '—'}")
    
    # GỌI CHAT GEMINI MỚI VÀO CUỐI SIDEBAR
    gemini_sidebar_chat()


# ==============================
# Tabs (ĐÃ THÊM TAB CHATBOT) (GIỮ NGUYÊN)
# ==============================
# ... (Rest of the code for tabs: tab_docs, tab_over, tab_find, tab_act, tab_chat)
