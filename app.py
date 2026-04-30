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

# Força tema light completo — funciona independente da config dark/light do usuário
st.markdown("""
    <style>
        /* ── Fundos gerais ── */
        html, body,
        [data-testid="stAppViewContainer"],
        [data-testid="stApp"],
        [data-testid="stHeader"],
        [data-testid="stToolbar"],
        .stApp,
        .main .block-container {
            background-color: #ffffff !important;
            color: #1a1a1a !important;
        }
        [data-testid="stSidebar"],
        section[data-testid="stSidebar"] > div {
            background-color: #f5f5f5 !important;
            color: #1a1a1a !important;
        }

        /* ── Texto geral ── */
        p, span, label, div, h1, h2, h3, h4, li, caption,
        [data-testid="stMarkdownContainer"] * {
            color: #1a1a1a !important;
        }

        /* ── Títulos com cor vermelha explícita não devem herdar o override ── */
        h1[style], h2[style], h3[style], p[style], div[style] {
            color: unset;   /* deixa o style inline prevalecer */
        }

        /* ── Inputs, selectbox, number_input ── */
        [data-testid="stSelectbox"] > div,
        [data-testid="stNumberInput"] > div,
        .stSelectbox label,
        .stNumberInput label {
            background-color: #ffffff !important;
            color: #1a1a1a !important;
        }
        [data-baseweb="select"] * {
            background-color: #ffffff !important;
            color: #1a1a1a !important;
        }

        /* ── Expander ── */
        [data-testid="stExpander"] {
            background-color: #fafafa !important;
            border: 1px solid #e0e0e0 !important;
        }
        [data-testid="stExpander"] summary,
        [data-testid="stExpander"] summary span {
            color: #1a1a1a !important;
        }

        /* ── Tabelas / dataframes ── */
        [data-testid="stDataFrame"] *,
        .stDataFrame * {
            background-color: #ffffff !important;
            color: #1a1a1a !important;
        }

        /* ── Caption / info ── */
        [data-testid="stCaptionContainer"],
        [data-testid="stCaptionContainer"] * {
            color: #555555 !important;
        }

        /* ── Botões ── */
        .stButton > button {
            background-color: #8B0000 !important;
            color: #ffffff !important;
            border: none !important;
        }
        .stButton > button:hover {
            background-color: #6a0000 !important;
        }

        /* ── Download button ── */
        [data-testid="stDownloadButton"] > button {
            color: #1a1a1a !important;
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
        color:#ffffff; display:flex; justify-content:space-between; align-items:center;">
            <div style="font-weight:800; font-size:18px; color:#ffffff;">{title}</div>
            <div style="font-weight:900; font-size:20px; background:#ffffff; color:#8B0000;
                        padding:6px 14px; border-radius:10px; min-width:90px;
                        text-align:center; color:#8B0000;">{value}</div>
        </div>
    """
    card_red = """
        <div style="width:460px; padding:18px 24px; margin:12px 0;
        background:linear-gradient(45deg,#b31313 0%,#d01f1f 70%,#e23a3a 100%);
        border-radius:16px; box-shadow:0 4px 10px rgba(139,0,0,.25);
        color:#ffffff; display:flex; justify-content:space-between; align-items:center;">
            <div style="font-weight:800; font-size:18px; color:#ffffff;">{title}</div>
            <div style="font-weight:900; font-size:20px; background:#ffffff; color:#b31313;
                        padding:6px 14px; border-radius:10px; min-width:90px;
                        text-align:center; color:#b31313;">{value}</div>
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
        title=dict(text="📈 Pareto - Volume de CR Evitado", font=dict(color="#1a1a1a")),
        xaxis=dict(title="Subcanais", color="#1a1a1a", tickfont=dict(color="#1a1a1a")),
        yaxis=dict(title="Volume CR Evitado", color="#1a1a1a", tickfont=dict(color="#1a1a1a")),
        yaxis2=dict(title="Acumulado %", overlaying="y", side="right", range=[0, 100],
                    color="#1a1a1a", tickfont=dict(color="#1a1a1a")),
        legend=dict(x=0.7, y=1.15, orientation="h", font=dict(color="#1a1a1a")),
        bargap=0.2,
        margin=dict(l=10, r=10, t=60, b=80),
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        font=dict(color="#1a1a1a"),
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

    # =================== ANÁLISE ESTATÍSTICA ===================
    with st.expander("🔍 Estatística & Ciência de Dados", expanded=False):
        st.markdown("---")
        st.markdown("<h2 style='color:#8B0000;'>📊🔬 Análise Estatística & Ciência de Dados</h2>", unsafe_allow_html=True)

        if not df_lote.empty:
            st.markdown("<h3 style='color:#8B0000;'>📈 Estatísticas Descritivas por Indicador</h3>", unsafe_allow_html=True)
            st.markdown("""
            <p style='font-size:15px; color:#444; text-align:justify;'>
            Esta tabela resume os principais indicadores estatísticos de cada métrica simulada.
            <b>Média</b> e <b>Mediana</b> mostram o comportamento central;
            <b>Desvio Padrão</b> e <b>Coeficiente de Variação (CV%)</b> indicam a dispersão dos dados.
            Um CV acima de <b>30%</b> sugere alta variabilidade entre os subcanais.
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
            A <b>Correlação de Pearson</b> mede a força e a direção da relação linear entre duas variáveis numéricas.
            No cenário atual, a correlação é <b>{corr:.2f}</b> → relação {interpret}.
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
                title=dict(text="🔬 Relação entre Volume de Acessos e Volume CR Evitado",
                           font=dict(color="#1a1a1a")),
                xaxis_title="Volume de Acessos",
                yaxis_title="Volume de CR Evitado",
                plot_bgcolor="#ffffff",
                paper_bgcolor="#ffffff",
                font=dict(color="#1a1a1a"),
                height=650,
            )
            st.plotly_chart(fig_scatter, use_container_width=True)
