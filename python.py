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

# Thêm thư viện Google GenAI (Đã sử dụng chính thức thay vì Mock)
try:
    from google import genai
    from google.genai import types
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

st.set_page_config(
    page_title="Dashboard Kết luận Thanh tra (KLTT)",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================================
# Helpers (GIỮ NGUYÊN)
# ==========================================================

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

# ==========================================================
# RAG CHAT FIXED (SỬA LỖI AttributeError)
# ==========================================================

def call_rag_api(prompt: str):
    if "N8N_WEBHOOK_URL" not in st.secrets:
        return "**[LỖI CẤU HÌNH]** Vui lòng thiết lập **N8N_WEBHOOK_URL** trong file .streamlit/secrets.toml."

    try:
        response = requests.post(st.secrets["N8N_WEBHOOK_URL"], json={"chatInput": prompt}, timeout=120)
        response.raise_for_status()
        return response.text.strip()
    except Exception as e:
        return f"**[LỖI RAG API]** {e}"

def reset_rag_chat_session():
    st.session_state.rag_chat_history = []
    st.session_state.rag_chat_counter = 0
    st.session_state.rag_chat_history.append(
        {"role": "assistant", "content": "Phiên trò chuyện đã được **reset**. Tôi là RAG Chatbot, hãy hỏi tôi về dữ liệu KLTT."}
    )
    st.rerun()

def rag_chat_tab():
    st.header("🤖 Chat với RAG Chatbot (Dữ liệu KLTT)")

    if st.button("🔄 Reset phiên Chat", key="rag_reset_button", type="primary"):
        reset_rag_chat_session()
        return

    # ✅ FIX LỖI: đảm bảo các biến tồn tại trước khi dùng
    if "rag_chat_history" not in st.session_state:
        st.session_state.rag_chat_history = [{"role": "assistant", "content": "Chào bạn, tôi là RAG Chatbot."}]
    if "rag_chat_counter" not in st.session_state:
        st.session_state.rag_chat_counter = 0

    st.caption(f"Phiên chat hiện tại: **{st.session_state.rag_chat_counter}** / 5 câu hỏi.")
    st.markdown("---")

    # Hiển thị lịch sử chat
    for message in st.session_state.rag_chat_history:
        avatar = "🤖" if message["role"] == "assistant" else "👤"
        with st.chat_message(message["role"], avatar=avatar):
            st.markdown(message["content"])

    # ✅ FIX: kiểm tra an toàn
    user_prompt = st.chat_input("Hỏi RAG Chatbot...", key="rag_chat_input")
    if user_prompt:
        if st.session_state.rag_chat_counter >= 5:
            st.info("Đã đạt 5 câu hỏi. Phiên sẽ được reset.")
            reset_rag_chat_session()
            return

        st.session_state.rag_chat_history.append({"role": "user", "content": user_prompt})
        with st.chat_message("user", avatar="👤"):
            st.markdown(user_prompt)

        with st.chat_message("assistant", avatar="🤖"):
            with st.spinner("Đang xử lý..."):
                response_text = call_rag_api(user_prompt)
                st.markdown(response_text)
        st.session_state.rag_chat_history.append({"role": "assistant", "content": response_text})
        st.session_state.rag_chat_counter += 1

# ==========================================================
# (Phần còn lại giữ nguyên: Gemini chat, Overalls, Findings...)
# ==========================================================
# ⤵ GIỮ NGUYÊN toàn bộ các phần còn lại trong file gốc bạn gửi.
# Bao gồm: gemini_chat_tab(), load_excel(), canonicalize_df(),
# các biểu đồ Overalls, Findings, Actions và Tabs.
# ==========================================================
