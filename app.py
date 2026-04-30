# app_calculadora_ganhos.py - versao corrigida

import io, base64, unicodedata, re
from pathlib import Path
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ====================== CONFIG ======================
st.set_page_config(
    page_title="🖩 Calculadora de Ganhos",
    page_icon="📶",
    layout="wide",
    initial_sidebar_state="auto",
)

# Tema light - só forca background, sem sobrescrever cores de texto
st.markdown("""
    <style>
        html, body,
        [data-testid="stAppViewContainer"],
        [data-testid="stApp"],
        [data-testid="stHeader"],
        [data-testid="stToolbar"],
        section[data-testid="stSidebar"] > div,
        .stApp {
            background-color: #ffffff !important;
        }
        [data-testid="stSidebar"] {
            background-color: #f5f5f5 !important;
        }
    </style>
""", unsafe_allow_html=True)


# ====================== LOGO ======================
def _find_asset_bytes(name_candidates):
    for d in [Path.cwd(), Path.cwd() / "assets", Path.cwd() / "static"]:
        for base in name_candidates:
            for ext in [".png", ".jpg", ".jpeg", ".webp"]:
                p = d / f"{base}{ext}"
                if p.exists():
                    return p.read_bytes()
    return None

logo_bytes = _find_asset_bytes(["claro_logo_BF", "logo_claro", "claro"])
if logo_bytes:
    img_b64 = base64.b64encode(logo_bytes).decode()
    st.markdown(f"""
        <h1 style='text-align:center;color:#8B0000;font-size:54px;'>
        <img src='data:image/png;base64,{img_b64}' style='height:70px;vertical-align:middle;margin-right:10px'>
        Calculadora de Ganhos</h1>""", unsafe_allow_html=True)
else:
    st.markdown("<h1 style='text-align:center;color:#8B0000;'>🖩 Calculadora de Ganhos</h1>", unsafe_allow_html=True)

# ====================== PARÂMETROS FIXOS ======================
RETIDO_DICT = {"App": 0.9169, "Bot": 0.8835, "Web": 0.9027}
CR_SEGMENTO = {"Móvel": 0.4947, "Residencial": 0.4989}
DEFAULT_TX_UU_CPF = 12.28

# ====================== NORMALIZAÇÃO ======================
def normalize_text(s):
    if pd.isna(s):
        return ""
    s = str(s).lower().strip()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = re.sub(r"^[0-9.\-\s]+", "", s)
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()

# ====================== DERIVAR SEGMENTO ======================
def derivar_segmento(subcanal):
    """Sempre deriva do subcanal (coluna SEGMENTO pode estar zerada/corrompida)."""
    sub = str(subcanal).lower() if pd.notna(subcanal) else ""
    if any(k in sub for k in ["hfc", "dth", "res.", "residencial", "box tv"]):
        return "Residencial"
    if sub and sub != "nan":
        return "Móvel"
    return None

# ====================== BASE ======================
URL = "https://github.com/sas-ecare/calc_gss-app/raw/refs/heads/main/base/Tabela_Performance_v2.xlsx"

@st.cache_data(show_spinner=True)
def carregar_dados(uploaded_bytes=None):
    try:
        if uploaded_bytes is not None:
            df = pd.read_excel(io.BytesIO(uploaded_bytes), sheet_name="Tabela Performance")
        else:
            df = pd.read_excel(URL, sheet_name="Tabela Performance")
    except Exception:
        return None

    df = df[df["TP_META"].astype(str).str.lower().eq("real")].copy()
    df["VOL_KPI"] = pd.to_numeric(df["VOL_KPI"], errors="coerce").fillna(0)
    df["ANOMES"] = pd.to_numeric(df["ANOMES"], errors="coerce").astype(int)
    df["NM_KPI_NORM"] = df["NM_KPI"].map(normalize_text)
    df["SUBCANAL_NORM"] = df["NM_SUBCANAL"].map(normalize_text)
    df["TORRE_NORM"] = df["NM_TORRE"].map(normalize_text)

    # ✅ Sempre deriva SEGMENTO do subcanal (ignora coluna que pode estar zerada/corrompida)
    df["SEGMENTO"] = df["NM_SUBCANAL"].map(derivar_segmento)
    df["SEGMENTO_NORM"] = df["SEGMENTO"].map(normalize_text)

    return df

# ====================== CARREGAMENTO (upload fora do cache) ======================

# Sidebar com controle de cache
with st.sidebar:
    st.markdown("<h3 style='color:#8B0000;'>⚙️ Base de Dados</h3>", unsafe_allow_html=True)
    if st.button("🔄 Atualizar Base"):
        st.cache_data.clear()
        st.rerun()

df = carregar_dados()

if df is None:
    st.warning("⚠️ Não foi possível carregar do GitHub. Faça upload manual abaixo.")
    uploaded = st.file_uploader("📄 Envie a planilha Tabela_Performance_v2.xlsx", type=["xlsx"])
    if uploaded is not None:
        st.cache_data.clear()
        df = carregar_dados(uploaded.read())
        st.success("✅ Base carregada com sucesso via upload manual.")
    if df is None:
        st.stop()

mes_fmt = {1:"Jan",2:"Fev",3:"Mar",4:"Abr",5:"Mai",6:"Jun",7:"Jul",8:"Ago",9:"Set",10:"Out",11:"Nov",12:"Dez"}
ultimo_mes = df["ANOMES"].max()
with st.sidebar:
    st.caption(f"📅 Base até: **{mes_fmt[int(str(ultimo_mes)[4:])]} / {str(ultimo_mes)[:4]}**")

# ====================== HELPERS ======================
def fmt_int(x):
    try:
        return f"{np.floor(float(x) + 1e-9):,.0f}".replace(",", ".")
    except:
        return "0"

def regra_retido_por_tribo(tribo):
    if str(tribo).strip().lower() == "dma":
        return RETIDO_DICT["Bot"]
    return RETIDO_DICT.get(tribo, RETIDO_DICT["Web"])

# ====================== FUNÇÕES DE LEITURA ======================
def soma_kpi(df_scope, termos):
    mask = False
    for termo in termos:
        mask |= df_scope["NM_KPI_NORM"].str.contains(termo, case=False, na=False)
    return df_scope.loc[mask, "VOL_KPI"].sum()

def get_volumes(df, segmento, subcanal, anomes):
    seg_key = normalize_text(segmento)
    sub_key = normalize_text(subcanal)
    df_f = df[
        (df["SEGMENTO_NORM"] == seg_key)
        & (df["SUBCANAL_NORM"] == sub_key)
        & (df["ANOMES"] == anomes)
    ].copy()

    vol_71 = soma_kpi(df_f, ["transacao", "transa", "7 1"])
    vol_41 = soma_kpi(df_f, ["usuario unico", "cpf", "4 1"])
    vol_6  = soma_kpi(df_f, ["acesso", "6 "])

    return float(vol_71), float(vol_41), float(vol_6)

def tx_trn_por_acesso(vol_71, vol_6):
    if vol_71 <= 0 or vol_6 <= 0:
        return 1.75
    return max(vol_71 / vol_6, 1.0)

def tx_uu_por_cpf(vol_71, vol_41):
    if vol_71 <= 0 or vol_41 <= 0:
        return DEFAULT_TX_UU_CPF
    try:
        taxa = vol_71 / vol_41
        if not np.isfinite(taxa) or taxa <= 0:
            return DEFAULT_TX_UU_CPF
        return taxa
    except ZeroDivisionError:
        return DEFAULT_TX_UU_CPF

# ====================== FILTROS ======================
st.markdown("<h2 style='color:#8B0000;'>🔎 Filtros de Cenário</h2>", unsafe_allow_html=True)
c1, c2, c3 = st.columns(3)

segmentos = sorted(df["SEGMENTO"].dropna().unique().tolist())
segmento = c1.selectbox("📊 SEGMENTO", segmentos)

anomes_unicos = sorted(df["ANOMES"].unique())
meses_map = {1:"Jan",2:"Fev",3:"Mar",4:"Abr",5:"Mai",6:"Jun",
             7:"Jul",8:"Ago",9:"Set",10:"Out",11:"Nov",12:"Dez"}
mes_legivel = [f"{meses_map[int(str(a)[4:])]} / {str(a)[:4]}" for a in anomes_unicos]
map_anomes_legivel = dict(zip(mes_legivel, anomes_unicos))
anomes_legivel = c2.selectbox("🗓️ MÊS", mes_legivel, index=len(mes_legivel)-1)
anomes_escolhido = map_anomes_legivel[anomes_legivel]

subcanais = sorted(df.loc[df["SEGMENTO"] == segmento, "NM_SUBCANAL"].dropna().unique())
subcanal = c3.selectbox("📌 SUBCANAL", subcanais)

df_sub = df[
    (df["SEGMENTO"] == segmento) &
    (df["NM_SUBCANAL"] == subcanal) &
    (df["ANOMES"] == anomes_escolhido)
]
tribo = df_sub["NM_TORRE"].dropna().unique().tolist()[0] if not df_sub.empty else "Indefinido"

# ====================== INPUT ======================
st.markdown("---")
volume_trans = st.number_input("📥 VOLUME DE TRANSAÇÕES ESPERADO", min_value=0, value=1_000, step=1000)

# ====================== CÁLCULOS ======================
if st.button("🚀 Calcular Ganhos Potenciais"):
    vol_71, vol_41, vol_6 = get_volumes(df, segmento, subcanal, anomes_escolhido)
    tx_trn_acc  = tx_trn_por_acesso(vol_71, vol_6)
    tx_uu_cpf   = tx_uu_por_cpf(vol_71, vol_41)
    cr_segmento = CR_SEGMENTO.get(segmento, 0.50)
    retido      = regra_retido_por_tribo(tribo)

    vol_acessos     = volume_trans / tx_trn_acc if tx_trn_acc > 0 else 0
    mau_cpf         = volume_trans / tx_uu_cpf  if tx_uu_cpf  > 0 else 0
    cr_evitado      = vol_acessos * cr_segmento * retido
    cr_evitado_floor = np.floor(cr_evitado + 1e-9)

    # =================== CARDS ===================
    st.markdown("---")
    st.markdown("<h2 style='color:#8B0000;'>📊 Resultados Gerais</h2>", unsafe_allow_html=True)

    card_darkred = """
        <div style="width:460px; padding:18px 24px; margin:12px 0;
        background:darkred;
        border-radius:16px; box-shadow:0 4px 10px rgba(139,0,0,.25);
        color:#fff; display:flex; justify-content:space-between; align-items:center;">
            <div style="font-weight:800; font-size:18px;">{title}</div>
            <div style="font-weight:900; font-size:20px; background:#fff; color:#8B0000;
                        padding:6px 14px; border-radius:10px; min-width:90px;
                        text-align:center;">{value}</div>
        </div>
    """
    card_red = """
        <div style="width:460px; padding:18px 24px; margin:12px 0;
        background:linear-gradient(45deg,#b31313 0%,#d01f1f 70%,#e23a3a 100%);
        border-radius:16px; box-shadow:0 4px 10px rgba(139,0,0,.25);
        color:#fff; display:flex; justify-content:space-between; align-items:center;">
            <div style="font-weight:800; font-size:18px;">{title}</div>
            <div style="font-weight:900; font-size:20px; background:#fff; color:#b31313;
                        padding:6px 14px; border-radius:10px; min-width:90px;
                        text-align:center;">{value}</div>
        </div>
    """

    col1, col2 = st.columns(2, gap="large")

    with col1:
        st.markdown(card_darkred.format(title="Volume de Transações",           value=fmt_int(volume_trans)),                         unsafe_allow_html=True)
        st.markdown(card_darkred.format(title="Taxa de Transação ÷ Acesso",     value=f"{tx_trn_acc:.2f}"),                           unsafe_allow_html=True)
        st.markdown(card_darkred.format(title="% Ligação Direcionada Humano",   value=f"{CR_SEGMENTO.get(segmento,0.5)*100:.2f}%"),   unsafe_allow_html=True)
        st.markdown(card_darkred.format(title="% Retido Digital 72h",           value=f"{retido*100:.2f}%"),                          unsafe_allow_html=True)

    with col2:
        st.markdown(card_red.format(title="Volume Ligações Evitadas Humano", value=fmt_int(cr_evitado_floor)), unsafe_allow_html=True)
        st.markdown(card_red.format(title="Volume de Acessos",               value=fmt_int(vol_acessos)),      unsafe_allow_html=True)
        st.markdown(card_red.format(title="Volume de MAU (CPF)",             value=fmt_int(mau_cpf)),          unsafe_allow_html=True)

    st.caption("Fórmulas: Acessos = Transações ÷ (Tx Transações/Acesso).  MAU = Transações ÷ (Transações/Usuários Únicos).  CR Evitado = Acessos × CR × %Retido.")

    with st.expander("🔍 Diagnóstico de Premissas", expanded=False):
        st.markdown(f"""
        **Segmento:** {segmento}  
        **Subcanal:** {subcanal}  
        **Tribo:** {tribo}  
        **ANOMES:** {anomes_escolhido}  

        | Item | Valor |
        |------|------:|
        | Volume Transações | {fmt_int(vol_71)} |
        | Volume Usuários Únicos CPF | {fmt_int(vol_41)} |
        | Volume Acessos | {fmt_int(vol_6)} |
        | **Tx Transações/Acessos** | {tx_trn_acc:.2f} |
        | **Tx UU/CPF** | {tx_uu_cpf:.2f} |
        | CR Segmento | {cr_segmento*100:.2f}% |
        | % Retido Aplicado | {retido*100:.2f}% |
        """, unsafe_allow_html=True)

    # =================== SIMULAÇÃO TODOS OS SUBCANAIS ===================
    st.markdown("---")
    st.markdown("<h2 style='color:#8B0000;'>📄 Simulação - Todos os Subcanais</h2>", unsafe_allow_html=True)
    resultados = []
    for sub in sorted(df.loc[df["SEGMENTO"] == segmento, "NM_SUBCANAL"].dropna().unique()):
        df_i = df[
            (df["SEGMENTO"] == segmento) &
            (df["NM_SUBCANAL"] == sub) &
            (df["ANOMES"] == anomes_escolhido)
        ]
        tribo_i  = df_i["NM_TORRE"].dropna().unique().tolist()[0] if not df_i.empty else "Indefinido"
        v71, v41, v6 = get_volumes(df, segmento, sub, anomes_escolhido)
        tx_i     = tx_trn_por_acesso(v71, v6)
        tx_uu_i  = tx_uu_por_cpf(v71, v41)
        ret_i    = regra_retido_por_tribo(tribo_i)
        cr_i     = CR_SEGMENTO.get(segmento, 0.50)

        vol_acc_i = volume_trans / tx_i   if tx_i   > 0 else 0
        mau_i     = volume_trans / tx_uu_i if tx_uu_i > 0 else 0
        est_i     = np.floor((vol_acc_i * cr_i * ret_i) + 1e-9)

        resultados.append({
            "Subcanal":           sub,
            "Tribo":              tribo_i,
            "Tx Trans/Acessos":   round(tx_i, 2),
            "Tx UU/CPF":          round(tx_uu_i, 2),
            "% Retido":           round(ret_i * 100, 2),
            "% CR":               round(cr_i * 100, 2),
            "Volume Acessos":     int(vol_acc_i),
            "MAU (CPF)":          int(mau_i),
            "Volume CR Evitado":  int(est_i),
        })

    df_lote = pd.DataFrame(resultados)
    st.dataframe(df_lote, use_container_width=False)

    # =================== PARETO ===================
    st.markdown("<h2 style='color:#8B0000;'>🔎 Análise de Pareto - Potencial de Ganho</h2>", unsafe_allow_html=True)
    df_p  = df_lote.sort_values("Volume CR Evitado", ascending=False).reset_index(drop=True)
    tot   = df_p["Volume CR Evitado"].sum()
    df_p["Acumulado"]   = df_p["Volume CR Evitado"].cumsum()
    df_p["Acumulado %"] = 100 * df_p["Acumulado"] / tot if tot > 0 else 0
    df_p["Cor"]         = np.where(df_p["Acumulado %"] <= 80, "crimson", "lightgray")

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df_p["Subcanal"], y=df_p["Volume CR Evitado"],
        name="Volume CR Evitado", marker_color=df_p["Cor"]
    ))
    fig.add_trace(go.Scatter(
        x=df_p["Subcanal"], y=df_p["Acumulado %"],
        name="Acumulado %", mode="lines+markers",
        marker=dict(color="royalblue"), yaxis="y2"
    ))
    fig.update_layout(
        title="📈 Pareto - Volume de CR Evitado",
        xaxis=dict(title="Subcanais"),
        yaxis=dict(title="Volume CR Evitado"),
        yaxis2=dict(title="Acumulado %", overlaying="y", side="right", range=[0, 100]),
        legend=dict(x=0.7, y=1.15, orientation="h"),
        bargap=0.2,
        margin=dict(l=10, r=10, t=60, b=80),
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
    )
    st.plotly_chart(fig, use_container_width=True)

    # =================== INSIGHTS ===================
    df_top = df_p[df_p["Acumulado %"] <= 80].copy()

    st.markdown("<h2 style='color:#8B0000;'>🧠 Insights</h2>", unsafe_allow_html=True)
    st.markdown("**🏆 Subcanais Prioritários (Top 80%)**")

    if df_top.empty:
        st.info("Não há subcanais no Top 80% para o cenário selecionado.")
    else:
        st.markdown(f"""
        - Nesta simulação, **{len(df_top)} subcanais** representam **80%** do potencial de ganho.  
        **AÇÃO:** priorize estes subcanais para maximizar impacto.
        """)

        colunas_disp     = df_top.columns.tolist()
        colunas_desejadas = ["Subcanal", "Tribo", "Volume CR Evitado"]
        colunas_validas   = [c for c in colunas_desejadas if c in colunas_disp]
        st.dataframe(df_top[colunas_validas], use_container_width=False)

    # =================== DOWNLOAD ===================
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as w:
        df_lote.to_excel(w, sheet_name="Resultados",    index=False)
        df_top.to_excel(w,  sheet_name="Top_80_Pareto", index=False)

    st.download_button(
        "📥 Baixar Excel Completo",
        buffer.getvalue(),
        file_name="simulacao_cr.xlsx",
        mime="application/vnd.ms-excel",
    )

    # =================== ANÁLISE EXECUTIVA ===================
    st.markdown("---")
    st.markdown("<h2 style='color:#8B0000;'>📊 Visão Executiva</h2>", unsafe_allow_html=True)

    # ── 1. KPIs consolidados do mês com variação MoM ──────────────────────────
    with st.expander("📌 KPIs Consolidados do Mês + Variação vs Mês Anterior", expanded=False):
        mes_atual  = anomes_escolhido
        ano_a      = int(str(mes_atual)[:4])
        mes_a      = int(str(mes_atual)[4:])
        mes_ant_n  = mes_a - 1 if mes_a > 1 else 12
        ano_ant_n  = ano_a if mes_a > 1 else ano_a - 1
        mes_ant    = int(f"{ano_ant_n}{mes_ant_n:02d}")

        def vol_segmento(anomes_ref, kpi_termos):
            df_ref = df[
                (df["SEGMENTO"] == segmento) &
                (df["ANOMES"] == anomes_ref)
            ]
            mask = False
            for t in kpi_termos:
                mask |= df_ref["NM_KPI_NORM"].str.contains(t, case=False, na=False)
            return float(df_ref.loc[mask, "VOL_KPI"].sum())

        def delta_pct(atual, anterior):
            if anterior <= 0:
                return None
            return (atual - anterior) / anterior * 100

        def fmt_delta(pct):
            if pct is None:
                return "—"
            seta = "▲" if pct >= 0 else "▼"
            cor  = "green" if pct >= 0 else "red"
            return f"<span style='color:{cor};font-weight:700'>{seta} {abs(pct):.1f}%</span>"

        kpis_def = {
            "Transações":        ["transacao", "transa"],
            "Acessos":           ["acesso"],
            "Usuários Únicos":   ["usuario unico", "cpf"],
        }

        st.markdown(f"**Segmento:** {segmento} &nbsp;|&nbsp; **Mês:** {mes_fmt[mes_a]}/{ano_a} vs {mes_fmt[mes_ant_n]}/{ano_ant_n}")
        st.markdown("---")

        cols_kpi = st.columns(len(kpis_def))
        for col, (nome, termos) in zip(cols_kpi, kpis_def.items()):
            v_atual = vol_segmento(mes_atual, termos)
            v_ant   = vol_segmento(mes_ant,   termos)
            pct     = delta_pct(v_atual, v_ant)
            col.markdown(f"""
            <div style='text-align:center;padding:16px;background:#fafafa;
                        border-radius:12px;border:1px solid #e0e0e0;'>
                <div style='font-size:13px;color:#666;font-weight:600;'>{nome}</div>
                <div style='font-size:26px;font-weight:900;color:#8B0000;'>{fmt_int(v_atual)}</div>
                <div style='font-size:14px;margin-top:4px;'>{fmt_delta(pct)}</div>
                <div style='font-size:11px;color:#aaa;'>vs mês anterior</div>
            </div>
            """, unsafe_allow_html=True)

    # ── 2. Tendência dos últimos 6 meses ──────────────────────────────────────
    with st.expander("📈 Tendência — Últimos 6 Meses (Segmento)", expanded=False):
        meses_disp = sorted(df["ANOMES"].unique())
        idx_atual  = meses_disp.index(anomes_escolhido) if anomes_escolhido in meses_disp else len(meses_disp) - 1
        janela     = meses_disp[max(0, idx_atual - 5): idx_atual + 1]

        kpi_tend_opcoes = {
            "Transações":      ["transacao", "transa"],
            "Acessos":         ["acesso"],
            "Usuários Únicos": ["usuario unico", "cpf"],
        }
        kpi_tend_label = st.selectbox("KPI:", list(kpi_tend_opcoes.keys()), key="kpi_tend")
        kpi_tend_termos = kpi_tend_opcoes[kpi_tend_label]

        # Agrega por subcanal × mês na janela
        df_tend = df[
            (df["SEGMENTO"] == segmento) &
            (df["ANOMES"].isin(janela))
        ].copy()
        mask_tend = False
        for t in kpi_tend_termos:
            mask_tend |= df_tend["NM_KPI_NORM"].str.contains(t, case=False, na=False)
        df_tend = df_tend[mask_tend].groupby(["NM_SUBCANAL", "ANOMES"])["VOL_KPI"].sum().reset_index()
        df_tend["label"] = df_tend["ANOMES"].apply(lambda a: f"{mes_fmt[int(str(a)[4:])]}/{str(a)[:4]}")

        # Top subcanais por volume médio na janela
        top_subs = (
            df_tend.groupby("NM_SUBCANAL")["VOL_KPI"].mean()
            .sort_values(ascending=False).head(6).index.tolist()
        )

        CORES = ["#8B0000","#e05c00","#1a6fab","#2a9d2a","#9b27af","#c89b00"]
        fig_tend = go.Figure()
        for i, sub_t in enumerate(top_subs):
            d = df_tend[df_tend["NM_SUBCANAL"] == sub_t].sort_values("ANOMES")
            d = d[d["VOL_KPI"] > 0]
            if d.empty:
                continue
            fig_tend.add_trace(go.Scatter(
                x=d["label"], y=d["VOL_KPI"],
                mode="lines+markers", name=sub_t,
                line=dict(color=CORES[i % len(CORES)], width=2),
                marker=dict(size=6),
            ))
        fig_tend.update_layout(
            title=f"{kpi_tend_label} — Top subcanais ({segmento})",
            xaxis_title="Mês", yaxis_title=kpi_tend_label,
            plot_bgcolor="#ffffff", paper_bgcolor="#ffffff",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            height=420,
        )
        st.plotly_chart(fig_tend, use_container_width=True)

        # Tabela variação MoM do subcanal selecionado
        df_sub_tend = df_tend[df_tend["NM_SUBCANAL"] == subcanal].sort_values("ANOMES")
        df_sub_tend = df_sub_tend[df_sub_tend["VOL_KPI"] > 0].copy()
        if len(df_sub_tend) >= 2:
            df_sub_tend["MoM (%)"] = df_sub_tend["VOL_KPI"].pct_change().mul(100).round(1)
            st.markdown(f"**Variação mês a mês — {subcanal}**")
            st.dataframe(
                df_sub_tend[["label", "VOL_KPI", "MoM (%)"]].rename(columns={"label": "Mês", "VOL_KPI": kpi_tend_label}),
                use_container_width=False,
            )

    # ── 3. Projeção próximos 3 meses ──────────────────────────────────────────
    with st.expander("🔮 Projeção — Próximos 3 Meses", expanded=False):
        st.markdown("""
        Projeção via **média ponderada exponencial** com detecção de tendência.
        Subcanais com menos de 3 meses de dados reais não são projetados.
        """)

        def forecast_ewm(df, segmento, subcanal, n=3):
            df_ts = df[
                (df["SEGMENTO"] == segmento) &
                (df["NM_SUBCANAL"] == subcanal)
            ].copy()
            mask = False
            for t in ["transacao", "transa"]:
                mask |= df_ts["NM_KPI_NORM"].str.contains(t, case=False, na=False)
            df_ts = df_ts[mask].groupby("ANOMES")["VOL_KPI"].sum().reset_index()
            df_ts = df_ts[df_ts["VOL_KPI"] > 0].sort_values("ANOMES")
            if len(df_ts) < 3:
                return [], []

            hist   = df_ts["VOL_KPI"].values.astype(float)
            pesos  = np.exp(np.linspace(0, 1, min(6, len(hist))))
            pesos /= pesos.sum()
            base   = float(np.dot(pesos, hist[-len(pesos):]))
            diffs  = np.diff(hist[-7:])
            tend   = float(np.mean(diffs / (hist[-len(diffs)-1:-1] + 1e-9))) if len(diffs) else 0.0
            tend   = np.clip(tend, -0.10, 0.10)

            ultimo = int(df_ts["ANOMES"].max())
            ano, mes = int(str(ultimo)[:4]), int(str(ultimo)[4:])
            labels, vals, vol = [], [], base
            for _ in range(n):
                mes += 1
                if mes > 12:
                    mes, ano = 1, ano + 1
                vol = vol * (1 + tend)
                labels.append(f"{mes_fmt[mes]}/{ano}")
                vals.append(max(vol, 0))

            hist_labels = df_ts["ANOMES"].apply(
                lambda a: f"{mes_fmt[int(str(a)[4:])]}/{str(a)[:4]}"
            ).tolist()
            return (hist_labels, df_ts["VOL_KPI"].tolist()), (labels, vals)

        hist_data, prev_data = forecast_ewm(df, segmento, subcanal)

        if not prev_data or not prev_data[0]:
            st.info(f"Dados insuficientes para projetar '{subcanal}'.")
        else:
            fig_fc = go.Figure()
            fig_fc.add_trace(go.Scatter(
                x=hist_data[0], y=hist_data[1],
                mode="lines+markers", name="Histórico Real",
                line=dict(color="#8B0000", width=2), marker=dict(size=6),
            ))
            # conecta última observação à primeira projeção
            x_link = [hist_data[0][-1]] + prev_data[0]
            y_link = [hist_data[1][-1]] + prev_data[1]
            fig_fc.add_trace(go.Scatter(
                x=x_link, y=y_link,
                mode="lines+markers", name="Projeção",
                line=dict(color="#e27d00", width=2, dash="dot"),
                marker=dict(size=8, symbol="diamond", color="#e27d00"),
            ))
            fig_fc.update_layout(
                title=f"Histórico + Projeção de Transações — {subcanal}",
                xaxis_title="Mês", yaxis_title="Transações",
                plot_bgcolor="#ffffff", paper_bgcolor="#ffffff",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                height=400,
            )
            st.plotly_chart(fig_fc, use_container_width=True)

            df_prev = pd.DataFrame({"Mês": prev_data[0], "Transações Projetadas": [int(v) for v in prev_data[1]]})
            st.dataframe(df_prev, use_container_width=False)

    # ── 4. Ranking de eficiência ───────────────────────────────────────────────
    with st.expander("🏅 Ranking de Eficiência por Subcanal", expanded=False):
        st.markdown("""
        Score **0–100** combinando CR Evitado (50%), % Retido (30%) e Taxa Transação/Acesso (20%).
        Prioriza quem entrega mais impacto com menor esforço — não apenas volume absoluto.
        """)

        def minmax(s):
            mn, mx = s.min(), s.max()
            return pd.Series([50.0] * len(s), index=s.index) if mx == mn else (s - mn) / (mx - mn) * 100

        df_ef = df_lote.copy()
        df_ef["Score_CR"]     = minmax(df_ef["Volume CR Evitado"].astype(float))
        df_ef["Score_Retido"] = minmax(df_ef["% Retido"].astype(float))
        df_ef["Score_TxAcc"]  = minmax(1 / (df_ef["Tx Trans/Acessos"].astype(float) + 0.01))
        df_ef["Eficiência"]   = (
            0.5 * df_ef["Score_CR"] +
            0.3 * df_ef["Score_Retido"] +
            0.2 * df_ef["Score_TxAcc"]
        ).round(1)

        df_ef = df_ef.sort_values("Eficiência", ascending=False).reset_index(drop=True)
        df_ef.index += 1

        n_subs = len(df_ef)
        cores_ef = [
            f"hsl({int(0 + 120 * i / max(n_subs - 1, 1))},70%,40%)"
            for i in range(n_subs)
        ][::-1]  # vermelho = maior score

        fig_ef = go.Figure(go.Bar(
            x=df_ef["Subcanal"], y=df_ef["Eficiência"],
            marker_color=cores_ef,
            text=df_ef["Eficiência"].astype(str),
            textposition="outside",
        ))
        fig_ef.update_layout(
            title="🏅 Ranking de Eficiência (0–100)",
            xaxis_title="Subcanal", yaxis_title="Score",
            yaxis_range=[0, 115],
            plot_bgcolor="#ffffff", paper_bgcolor="#ffffff",
            height=420,
        )
        st.plotly_chart(fig_ef, use_container_width=True)
        st.dataframe(
            df_ef[["Subcanal", "Tribo", "Volume CR Evitado", "% Retido", "Tx Trans/Acessos", "Eficiência"]],
            use_container_width=False,
        )

    # ── 5. Alertas executivos ─────────────────────────────────────────────────
    with st.expander("⚠️ Alertas — Queda MoM e Outliers", expanded=False):
        st.markdown("Subcanais com **queda acima de 10% vs mês anterior** ou **volume atípico (Z-score > 2)**.")

        # Queda MoM por subcanal no KPI transações
        alertas = []
        for sub_a in sorted(df.loc[df["SEGMENTO"] == segmento, "NM_SUBCANAL"].dropna().unique()):
            v_at, _, _ = get_volumes(df, segmento, sub_a, mes_atual)
            v_an, _, _ = get_volumes(df, segmento, sub_a, mes_ant)
            if v_an > 0 and v_at > 0:
                queda = (v_at - v_an) / v_an * 100
                if queda <= -10:
                    alertas.append({"Subcanal": sub_a, "Mês Atual": int(v_at), "Mês Anterior": int(v_an), "Variação (%)": round(queda, 1)})

        if alertas:
            st.warning(f"⚠️ {len(alertas)} subcanal(is) com queda ≥ 10% nas transações:")
            st.dataframe(pd.DataFrame(alertas).sort_values("Variação (%)"), use_container_width=False)
        else:
            st.success("✅ Nenhum subcanal com queda ≥ 10% nas transações.")

        st.markdown("---")

        # Outliers por Z-score no CR Evitado
        vals  = df_lote["Volume CR Evitado"].astype(float)
        media = vals.mean()
        std   = vals.std()
        if std > 0:
            df_z = df_lote.copy()
            df_z["Z-score"] = ((vals - media) / std).round(2)
            outliers_z = df_z[df_z["Z-score"].abs() > 2].sort_values("Z-score", key=abs, ascending=False)
            if not outliers_z.empty:
                st.warning(f"⚠️ {len(outliers_z)} subcanal(is) com volume de CR Evitado atípico:")
                st.dataframe(outliers_z[["Subcanal", "Volume CR Evitado", "Z-score"]], use_container_width=False)
            else:
                st.success("✅ Nenhum outlier detectado no Volume CR Evitado.")

    # ── 6. Estatística descritiva & correlação (original preservado) ───────────
    with st.expander("🔍 Estatística Descritiva & Correlação", expanded=False):
        if not df_lote.empty:
            st.markdown("<h3 style='color:#8B0000;'>📈 Estatísticas Descritivas por Indicador</h3>", unsafe_allow_html=True)
            st.markdown("""
            <p style='font-size:15px; color:#444; text-align:justify;'>
            <b>Média</b> e <b>Mediana</b> mostram o comportamento central;
            <b>Desvio Padrão</b> e <b>CV%</b> indicam a dispersão.
            CV acima de <b>30%</b> sugere alta variabilidade entre os subcanais.
            </p>
            """, unsafe_allow_html=True)

            desc = df_lote[["Volume Acessos", "Volume CR Evitado"]].describe().T
            desc["CV (%)"] = (desc["std"] / desc["mean"] * 100).round(2)
            st.dataframe(desc[["mean", "50%", "std", "min", "max", "CV (%)"]], use_container_width=False)

            corr = df_lote[["Volume Acessos", "Volume CR Evitado"]].corr(method="pearson").iloc[0, 1]
            interpret = (
                "forte e positiva 📈" if corr > 0.7 else
                "moderada 📊"         if corr > 0.4 else
                "fraca 🔹"            if corr > 0.2 else
                "nula ou negativa 🔻"
            )
            st.markdown(f"""
            ### 🔗 Correlação de Pearson (Acessos × CR Evitado)
            <p style='font-size:15px; color:#444; text-align:justify;'>
            Correlação de <b>{corr:.2f}</b> → relação {interpret}.
            </p>
            """, unsafe_allow_html=True)

            fig_scatter = go.Figure()
            fig_scatter.add_trace(go.Scatter(
                x=df_lote["Volume Acessos"],
                y=df_lote["Volume CR Evitado"],
                mode="markers+text",
                text=df_lote["Subcanal"],
                textposition="top right",
                textfont=dict(size=6),
                marker=dict(size=5, color="#b31313", opacity=0.7),
            ))
            fig_scatter.update_layout(
                title="🔬 Relação entre Volume de Acessos e Volume CR Evitado",
                xaxis_title="Volume de Acessos",
                yaxis_title="Volume de CR Evitado",
                template="plotly_white",
                height=650,
            )
            st.plotly_chart(fig_scatter, use_container_width=True)
