%%writefile app.py
# Streamlit Dashboard for KLTT (Overall, Document, Findings, Actions) - Colab Ready
# Run in Colab:
#   1) pip install streamlit pandas plotly openpyxl pyngrok
#   2) write this file (done by this cell)
#   3) launch runner cell to expose public URL

import io
import re
from datetime import date
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="KLTT Dashboard", layout="wide")
st.title("📊 KLTT Dashboard – Overall · Document · Findings · Actions")
st.caption("Tải 1 file Excel (4 sheet) hoặc 4 file riêng biệt để xem dashboard.")

# -----------------------------
# Required columns
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

def ensure_cols(df: pd.DataFrame, cols: list):
    for c in cols:
        if c not in df.columns:
            df[c] = pd.NA
    return df

# -----------------------------
# Upload widgets
# -----------------------------
with st.expander("📥 Upload dữ liệu", expanded=True):
    c1, c2 = st.columns([1,1])
    with c1:
        file_one = st.file_uploader("Tải 1 file Excel (4 sheet: Overall, Document, Findings, Actions)",
                                    type=["xlsx"], key="one")
    with c2:
        files_multi = st.file_uploader("Hoặc chọn 4 file riêng (Overall, Document, Findings, Actions)",
                                       type=["xlsx"], accept_multiple_files=True, key="multi")

    dfs = {}
    if file_one is not None:
        xls = pd.ExcelFile(file_one)
        for name in xls.sheet_names:
            dfs[name.lower()] = xls.parse(name)
    elif files_multi:
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

# Schema-safe
overall = ensure_cols(dfs["overall"].copy(), REQ_OVERALL_COLS)
document = ensure_cols(dfs["document"].copy(), REQ_DOC_COLS)
findings = ensure_cols(dfs["findings"].copy(), REQ_FINDINGS_COLS)
actions  = ensure_cols(dfs["actions"].copy(), REQ_ACTIONS_COLS)

# Date parsing
def _to_date_cols(df, cols):
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce").dt.date
    return df

document = _to_date_cols(document, ["period_start","period_end","issue_date","created_at"])
overall  = _to_date_cols(overall, ["inspection_onsite_start","inspection_onsite_end","period_start","period_end"])
findings = _to_date_cols(findings, ["remediation_deadline","closure_date"])
actions  = _to_date_cols(actions, ["deadline","completion_date"])

# Joins for context
fa = actions.merge(findings[["finding_id","doc_id","severity","category"]],
                   left_on="related_finding_id", right_on="finding_id", how="left")
fa = fa.merge(document[["doc_id","province_city"]], on="doc_id", how="left")

# -----------------------------
# Filters
# -----------------------------
st.sidebar.header("🔎 Bộ lọc")
sel_doc = st.sidebar.multiselect("doc_id", sorted(document["doc_id"].dropna().unique()),
                                 default=list(sorted(document["doc_id"].dropna().unique())))
sel_city = st.sidebar.multiselect("province_city", sorted(document["province_city"].dropna().unique()))
sel_sev = st.sidebar.multiselect("severity (findings)", sorted(findings["severity"].dropna().unique()))
sel_cat = st.sidebar.multiselect("category (findings)", sorted(findings["category"].dropna().unique()))
sel_astatus = st.sidebar.multiselect("action status", sorted(actions["status"].dropna().unique()))

mask_find = findings["doc_id"].isin(sel_doc) if sel_doc else True
if sel_city:
    mask_find = mask_find & findings["doc_id"].isin(document.loc[document["province_city"].isin(sel_city),"doc_id"])
mask_find = mask_find & (findings["severity"].isin(sel_sev) if sel_sev else True)
mask_find = mask_find & (findings["category"].isin(sel_cat) if sel_cat else True)
filt_findings = findings[mask_find]

mask_act = actions["doc_id"].isin(sel_doc) if sel_doc else True
if sel_astatus:
    mask_act = mask_act & actions["status"].isin(sel_astatus)
filt_actions = actions[mask_act]

# -----------------------------
# KPI Row
# -----------------------------
c1, c2, c3, c4, c5 = st.columns(5)
with c1: st.metric("📄 Số văn bản", len(document[document["doc_id"].isin(sel_doc)]) if sel_doc else len(document))
with c2: st.metric("⚠️ Tổng Findings", len(filt_findings))
with c3: st.metric("🟥 Major Findings", int((filt_findings["severity"] == "major").sum()))
with c4: st.metric("🛠️ Tổng Actions", len(filt_actions))
with c5:
    done = int((filt_actions["status"] == "done").sum())
    all_a = max(1, len(filt_actions))
    st.metric("✅ Action done %", f"{done/all_a*100:.1f}%")

st.markdown("---")

# -----------------------------
# Tabs
# -----------------------------
TAB1, TAB2, TAB3 = st.tabs(["🔎 Findings", "🛠️ Actions", "📈 Overview"])

with TAB1:
    left, right = st.columns([1,1])
    with left:
        if not filt_findings.empty:
            fig1 = px.bar(
                filt_findings.groupby(["category","severity"]).size().reset_index(name="count"),
                x="category", y="count", color="severity", barmode="stack",
                title="Số lượng Findings theo Category & Severity"
            )
            st.plotly_chart(fig1, use_container_width=True)
        else:
            st.info("Không có dữ liệu findings sau filter.")
    with right:
        if not filt_findings.empty:
            tmp = filt_findings.assign(has_raw=filt_findings["notes"].fillna("").str.contains("RAW", case=False))
            pie = tmp.groupby("has_raw").size().reset_index(name="count")
            pie["has_raw"] = pie["has_raw"].map({True:"Không có căn cứ (RAW)", False:"Có căn cứ pháp lý"})
            fig2 = px.pie(pie, names="has_raw", values="count", title="Tỷ trọng Findings có/không căn cứ pháp lý")
            st.plotly_chart(fig2, use_container_width=True)
    st.subheader("📋 Bảng Findings")
    show_cols = [c for c in REQ_FINDINGS_COLS if c in filt_findings.columns]
    st.dataframe(filt_findings[show_cols].sort_values(["doc_id","severity","category","finding_id"]),
                 use_container_width=True, hide_index=True)

with TAB2:
    a = filt_actions.copy()
    today = date.today()
    a["is_overdue"] = a.apply(lambda r: (pd.notna(r.get("deadline")) and (r.get("status") != "done") and (r.get("deadline") < today)), axis=1)

    l, r = st.columns([1,1])
    with l:
        if not a.empty:
            by_st = a.groupby("status").size().reset_index(name="count")
            fig3 = px.bar(by_st, x="status", y="count", color="status", title="Phân bố trạng thái Actions")
            st.plotly_chart(fig3, use_container_width=True)
        else:
            st.info("Không có dữ liệu actions sau lọc.")
    with r:
        if not a.empty:
            st.metric("⏰ Overdue Actions", f"{int(a['is_overdue'].sum())} / {len(a)}")
            fig4 = px.pie(a, names="is_overdue", hole=0.45, title="Tỷ trọng Overdue")
            fig4.update_traces(textinfo="value+percent")
            st.plotly_chart(fig4, use_container_width=True)

    a_join = a.merge(findings[["finding_id","severity","category"]],
                     left_on="related_finding_id", right_on="finding_id", how="left")
    st.subheader("📋 Bảng Actions (kèm context Finding)")
    cols = [c for c in REQ_ACTIONS_COLS if c in a_join.columns] + ["severity","category"]
    cols = list(dict.fromkeys(cols))
    st.dataframe(a_join[cols].sort_values(["doc_id","status","action_id"]),
                 use_container_width=True, hide_index=True)

with TAB3:
    d = document.copy()
    if sel_doc: d = d[d["doc_id"].isin(sel_doc)]
    o = overall[overall["doc_id"].isin(d["doc_id"])].copy()

    def fmt_money(x):
        try: return f"{int(x):,}".replace(",", ".")
        except: return ""

    top = st.columns(4)
    with top[0]: st.metric("Tổng dư nợ (VND)", fmt_money(o["loans_outstanding_vnd"].sum()))
    with top[1]: st.metric("Tổng vốn huy động (VND)", fmt_money(o["mobilized_capital_vnd"].sum()))
    with top[2]: st.metric("Bình quân NPL (%)", f"{o['npl_ratio_percent'].astype(float).mean():.2f}" if not o.empty else "0.00")
    with top[3]: st.metric("Tổng hồ sơ mẫu", int(o["sample_total_files"].sum()) if "sample_total_files" in o else 0)

    ca, cb = st.columns([1,1])
    with ca:
        if not o.empty:
            fig5 = px.bar(o, x="doc_id", y="npl_ratio_percent", title="Tỷ lệ NPL theo doc_id", text="npl_ratio_percent")
            st.plotly_chart(fig5, use_container_width=True)
    with cb:
        if not o.empty:
            long = o.melt(id_vars=["doc_id"],
                          value_vars=["structure_term_short_vnd","structure_term_medium_long_vnd"],
                          var_name="term", value_name="amount")
            fig6 = px.bar(long, x="doc_id", y="amount", color="term", title="Cơ cấu kỳ hạn ngắn vs trung/dài hạn")
            st.plotly_chart(fig6, use_container_width=True)

    st.subheader("📄 Thông tin Document")
    showd = [c for c in REQ_DOC_COLS if c in d.columns]
    st.dataframe(d[showd].sort_values(["period_end","doc_id"], ascending=[False, True]),
                 use_container_width=True, hide_index=True)

st.markdown("\n—\nMade with ❤️ using Streamlit & Plotly – Hỗ trợ: lọc, phát hiện overdue, so sánh đa chi nhánh theo `doc_id`.")
