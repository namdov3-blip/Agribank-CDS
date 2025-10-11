# python.py
# Streamlit app: Dashboard trực quan hóa Kết luận Thanh tra (KLTT)
# Chạy: streamlit run python.py
# Yêu cầu cài đặt:
#   pip install streamlit pandas altair openpyxl plotly requests google-generativeai

import io
import numpy as np
import pandas as pd
import streamlit as st
import altair as alt
import plotly.express as px
import requests  # THÊM MỚI: Thư viện để gọi n8n Webhook

# === GEMINI CHAT (NEW) ===
try:
    import google.generativeai as genai
    _HAS_GEMINI = True
except Exception:
    _HAS_GEMINI = False

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
# RAG CHATBOT LOGIC (GIỮ NGUYÊN + HÀM)
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
        "chatId": st.session_state.chat_session_id  # Truyền Chat ID
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
    
    # Dùng st.rerun() để làm mới giao diện ngay lập tức
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
            with st.chat_message("assistant"):
                st.info("Phiên trò chuyện đã đạt 5 câu hỏi. **Lịch sử sẽ được xóa.** Vui lòng bắt đầu câu hỏi mới.")
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
# GEMINI CHAT HELPERS (NEW)
# ==============================

def _setup_gemini():
    """
    Khởi tạo model Gemini từ secrets.
    Cần thêm vào .streamlit/secrets.toml:
    GEMINI_API_KEY = "your_key"
    # tuỳ chọn:
    # GEMINI_MODEL = "gemini-1.5-flash" hoặc "gemini-1.5-pro"
    """
    if not _HAS_GEMINI:
        return None, "Chưa cài thư viện google-generativeai. Vui lòng chạy: pip install google-generativeai"
    if "GEMINI_API_KEY" not in st.secrets:
        return None, "Thiếu GEMINI_API_KEY trong secrets.toml"
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        model_name = st.secrets.get("GEMINI_MODEL", "gemini-1.5-flash")
        model = genai.GenerativeModel(model_name)
        return model, None
    except Exception as e:
        return None, f"Lỗi khởi tạo Gemini: {e}"

def _call_gemini(model, user_msg: str, history: list):
    """
    Gọi Gemini kèm ngữ cảnh (tối đa 6 lượt gần nhất) để hội thoại mượt hơn.
    history: list[{'role': 'user'|'assistant', 'content': str}]
    """
    contents = []
    for h in history[-6:]:
        role = "user" if h["role"] == "user" else "model"
        contents.append({"role": role, "parts": [str(h["content"])[:6000]]})

    system_hint = (
        "Bạn là trợ lý AI của Agribank. Trả lời ngắn gọn, chính xác, ưu tiên tiếng Việt, "
        "dùng gạch đầu dòng nếu cần. Nếu câu hỏi nằm ngoài phạm vi, hãy nói rõ và gợi ý cách hỏi phù hợp."
    )
    contents.insert(0, {"role": "user", "parts": [system_hint]})
    contents.append({"role": "user", "parts": [user_msg[:6000]]})

    try:
        resp = model.generate_content(contents)
        return (resp.text or "").strip() if hasattr(resp, "text") else "Không nhận được nội dung phản hồi từ Gemini."
    except Exception as e:
        return f"Lỗi gọi Gemini: {e}"

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

        "strucuture_econ_state_vnd": ["strucuture_econ_state_vnd"],
        "strucuture_econ_nonstate_enterprises_vnd": ["strucuture_econ_nonstate_enterprises_vnd"],
        "strucuture_econ_individuals_households_vnd": ["strucuture_econ_individuals_households_vnd"],
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
# Sidebar (Upload + Gemini Chat) (ĐÃ CHÈN CHAT GEMINI)
# ==============================

with st.sidebar:
    st.header("📤 Tải dữ liệu")
    uploaded = st.file_uploader("Excel (.xlsx): documents, overalls, findings, (actions tuỳ chọn)", type=["xlsx"])
    st.caption("Tên sheet & cột không phân biệt hoa/thường.")

    # === GEMINI CHAT SIDEBAR (NEW) ===
    st.markdown("---")
    with st.expander("💬 Gemini Chat (beta)", expanded=False):
        model, gem_err = _setup_gemini()

        # Khởi tạo lịch sử chat lưu trong session
        if "gem_chat_history" not in st.session_state:
            st.session_state.gem_chat_history = [
                {"role": "assistant", "content": "Xin chào! Tôi là Gemini – trợ lý AI hỗ trợ bạn trong thiết kế sản phẩm AI/Chuyển đổi số Agribank. Bạn muốn hỏi gì?"}
            ]

        # Hiển thị lịch sử tóm tắt (sidebar không hỗ trợ st.chat_message, dùng markdown)
        hist_container = st.container()
        for m in st.session_state.gem_chat_history[-8:]:
            who = "👤 Bạn" if m["role"] == "user" else "🤖 Gemini"
            hist_container.markdown(f"**{who}:** {m['content']}")

        # Input + Buttons
        user_msg = st.text_input("Nhập câu hỏi cho Gemini...", key="gem_input")
        c1, c2 = st.columns(2)
        send_clicked = c1.button("Gửi", use_container_width=True, disabled=(not user_msg))
        reset_clicked = c2.button("Reset", use_container_width=True)

        if reset_clicked:
            st.session_state.gem_chat_history = [
                {"role": "assistant", "content": "Đã tạo phiên mới. Tôi là Gemini, sẵn sàng hỗ trợ bạn!"}
            ]
            st.rerun()

        if send_clicked and user_msg:
            if gem_err:
                st.warning(gem_err)
            elif model is None:
                st.warning("Gemini chưa sẵn sàng.")
            else:
                # Lưu câu hỏi
                st.session_state.gem_chat_history.append({"role": "user", "content": user_msg})
                with st.spinner("Gemini đang trả lời..."):
                    answer = _call_gemini(model, user_msg, st.session_state.gem_chat_history)
                st.session_state.gem_chat_history.append({"role": "assistant", "content": answer})
                st.rerun()

st.title("🛡️ Dashboard Báo Cáo Kết Luận Thanh Tra")

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

# Sidebar filter (findings only) (GIỮ NGUYÊN)
with st.sidebar:
    st.header("🔎 Lọc Findings")
    all_refs = sorted(df_find["legal_reference_filter"].astype(str).unique().tolist())
    selected_refs = st.multiselect("Chọn Legal_reference", options=all_refs, default=all_refs)
    f_df = df_find[df_find["legal_reference_filter"].astype(str).isin([str(x) for x in selected_refs])].copy()

    st.markdown("---")
    st.metric("💸 Tổng tiền ảnh hưởng (lọc)", format_vnd(f_df["quantified_amount"].sum()))
    st.metric("👥 Tổng hồ sơ ảnh hưởng (lọc)", f"{int(f_df['impacted_accounts'].sum()) if 'impacted_accounts' in f_df.columns and pd.notna(f_df['impacted_accounts'].sum()) else '—'}")

# ==============================
# Tabs (ĐÃ THÊM TAB CHATBOT)
# ==============================

# THÊM '🤖 Chatbot' VÀO DANH SÁCH TABS
tab_docs, tab_over, tab_find, tab_act, tab_chat = st.tabs(["📝 Documents","📊 Overalls","🚨 Findings","✅ Actions", "🤖 Chatbot"])

# ---- Chatbot Tab (GỌI HÀM MỚI) ----
with tab_chat:
    rag_chat_tab()

# ---- Documents (GIỮ NGUYÊN) ----
with tab_docs:
    st.header("Báo Cáo Kết Luận Thanh Tra (Metadata)")
    st.markdown("---")
    if len(df_docs) == 0:
        st.info("Không có dữ liệu documents.")
    else:
        for idx, row in df_docs.reset_index(drop=True).iterrows():
            st.markdown(f'<div class="doc-wrap"><div class="doc-title">📝 Báo cáo kết luận thanh tra — {str(row.get("doc_id","—"))}</div>', unsafe_allow_html=True)
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                info_card("Mã số kết luận thanh tra (Doc_id)", str(row.get("doc_id","—")))
                info_card("Đơn vị phát hành (Issuing_authority)", str(row.get("issuing_authority","—")))
                info_card("Người kiểm soát (Signer_name)", str(row.get("signer_name","—")))
            with c2:
                d = row.get("issue_date", pd.NaT)
                info_card("Ngày phát hành (Issue_date)", d.strftime("%d/%m/%Y") if pd.notna(d) else "—")
                info_card("Đơn vị được kiểm tra (inspected_entity_name)", str(row.get("inspected_entity_name","—")))
                info_card("Chức vụ (Signer_title)", str(row.get("signer_title","—")))
            with c3:
                info_card("Title", str(row.get("title","—")))
                info_card("Lĩnh vực (sector)", str(row.get("sector","—")))
            with c4:
                ps = row.get("period_start", pd.NaT); pe = row.get("period_end", pd.NaT)
                info_card("Thời gian bắt đầu (period_start)", ps.strftime("%d/%m/%Y") if pd.notna(ps) else "—")
                info_card("Thời gian kết thúc (period_end)", pe.strftime("%d/%m/%Y") if pd.notna(pe) else "—")
            st.markdown("</div>", unsafe_allow_html=True)

# ---- Overalls (GIỮ NGUYÊN) ----
with tab_over:
    st.header("Thông Tin Tổng Quan")
    st.markdown("---")
    over_row = df_over.iloc[-1] if len(df_over) else pd.Series({})

    # KPIs sơ lược
    k1,k2,k3,k4,k5 = st.columns(5)
    with k1:
        st.metric("Tổng nhân sự", f"{int(over_row.get('staff_total', np.nan)) if pd.notna(over_row.get('staff_total', np.nan)) else '—'}")
        st.metric("Mẫu kiểm tra", f"{int(over_row.get('sample_total_files', np.nan)) if pd.notna(over_row.get('sample_total_files', np.nan)) else '—'}")
    with k2:
        st.metric("Phòng nghiệp vụ (HQ)", f"{int(over_row.get('departments_at_hq_count', np.nan)) if pd.notna(over_row.get('departments_at_hq_count', np.nan)) else '—'}")
        st.metric("Phòng giao dịch", f"{int(over_row.get('transaction_offices_count', np.nan)) if pd.notna(over_row.get('transaction_offices_count', np.nan)) else '—'}")
    with k3:
        st.metric("Nguồn vốn gần nhất", format_vnd(over_row.get("mobilized_capital_vnd", np.nan)))
    with k4:
        st.metric("Dư nợ gần nhất", format_vnd(over_row.get("loans_outstanding_vnd", np.nan)))
    with k5:
        st.metric("Nợ xấu (nhóm 3-5)", format_vnd(over_row.get("npl_total_vnd", np.nan)))
        st.metric("Tỷ lệ NPL / Dư nợ", f"{over_row.get('npl_ratio_percent', np.nan):.2f}%" if pd.notna(over_row.get('npl_ratio_percent', np.nan)) else "—")
        st.metric("Tổng dư nợ đã kiểm tra", format_vnd(over_row.get("sample_outstanding_checked_vnd", np.nan)))

    st.markdown("---")

    # 1) Chất lượng tín dụng Nhóm 1–3 (Bar + Pie)
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
    c1, c2 = st.columns([2,1])
    with c1:
        fig_q_bar = make_bar(dfq, title="Bar: Quy mô theo nhóm (nhãn đậm & đổi màu)")
        st.plotly_chart(fig_q_bar, use_container_width=True)
    with c2:
        fig_q_pie = make_pie([(r["Chỉ tiêu"], r["Giá trị"]) for _, r in dfq.iterrows()], title="Pie: Cơ cấu tỷ trọng")
        st.plotly_chart(fig_q_pie, use_container_width=True)

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
    fig_t = make_bar(dft, title="Kỳ hạn (bar nhỏ, mỗi cột 1 màu)")
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
    fig_c = make_bar(dfc, title="Tiền tệ (bar nhỏ, nhãn đậm & màu)")
    st.plotly_chart(fig_c, use_container_width=True)

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
    fig_p = make_bar(dfp, title="Mục đích vay (bar nhỏ)")
    st.plotly_chart(fig_p, use_container_width=True)

    # 5) Thành phần kinh tế (luôn hiển thị cả 0)
    st.subheader("**Cơ cấu theo thành phần kinh tế**")
    eco_items = [
        ("DN Nhà nước", "strucuture_econ_state_vnd"),
        ("DN tổ chức kinh tế", "strucuture_econ_nonstate_enterprises_vnd"),
        ("DN tư nhân cá thể", "strucuture_econ_individuals_households_vnd"),
    ]
    eco_data = []
    for n, c in eco_items:
        val = over_row.get(c, np.nan) if c in df_over.columns else np.nan
        eco_data.append({"Chỉ tiêu": n, "Giá trị": 0 if pd.isna(val) else float(val)})
    dfe = pd.DataFrame(eco_data)
    fig_e = make_bar(dfe, title="Thành phần kinh tế (bar nhỏ, hiển thị 0)")
    st.plotly_chart(fig_e, use_container_width=True)

# ---- Findings (GIỮ NGUYÊN) ----
with tab_find:
    st.header("Phát hiện & Nguyên nhân (Findings)")
    st.subheader(f"Đang lọc theo: {len(selected_refs)}/{len(all_refs)} legal_reference")
    st.markdown("---")
    if f_df.empty:
        st.warning("Không có dữ liệu theo bộ lọc hiện tại.")
    else:
        col1, col2 = st.columns(2)
        with col1:
            cat_count = f_df["category"].value_counts().reset_index()
            cat_count.columns = ["Category","Count"]
            fig1 = px.bar(cat_count, x="Category", y="Count", text="Count", color="Category",
                          title="Số lần xuất hiện theo Category")
            fig1.update_traces(textposition="outside")
            fig1.update_layout(height=380, xaxis_title="", yaxis_title="Số lần")
            st.plotly_chart(fig1, use_container_width=True)
        with col2:
            cat_sub = f_df.groupby(["category","sub_category"]).size().reset_index(name="Count")
            fig2 = px.bar(cat_sub, x="category", y="Count", color="sub_category",
                          title="Category × Sub_category (số lần)", barmode="group",
                          labels={"category":"Category","sub_category":"Sub_category","Count":"Số lần"})
            fig2.update_layout(height=380)
            st.plotly_chart(fig2, use_container_width=True)

        st.markdown("---")
        st.subheader("Xu hướng theo Legal_reference (gộp RAWx → RAW)")
        legal_count = f_df["legal_reference_chart"].value_counts().reset_index()
        legal_count.columns = ["Legal_reference","Count"]
        fig3 = px.line(legal_count, x="Legal_reference", y="Count", markers=True,
                       title="Số lần xuất hiện theo Legal_reference (gộp RAWx→RAW)")
        st.plotly_chart(fig3, use_container_width=True)
        st.info("RAW = luật/quy định không được nhắc tới; ô trống đã gán RAW1, RAW2… và gộp thành RAW cho biểu đồ.")

        st.markdown("---")
        st.subheader("Tần suất từng Legal_reference (không gộp phụ lục/điểm khoản)")
        freq_tbl = f_df["legal_reference_filter"].value_counts().reset_index()
        freq_tbl.columns = ["Legal_reference","Số lần"]
        st.dataframe(freq_tbl, use_container_width=True, height=320)

        st.markdown("---")
        st.subheader("Chi tiết theo từng Sub_category")
        order_sub = f_df["sub_category"].value_counts().index.tolist()
        for sub in order_sub:
            st.markdown(f"#### 🔹 {sub}")
            sub_df = f_df[f_df["sub_category"]==sub].copy()
            sub_df["legal_reference"] = sub_df["legal_reference_filter"]
            cols_show = [c for c in ["description","legal_reference","quantified_amount","impacted_accounts","root_cause"] if c in sub_df.columns]
            sub_df = sub_df[cols_show]
            if "quantified_amount" in sub_df.columns:
                sub_df["quantified_amount"] = sub_df["quantified_amount"].apply(format_vnd)
            if "impacted_accounts" in sub_df.columns:
                sub_df["impacted_accounts"] = sub_df["impacted_accounts"].apply(lambda x: f"{int(x):,}" if pd.notna(x) else "—")
            rename = {
                "description":"Mô tả",
                "legal_reference":"Điều luật/Quy định",
                "quantified_amount":"Số tiền ảnh hưởng",
                "impacted_accounts":"Số KH/Hồ sơ",
                "root_cause":"Nguyên nhân gốc"
            }
            st.dataframe(sub_df.rename(columns=rename), use_container_width=True)

        st.markdown("---")
        st.subheader("Phân tích theo bộ luật")
        tmp = f_df.copy()
        tmp["legal_reference"] = tmp["legal_reference_filter"]
        cols = ["legal_reference"]
        if "root_cause" in tmp.columns: cols.append("root_cause")
        if "recommendation" in tmp.columns: cols.append("recommendation")
        law_tbl = tmp[cols].drop_duplicates().reset_index(drop=True)
        law_tbl = law_tbl.rename(columns={
            "legal_reference":"Legal_reference",
            "root_cause":"Root_cause",
            "recommendation":"Recommendation"
        })
        st.dataframe(law_tbl, use_container_width=True)

# ---- Actions (GIỮ NGUYÊN) ----
with tab_act:
    st.header("Biện pháp khắc phục (Actions)")
    st.markdown("---")
    if df_act is None or df_act.empty:
        st.info("Không có sheet actions hoặc thiếu cột. Cần: action_type, legal_reference, action_description, evidence_of_completion.")
    else:
        df_act_full = df_act.copy()
        df_act_full["Legal_reference"] = coalesce_series_with_raw(df_act_full["legal_reference"], prefix="RAW")
        # Chart
        if "action_type" in df_act_full.columns:
            act_count = df_act_full["action_type"].value_counts().reset_index()
            act_count.columns = ["Action_type","Count"]
            fig = px.pie(act_count, values="Count", names="Action_type", title="Phân loại tính chất biện pháp", hole=.35)
            fig.update_traces(textinfo="percent+label")
            st.plotly_chart(fig, use_container_width=True)
        st.markdown("---")
        # Table (all rows)
        cols = [c for c in ["Legal_reference","action_type","action_description","evidence_of_completion"] if c in df_act_full.columns or c=="Legal_reference"]
        rename = {
            "action_type":"Tính chất biện pháp",
            "action_description":"Nội dung công việc phải làm",
            "evidence_of_completion":"Công việc chi tiết / Minh chứng"
        }
        st.dataframe(df_act_full[cols].rename(columns=rename), use_container_width=True, height=500)

st.caption("© KLTT Dashboard • Streamlit • Altair • Plotly • Gemini (sidebar) • n8n RAG (tab)")
