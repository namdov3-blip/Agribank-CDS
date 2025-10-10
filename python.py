# Streamlit Dashboard for KLTT (Overall, Document, Findings, Actions)
# ---------------------------------------------------------------
# Features:
# - Upload either 1 Excel (4 sheets) or 4 separate Excels
# - Filters: doc_id, province_city, severity, category, status
# - KPI cards, charts (bar, pie, treemap), tables with conditional formatting
# - Overdue actions detection
#
# Run:
#   pip install streamlit pandas plotly openpyxl
#   streamlit run app.py

import io
import re
import sys
from datetime import datetime, date

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="KLTT Dashboard", layout="wide")
st.title("📊 KLTT Dashboard – Overall · Document · Findings · Actions")
st.caption("Tải 1 file Excel (4 sheet) hoặc 4 file riêng biệt để xem dashboard.")

# -----------------------------
# Helpers
# -----------------------------
REQ_FINDINGS_COLS = [
    "finding_id","doc_id","category","sub_category","description","evidence_ref",
    "severity","legal_reference","quantified_amount","currency","impacted_accounts",
    "root_cause","recommendation","remediation_deadline","responsible_party","status",
    "closure_date","notes"
]
REQ_ACTIONS_COLS = [
    "action_id","doc_id","related_finding_id","action_type","action_description",
    "legal_reference","amount","currency","deadline","responsible_party","status",
    "completion_date","evidence_of_completion"
]
REQ_DOC_COLS = [
    "doc_id","doc_code","title","doc_type","issuing_authority","issuer_unit",
    "inspected_entity_name","inspected_entity_id","sector","province_city",
    "inspection_type","inspection_scope","inspection_objectives","period_start",
    "period_end","field_coverage","issue_date","legal_basis_list","summary_findings",
    "overall_risk_rating","signer_name","signer_title","distribution_list",
    "attachments_note","created_at","source_file"
]
REQ_OVERALL_COLS = [
    "doc_id","period_start","period_end","inspection_onsite_start","inspection_onsite_end",
    "departments_at_hq_count","transaction_offices_count","staff_total",
    "mobilized_capital_vnd","loans_outstanding_vnd","npl_total_vnd","npl_ratio_percent",
    "npl_group3_vnd","npl_group4_vnd","npl_group5_vnd","structure_term_short_vnd",
    "structure_term_medium_long_vnd","structure_currency_vnd_vnd","structure_currency_fx_vnd",
    "structure_purpose_bds_flexible_vnd","structure_purpose_securities_vnd",
    "structure_purpose_consumption_vnd","structure_purpose_trade_vnd",
    "structure_purpose_other_vnd","structure_quality_group1_vnd",
    "structure_quality_group2_vnd","structure_quality_group3_vnd",
    "structure_quality_group4_vnd","structure_quality_group5_vnd","structure_econ_state_vnd",
    "structure_econ_nonstate_enterprises_vnd","structure_econ_individuals_households_vnd",
    "sample_total_files","sample_borrowers_with_outstanding","sample_outstanding_checked_vnd",
    "notes"
]

def _to_date(s):
    if pd.isna(s) or s == "":
        return pd.NaT
    try:
        return pd.to_datetime(s).date()
    except Exception:
        return pd.NaT

# -----------------------------
# Upload section
# -----------------------------
with st.expander("📥 Upload dữ liệu", expanded=True):
    colu1, colu2 = st.columns([1,1])
    with colu1:
        file_one = st.file_uploader("Tải 1 file Excel (4 sheet: Overall, Document, Findings, Actions)", type=["xlsx"], key="one")
    with colu2:
        files_multi = st.file_uploader("Hoặc chọn 4 file riêng (Overall, Document, Findings, Actions)", type=["xlsx"], accept_multiple_files=True, key="multi")

    dfs = {}

    if file_one is not None:
        xls = pd.ExcelFile(file_one)
        for name in xls.sheet_names:
            dfs[name.lower()] = xls.parse(name)
    elif files_multi:
        # Try map by filename keywords
        for f in files_multi:
            name = f.name.lower()
            if "overall" in name:
                dfs["overall"] = pd.read_excel(f)
            elif "document" in name or "documents" in name:
                dfs["document"] = pd.read_excel(f)
            elif "finding" in name:
                dfs["findings"] = pd.read_excel(f)
            elif "action" in name:
                dfs["actions"] = pd.read_excel(f)

    valid = all(k in dfs for k in ["overall","document","findings","actions"]) if dfs else False
    if not valid:
        st.info("⬆️ Hãy tải 1 file (4 sheet) **hoặc** 4 file riêng biệt để tiếp tục.")
        st.stop()

# Coerce required columns / missing-safe
for key, req_cols in {
    "overall": REQ_OVERALL_COLS,
    "document": REQ_DOC_COLS,
    "findings": REQ_FINDINGS_COLS,
    "actions": REQ_ACTIONS_COLS,
}.items():
    for c in req_cols:
        if c not in dfs[key].columns:
            dfs[key][c] = pd.NA

# Basic typing
findings = dfs["findings"].copy()
actions  = dfs["actions"].copy()
document = dfs["document"].copy()
overall  = dfs["overall"].copy()

# Date parsing
for col in ["period_start","period_end","issue_date","created_at"]:
    if col in document.columns:
        document[col] = pd.to_datetime(document[col], errors="coerce").dt.date
for col in ["inspection_onsite_start","inspection_onsite_end","period_start","period_end"]:
    if col in overall.columns:
        overall[col] = pd.to_datetime(overall[col], errors="coerce").dt.date
for col in ["remediation_deadline","closure_date"]:
    if col in findings.columns:
        findings[col] = pd.to_datetime(findings[col], errors="coerce").dt.date
for col in ["deadline","completion_date"]:
    if col in actions.columns:
        actions[col] = pd.to_datetime(actions[col], errors="coerce").dt.date

# Join helpers
findings_actions = actions.merge(findings[["finding_id","doc_id","severity","category"]],
                                 left_on="related_finding_id", right_on="finding_id", how="left",
                                 suffixes=("_act","_f"))
findings_actions = findings_actions.merge(document[["doc_id","province_city"]], on="doc_id", how="left")

# -----------------------------
# Filters
# -----------------------------
st.sidebar.header("🔎 Bộ lọc")
sel_doc = st.sidebar.multiselect("doc_id", sorted(document["doc_id"].dropna().unique()), default=list(sorted(document["doc_id"].dropna().unique())))
sel_city = st.sidebar.multiselect("province_city", sorted(document["province_city"].dropna().unique()))
sel_sev = st.sidebar.multiselect("severity (findings)", sorted(findings["severity"].dropna().unique()))
sel_cat = st.sidebar.multiselect("category (findings)", sorted(findings["category"].dropna().unique()))
sel_astatus = st.sidebar.multiselect("action status", sorted(actions["status"].dropna().unique()))

# Apply filters
mask_doc = findings["doc_id"].isin(sel_doc) if sel_doc else True
mask_city = findings["doc_id"].isin(document.loc[document["province_city"].isin(sel_city), "doc_id"]) if sel_city else True
mask_sev = findings["severity"].isin(sel_sev) if sel_sev else True
mask_cat = findings["category"].isin(sel_cat) if sel_cat else True
filt_findings = findings[mask_doc & mask_city & mask_sev & mask_cat]

mask_a = actions["doc_id"].isin(sel_doc) if sel_doc else True
if sel_astatus:
    mask_a = mask_a & actions["status"].isin(sel_astatus)

filt_actions = actions[mask_a]

# -----------------------------
# KPI Row
# -----------------------------
col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.metric("📄 Số văn bản", len(document[document["doc_id"].isin(sel_doc)]))
with col2:
    st.metric("⚠️ Tổng Findings", len(filt_findings))
with col3:
    st.metric("🟥 Major Findings", int((filt_findings["severity"] == "major").sum()))
with col4:
    st.metric("🛠️ Tổng Actions", len(filt_actions))
with col5:
    done = int((filt_actions["status"] == "done").sum())
    all_a = max(1, len(filt_actions))
    st.metric("✅ Action done %", f"{done/all_a*100:.1f}%")

st.markdown("---")

# -----------------------------
# Tabs
# -----------------------------
TAB1, TAB2, TAB3 = st.tabs(["🔎 Findings", "🛠️ Actions", "📈 Overview "])

# --- TAB 1: Findings ---
with TAB1:
    lcol, rcol = st.columns([1,1])
    with lcol:
        if not filt_findings.empty:
            fig1 = px.bar(filt_findings.groupby(["category","severity"]).size().reset_index(name="count"),
                          x="category", y="count", color="severity", barmode="stack",
                          title="Số lượng Findings theo Category & Severity")
            st.plotly_chart(fig1, use_container_width=True)
        else:
            st.info("Không có dữ liệu findings sau khi áp filter.")
    with rcol:
        if not filt_findings.empty:
            has_raw = filt_findings.assign(has_raw=filt_findings["notes"].fillna("").str.contains("RAW", case=False))
            raw_counts = has_raw.groupby("has_raw").size().reset_index(name="count")
            raw_counts["has_raw"] = raw_counts["has_raw"].map({True:"Không có căn cứ (RAW)", False:"Có căn cứ pháp lý"})
            fig2 = px.pie(raw_counts, names="has_raw", values="count", title="Tỷ trọng Findings có/không căn cứ pháp lý")
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.empty()

    st.subheader("📋 Bảng Findings")
    show_cols = [c for c in REQ_FINDINGS_COLS if c in filt_findings.columns]
    st.dataframe(filt_findings[show_cols].sort_values(["doc_id","severity","category","finding_id"]), use_container_width=True, hide_index=True)

# --- TAB 2: Actions ---
with TAB2:
    # Overdue detection
    today = date.today()
    a = filt_actions.copy()
    a["is_overdue"] = a.apply(lambda r: (pd.notna(r.get("deadline")) and (r.get("status") != "done") and (r.get("deadline") < today)), axis=1)

    lcol, rcol = st.columns([1,1])
    with lcol:
        if not a.empty:
            by_status = a.groupby("status").size().reset_index(name="count")
            fig3 = px.bar(by_status, x="status", y="count", color="status", title="Phân bố trạng thái Actions")
            st.plotly_chart(fig3, use_container_width=True)
        else:
            st.info("Không có dữ liệu actions sau lọc.")
    with rcol:
        if not a.empty:
            od_cnt = int(a["is_overdue"].sum())
            od_total = len(a)
            st.metric("⏰ Overdue Actions", f"{od_cnt} / {od_total}")
            fig4 = px.pie(a, names="is_overdue", title="Tỷ trọng Overdue", hole=0.45)
            fig4.update_traces(textinfo="value+percent")
            st.plotly_chart(fig4, use_container_width=True)

    # Join with findings for context
    a_join = a.merge(findings[["finding_id","severity","category"]], left_on="related_finding_id", right_on="finding_id", how="left")
    st.subheader("📋 Bảng Actions (kèm ngữ cảnh Finding)")
    cols = [c for c in REQ_ACTIONS_COLS if c in a_join.columns] + ["severity","category"]
    cols = list(dict.fromkeys(cols))
    st.dataframe(a_join[cols].sort_values(["doc_id","status","action_id"]), use_container_width=True, hide_index=True)

# --- TAB 3: Overview (from Overall & Document)
with TAB3:
    d = document.copy()
    if sel_doc:
        d = d[d["doc_id"].isin(sel_doc)]

    o = overall[overall["doc_id"].isin(d["doc_id"])].copy()

    top_row = st.columns(4)
    def _fmt_money(x):
        try:
            return f"{int(x):,}".replace(",", ".")
        except Exception:
            return ""

    with top_row[0]:
        st.metric("Tổng dư nợ (VND)", _fmt_money(o["loans_outstanding_vnd"].sum()))
    with top_row[1]:
        st.metric("Tổng vốn huy động (VND)", _fmt_money(o["mobilized_capital_vnd"].sum()))
    with top_row[2]:
        st.metric("Bình quân NPL (%)", f"{o['npl_ratio_percent'].astype(float).mean():.2f}")
    with top_row[3]:
        st.metric("Tổng hồ sơ mẫu", int(o["sample_total_files"].sum()))

    colA, colB = st.columns([1,1])
    with colA:
        if not o.empty:
            fig5 = px.bar(o, x="doc_id", y="npl_ratio_percent", title="Tỷ lệ NPL theo doc_id", text="npl_ratio_percent")
            st.plotly_chart(fig5, use_container_width=True)
    with colB:
        if not o.empty:
            long = o.melt(id_vars=["doc_id"], value_vars=[
                "structure_term_short_vnd","structure_term_medium_long_vnd"
            ], var_name="term", value_name="amount")
            fig6 = px.bar(long, x="doc_id", y="amount", color="term", title="Cơ cấu kỳ hạn ngắn vs trung/dài hạn")
            st.plotly_chart(fig6, use_container_width=True)

    st.subheader("📄 Thông tin Document")
    showd = [c for c in REQ_DOC_COLS if c in d.columns]
    st.dataframe(d[showd].sort_values(["period_end","doc_id"], ascending=[False, True]), use_container_width=True, hide_index=True)

st.markdown("\n—\nMade with ❤️ using Streamlit & Plotly • Hỗ trợ: lọc, phát hiện overdue, và so sánh đa chi nhánh theo `doc_id`.")
