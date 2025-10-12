# python.py
# Streamlit app: Dashboard trực quan hóa Kết luận Thanh tra (KLTT)
# Chạy: streamlit run python.py
# Yêu cầu:
#   pip install streamlit pandas altair openpyxl plotly requests google-genai

import io
import time
import numpy as np
import pandas as pd
import streamlit as st
import altair as alt
import plotly.express as px
import requests  # gọi n8n Webhook
from google import genai
from google.genai.errors import APIError

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

def call_n8n_chatbot(prompt: str):
    """Gửi câu hỏi tới n8n RAG Webhook và nhận câu trả lời. Bao gồm logic Chat ID."""
    if "N8N_WEBHOOK_URL" not in st.secrets:
        return "Lỗi cấu hình: Thiếu N8N_WEBHOOK_URL trong secrets.toml. Vui lòng thiết lập để sử dụng chatbot."
    webhook_url = st.secrets["N8N_WEBHOOK_URL"]

    if "chat_session_id" not in st.session_state:
        st.session_state.chat_session_id = pd.Timestamp.now().strftime("%Y%m%d%H%M%S%f")

    payload = {"query": prompt, "chatId": st.session_state.chat_session_id}
    try:
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
    st.header("🤖 Trợ lý RAG (Hỏi & Đáp Dữ liệu KLTT)")
    if st.button("🔄 Bắt đầu phiên Chat mới (Reset Lịch sử)", type="primary"):
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
# GEMINI CHATBOT (TAB RIÊNG, SỬA 400)
# ==============================

GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY")
GEMINI_MODEL = st.secrets.get("GEMINI_MODEL", "gemini-1.5-flash")  # model ổn định

try:
    gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
except Exception:
    gemini_client = None

def _normalize_gemini_messages(streamlit_history: list) -> list:
    """
    Chuẩn hoá lịch sử thành 'contents' cho Gemini SDK:
    - Bỏ mọi message ở đầu cho tới khi gặp 'user' (tránh 400).
    - Map role: assistant->model, user->user.
    - Không để 2 'model' liên tiếp.
    - Cắt text dài tránh payload quá khổ.
    """
    i = 0
    while i < len(streamlit_history) and streamlit_history[i].get("role") != "user":
        i += 1
    msgs = streamlit_history[i:] if i < len(streamlit_history) else []
    if not msgs:
        msgs = [{"role": "user", "content": ""}]

    contents = []
    for m in msgs:
        api_role = "model" if m["role"] == "assistant" else "user"
        text = str(m.get("content", ""))[:20000]
        if contents and contents[-1]["role"] == api_role and api_role == "model":
            contents[-1]["parts"][0]["text"] += "\n\n" + text
        else:
            contents.append({"role": api_role, "parts": [{"text": text}]})
    return contents

def gemini_chat_tab():
    st.header("🧠 Gemini Chat (General AI)")
    st.caption("Tip: Dùng Gemini cho câu hỏi tổng quát, soạn thảo, ý tưởng… (không ràng buộc dữ liệu KLTT).")
    st.markdown("---")

    if not gemini_client:
        st.warning(
            "Thiếu `GEMINI_API_KEY` trong `.streamlit/secrets.toml`.\n"
            "Ví dụ:\n\nGEMINI_API_KEY = \"your_api_key\"\n# Tuỳ chọn:\n# GEMINI_MODEL = \"gemini-1.5-pro\""
        )
        return

    # Reset phiên
    if st.button("🔄 Reset phiên Gemini", key="gemini_reset_btn"):
        st.session_state.gemini_history = [
            {"role": "assistant", "content": "Xin chào 👋 Tôi là **Gemini**. Hãy đặt câu hỏi hoặc mô tả tác vụ bạn cần hỗ trợ."}
        ]
        st.rerun()

    # Khởi tạo lịch sử
    if "gemini_history" not in st.session_state:
        st.session_state.gemini_history = [
            {"role": "a
