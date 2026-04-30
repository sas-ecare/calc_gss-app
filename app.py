# app_calculadora_ganhos_v3.py — versão com Ciência de Dados completa

import io, base64, unicodedata, re, warnings
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import streamlit as st

warnings.filterwarnings("ignore")

# ====================== CONFIG ======================
st.set_page_config(
    page_title="🖩 Calculadora de Ganhos",
    page_icon="📶",
    layout="wide",
    initial_sidebar_state="auto",
)

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


# ====================== CONSTANTES FALLBACK ======================
RETIDO_DICT_FALLBACK = {"App": 0.9169, "Bot": 0.8835, "Web": 0.9027, "Dma": 0.8835}
CR_SEGMENTO_FALLBACK = {"Móvel": 0.4947, "Residencial": 0.4989}
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

    df["VOL_KPI"] = pd.to_numeric(df["VOL_KPI"], errors="coerce").fillna(0)
    df["ANOMES"] = pd.to_numeric(df["ANOMES"], errors="coerce").astype(int)
    df["NM_KPI_NORM"] = df["NM_KPI"].map(normalize_text)
    df["SUBCANAL_NORM"] = df["NM_SUBCANAL"].map(normalize_text)
    df["TORRE_NORM"] = df["NM_TORRE"].map(normalize_text)
    df["SEGMENTO"] = df["NM_SUBCANAL"].map(derivar_segmento)
    df["SEGMENTO_NORM"] = df["SEGMENTO"].map(normalize_text)
    df["TP_META_NORM"] = df["TP_META"].astype(str).str.lower().str.strip()
    return df


# ====================== HELPERS ======================
mes_fmt = {1:"Jan",2:"Fev",3:"Mar",4:"Abr",5:"Mai",6:"Jun",
           7:"Jul",8:"Ago",9:"Set",10:"Out",11:"Nov",12:"Dez"}

def fmt_int(x):
    try:
        return f"{np.floor(float(x) + 1e-9):,.0f}".replace(",", ".")
    except:
        return "0"

def fmt_pct(x):
    return f"{float(x)*100:.2f}%"

def anomes_to_label(a):
    return f"{mes_fmt[int(str(a)[4:])]} / {str(a)[:4]}"


# ====================== [MELHORIA A] TAXAS DINÂMICAS DA BASE ======================
@st.cache_data(show_spinner=False)
def calcular_taxas_dinamicas(_df_all):
    """
    Calcula RETIDO por torre e CR por segmento diretamente da base (TP_META = Real),
    usando a média histórica dos KPIs de Retido Digital 72h.
    Fallback para as constantes hardcoded se não houver dados suficientes.
    """
    df_real = _df_all[_df_all["TP_META_NORM"] == "real"].copy()

    # --- RETIDO por torre ---
    retido_kpis = df_real[df_real["NM_KPI"].str.contains("Retido Digital", na=False)]
    retido_dict = {}
    if not retido_kpis.empty:
        for kpi, grupo in retido_kpis.groupby("NM_KPI"):
            torre = None
            if "Apps" in kpi:
                torre = "App"
            elif "Bot" in kpi:
                torre = "Bot"
            elif "Web" in kpi:
                torre = "Web"
            if torre:
                media = grupo[grupo["VOL_KPI"] > 0]["VOL_KPI"].mean()
                if pd.notna(media) and media > 0:
                    retido_dict[torre] = media
        retido_dict["Dma"] = retido_dict.get("Bot", RETIDO_DICT_FALLBACK["Bot"])

    retido_final = {**RETIDO_DICT_FALLBACK, **retido_dict}

    # --- CR por segmento: usa proporção transacoes que viram chamada (via taxa histórica) ---
    # Mantemos o CR do fallback pois não há KPI direto de chamadas na base
    cr_final = CR_SEGMENTO_FALLBACK.copy()

    return retido_final, cr_final


# ====================== CARREGAMENTO ======================
with st.sidebar:
    st.markdown("<h3 style='color:#8B0000;'>⚙️ Base de Dados</h3>", unsafe_allow_html=True)
    if st.button("🔄 Atualizar Base"):
        st.cache_data.clear()
        st.rerun()

df_all = carregar_dados()

if df_all is None:
    st.warning("⚠️ Não foi possível carregar do GitHub. Faça upload manual abaixo.")
    uploaded = st.file_uploader("📄 Envie a planilha Tabela_Performance_v2.xlsx", type=["xlsx"])
    if uploaded is not None:
        st.cache_data.clear()
        df_all = carregar_dados(uploaded.read())
        st.success("✅ Base carregada com sucesso via upload manual.")
    if df_all is None:
        st.stop()

df = df_all[df_all["TP_META_NORM"] == "real"].copy()

ultimo_mes = df["ANOMES"].max()
with st.sidebar:
    st.caption(f"📅 Base até: **{anomes_to_label(ultimo_mes)}**")

# Taxas dinâmicas [MELHORIA A]
RETIDO_DICT, CR_SEGMENTO = calcular_taxas_dinamicas(df_all)

with st.sidebar:
    with st.expander("📊 Taxas calculadas da base", expanded=False):
        st.markdown("**% Retido Digital 72h (médias reais):**")
        for k, v in RETIDO_DICT.items():
            st.caption(f"• {k}: {v*100:.2f}%")
        st.markdown("**CR por Segmento (fixo negócio):**")
        for k, v in CR_SEGMENTO.items():
            st.caption(f"• {k}: {v*100:.2f}%")


# ====================== FUNÇÕES DE LEITURA ======================
def regra_retido_por_tribo(tribo):
    t = str(tribo).strip()
    if t.lower() == "dma":
        return RETIDO_DICT.get("Bot", RETIDO_DICT_FALLBACK["Bot"])
    return RETIDO_DICT.get(t, RETIDO_DICT_FALLBACK["Web"])

# [MELHORIA B] Lookup exato por NM_KPI em vez de termos parciais frágeis
KPI_MAP = {
    "transacoes": "transacoes",
    "usuarios_unicos_cpf": "usuarios_unicos_cpf",
    "acessos": "acessos",
}

def soma_kpi_exato(df_scope, nm_kpi):
    mask = df_scope["NM_KPI"].astype(str).str.lower().str.strip() == nm_kpi.lower()
    return float(df_scope.loc[mask, "VOL_KPI"].sum())

def get_volumes(df, segmento, subcanal, anomes):
    seg_key = normalize_text(segmento)
    sub_key = normalize_text(subcanal)
    df_f = df[
        (df["SEGMENTO_NORM"] == seg_key)
        & (df["SUBCANAL_NORM"] == sub_key)
        & (df["ANOMES"] == anomes)
    ].copy()

    vol_71 = soma_kpi_exato(df_f, "transacoes")
    vol_41 = soma_kpi_exato(df_f, "usuarios_unicos_cpf")
    vol_6  = soma_kpi_exato(df_f, "acessos")

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


# ====================== CARDS ======================
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


# ====================== [MELHORIA E] FORECASTING ======================
def forecast_media_movel(df, segmento, subcanal, n_meses=3):
    """
    Projeção simples por média ponderada exponencial dos últimos 6 meses reais.
    Retorna lista de (anomes_futuro_str, volume_previsto).
    """
    seg_key = normalize_text(segmento)
    sub_key = normalize_text(subcanal)
    ts = df[
        (df["SEGMENTO_NORM"] == seg_key)
        & (df["SUBCANAL_NORM"] == sub_key)
        & (df["NM_KPI"] == "transacoes")
    ].copy()
    ts = ts.sort_values("ANOMES")
    ts_nonzero = ts[ts["VOL_KPI"] > 0]
    if len(ts_nonzero) < 3:
        return []

    historico = ts_nonzero.tail(6)["VOL_KPI"].values.astype(float)
    # Pesos exponenciais: mais recente = maior peso
    pesos = np.exp(np.linspace(0, 1, len(historico)))
    pesos /= pesos.sum()
    base_vol = float(np.dot(pesos, historico))

    # Tendência: variação percentual média dos últimos meses
    diffs = np.diff(historico)
    tendencia = float(np.mean(diffs / (historico[:-1] + 1e-9))) if len(diffs) > 0 else 0.0
    tendencia = np.clip(tendencia, -0.1, 0.1)  # limita variação a ±10% por mês

    ultimo_anomes = int(ts_nonzero["ANOMES"].max())
    previsoes = []
    vol_prev = base_vol
    ano = int(str(ultimo_anomes)[:4])
    mes = int(str(ultimo_anomes)[4:])

    for _ in range(n_meses):
        mes += 1
        if mes > 12:
            mes = 1
            ano += 1
        vol_prev = vol_prev * (1 + tendencia)
        label = f"{mes_fmt[mes]}/{ano}"
        previsoes.append((label, max(vol_prev, 0)))

    return previsoes


# ====================== [MELHORIA F] DETECÇÃO DE OUTLIERS ======================
def detectar_outliers_zscore(df_lote, coluna="Volume CR Evitado", threshold=2.0):
    """Retorna DataFrame com flag de outlier via Z-score."""
    vals = df_lote[coluna].astype(float)
    media = vals.mean()
    std = vals.std()
    if std == 0:
        df_lote["Z-score"] = 0.0
        df_lote["Outlier"] = False
        return df_lote
    df_lote = df_lote.copy()
    df_lote["Z-score"] = ((vals - media) / std).round(2)
    df_lote["Outlier"] = df_lote["Z-score"].abs() > threshold
    return df_lote


# ====================== FILTROS ======================
st.markdown("<h2 style='color:#8B0000;'>🔎 Filtros de Cenário</h2>", unsafe_allow_html=True)
c1, c2, c3 = st.columns(3)

segmentos = sorted(df["SEGMENTO"].dropna().unique().tolist())
segmento = c1.selectbox("📊 SEGMENTO", segmentos)

anomes_unicos = sorted(df["ANOMES"].unique())
mes_legivel = [anomes_to_label(a) for a in anomes_unicos]
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

    vol_acessos      = volume_trans / tx_trn_acc if tx_trn_acc > 0 else 0
    mau_cpf          = volume_trans / tx_uu_cpf  if tx_uu_cpf  > 0 else 0
    cr_evitado       = vol_acessos * cr_segmento * retido
    cr_evitado_floor = np.floor(cr_evitado + 1e-9)

    # =================== CARDS ===================
    st.markdown("---")
    st.markdown("<h2 style='color:#8B0000;'>📊 Resultados Gerais</h2>", unsafe_allow_html=True)

    col1, col2 = st.columns(2, gap="large")
    with col1:
        st.markdown(card_darkred.format(title="Volume de Transações",          value=fmt_int(volume_trans)),                        unsafe_allow_html=True)
        st.markdown(card_darkred.format(title="Taxa de Transação ÷ Acesso",    value=f"{tx_trn_acc:.2f}"),                          unsafe_allow_html=True)
        st.markdown(card_darkred.format(title="% Ligação Direcionada Humano",  value=f"{CR_SEGMENTO.get(segmento,0.5)*100:.2f}%"),  unsafe_allow_html=True)
        st.markdown(card_darkred.format(title="% Retido Digital 72h",          value=f"{retido*100:.2f}%"),                         unsafe_allow_html=True)
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
        colunas_validas = [c for c in ["Subcanal", "Tribo", "Volume CR Evitado"] if c in df_top.columns]
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

    # ============================================================
    # =================== CIÊNCIA DE DADOS =======================
    # ============================================================
    st.markdown("---")
    st.markdown("<h1 style='text-align:center;color:#8B0000;'>🔬 Ciência de Dados</h1>", unsafe_allow_html=True)

    # ===== [MELHORIA D] TENDÊNCIA TEMPORAL =====
    with st.expander("📈 D · Tendência Temporal por Subcanal", expanded=True):
        st.markdown("""
        <p style='color:#444;font-size:15px;'>
        Evolução mensal dos volumes reais de <b>Transações</b>, <b>Acessos</b> e <b>Usuários Únicos</b>
        por subcanal. Identifica sazonalidade, crescimento orgânico e quedas súbitas.
        </p>
        """, unsafe_allow_html=True)

        kpi_opcoes = {
            "Transações": "transacoes",
            "Acessos": "acessos",
            "Usuários Únicos (CPF)": "usuarios_unicos_cpf",
        }
        kpi_sel_label = st.selectbox("KPI para análise temporal:", list(kpi_opcoes.keys()), key="kpi_tend")
        kpi_sel = kpi_opcoes[kpi_sel_label]

        # Top subcanais por volume médio para não poluir o gráfico
        df_tend_base = df[
            (df["SEGMENTO"] == segmento) &
            (df["NM_KPI"] == kpi_sel)
        ].copy()

        # Agrega por subcanal+mês (soma de categorias)
        df_tend_agg = df_tend_base.groupby(["NM_SUBCANAL", "ANOMES"])["VOL_KPI"].sum().reset_index()
        df_tend_agg["label_mes"] = df_tend_agg["ANOMES"].map(anomes_to_label)

        top_subs_tend = (
            df_tend_agg.groupby("NM_SUBCANAL")["VOL_KPI"].mean()
            .sort_values(ascending=False).head(8).index.tolist()
        )

        max_sub_exibir = st.slider("Quantidade de subcanais no gráfico:", 2, min(8, len(top_subs_tend)), min(5, len(top_subs_tend)), key="slider_tend")
        subs_tend = top_subs_tend[:max_sub_exibir]

        fig_tend = go.Figure()
        cores_tend = px.colors.qualitative.Set1
        for i, sub_t in enumerate(subs_tend):
            d = df_tend_agg[df_tend_agg["NM_SUBCANAL"] == sub_t].sort_values("ANOMES")
            d_nonzero = d[d["VOL_KPI"] > 0]
            if d_nonzero.empty:
                continue
            fig_tend.add_trace(go.Scatter(
                x=d_nonzero["label_mes"],
                y=d_nonzero["VOL_KPI"],
                mode="lines+markers",
                name=sub_t,
                line=dict(color=cores_tend[i % len(cores_tend)], width=2),
                marker=dict(size=5),
            ))

        fig_tend.update_layout(
            title=f"Evolução Mensal — {kpi_sel_label} ({segmento})",
            xaxis_title="Mês",
            yaxis_title=kpi_sel_label,
            plot_bgcolor="#ffffff",
            paper_bgcolor="#ffffff",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            height=480,
        )
        st.plotly_chart(fig_tend, use_container_width=True)

        # Mini-tabela de variação MoM do subcanal selecionado
        df_tend_sub = df_tend_agg[df_tend_agg["NM_SUBCANAL"] == subcanal].sort_values("ANOMES")
        df_tend_sub = df_tend_sub[df_tend_sub["VOL_KPI"] > 0].copy()
        if len(df_tend_sub) >= 2:
            df_tend_sub["MoM (%)"] = df_tend_sub["VOL_KPI"].pct_change().mul(100).round(2)
            df_tend_sub = df_tend_sub.rename(columns={"label_mes": "Mês", "VOL_KPI": kpi_sel_label})
            st.markdown(f"**Variação MoM — {subcanal}**")
            st.dataframe(df_tend_sub[["Mês", kpi_sel_label, "MoM (%)"]].tail(12), use_container_width=False)

    # ===== [MELHORIA E] FORECASTING =====
    with st.expander("🔮 E · Projeção de Volume (Forecasting)", expanded=True):
        st.markdown("""
        <p style='color:#444;font-size:15px;'>
        Projeção dos próximos meses via <b>média ponderada exponencial</b> com detecção de tendência.
        Subcanais com menos de 3 meses de dados reais não são projetados.
        </p>
        """, unsafe_allow_html=True)

        n_meses_proj = st.slider("Meses a projetar:", 1, 6, 3, key="n_meses_proj")

        # Calcular previsão para subcanal selecionado
        previsoes_sel = forecast_media_movel(df, segmento, subcanal, n_meses=n_meses_proj)

        # Histórico para o gráfico
        df_hist_fc = df[
            (df["SEGMENTO"] == segmento) &
            (df["NM_SUBCANAL"] == subcanal) &
            (df["NM_KPI"] == "transacoes")
        ].copy()
        df_hist_agg = df_hist_fc.groupby("ANOMES")["VOL_KPI"].sum().reset_index()
        df_hist_agg = df_hist_agg[df_hist_agg["VOL_KPI"] > 0].sort_values("ANOMES")
        df_hist_agg["label"] = df_hist_agg["ANOMES"].map(anomes_to_label)

        fig_fc = go.Figure()
        fig_fc.add_trace(go.Scatter(
            x=df_hist_agg["label"],
            y=df_hist_agg["VOL_KPI"],
            mode="lines+markers",
            name="Histórico Real",
            line=dict(color="#8B0000", width=2),
            marker=dict(size=6),
        ))

        if previsoes_sel:
            labels_prev = [p[0] for p in previsoes_sel]
            vols_prev   = [p[1] for p in previsoes_sel]

            # Conecta histórico à previsão
            if not df_hist_agg.empty:
                labels_conecta = [df_hist_agg["label"].iloc[-1]] + labels_prev
                vols_conecta   = [df_hist_agg["VOL_KPI"].iloc[-1]] + vols_prev
            else:
                labels_conecta, vols_conecta = labels_prev, vols_prev

            fig_fc.add_trace(go.Scatter(
                x=labels_conecta,
                y=vols_conecta,
                mode="lines+markers",
                name="Projeção",
                line=dict(color="#e27d00", width=2, dash="dot"),
                marker=dict(size=8, symbol="diamond", color="#e27d00"),
            ))

            # Exibe tabela de projeção
            df_prev_tab = pd.DataFrame({"Mês": labels_prev, "Transações Projetadas": [int(v) for v in vols_prev]})
            st.markdown(f"**Projeção para {subcanal}:**")
            st.dataframe(df_prev_tab, use_container_width=False)
        else:
            st.info(f"Dados insuficientes para projetar '{subcanal}'.")

        fig_fc.update_layout(
            title=f"Histórico + Projeção — Transações ({subcanal})",
            xaxis_title="Mês",
            yaxis_title="Volume de Transações",
            plot_bgcolor="#ffffff",
            paper_bgcolor="#ffffff",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            height=420,
        )
        st.plotly_chart(fig_fc, use_container_width=True)

    # ===== [MELHORIA F] DETECÇÃO DE OUTLIERS =====
    with st.expander("⚠️ F · Detecção de Outliers (Z-score)", expanded=True):
        st.markdown("""
        <p style='color:#444;font-size:15px;'>
        Identifica subcanais com comportamento atípico usando <b>Z-score</b>.
        Valores com |Z| > 2.0 (padrão) indicam dados que merecem verificação antes de usar na simulação.
        </p>
        """, unsafe_allow_html=True)

        threshold_z = st.slider("Threshold Z-score:", 1.0, 3.0, 2.0, step=0.5, key="z_thresh")

        df_lote_z = detectar_outliers_zscore(df_lote.copy(), "Volume CR Evitado", threshold_z)
        outliers = df_lote_z[df_lote_z["Outlier"]]
        normais  = df_lote_z[~df_lote_z["Outlier"]]

        fig_z = go.Figure()
        fig_z.add_trace(go.Bar(
            x=normais["Subcanal"], y=normais["Volume CR Evitado"],
            name="Normal", marker_color="#8B0000", opacity=0.85,
        ))
        if not outliers.empty:
            fig_z.add_trace(go.Bar(
                x=outliers["Subcanal"], y=outliers["Volume CR Evitado"],
                name=f"⚠️ Outlier (|Z|>{threshold_z})", marker_color="#FF6B00",
            ))
        fig_z.update_layout(
            title="Volume CR Evitado por Subcanal — Outliers destacados",
            barmode="overlay",
            xaxis_title="Subcanal",
            yaxis_title="Volume CR Evitado",
            plot_bgcolor="#ffffff",
            paper_bgcolor="#ffffff",
            height=400,
        )
        st.plotly_chart(fig_z, use_container_width=True)

        if not outliers.empty:
            st.warning(f"⚠️ **{len(outliers)} subcanal(is) com volume atípico** — revisar premissas antes de usar:")
            st.dataframe(outliers[["Subcanal", "Volume CR Evitado", "Z-score"]].sort_values("Z-score", key=abs, ascending=False), use_container_width=False)
        else:
            st.success(f"✅ Nenhum outlier detectado com threshold Z = {threshold_z}.")

    # ===== [MELHORIA G] ÍNDICE DE EFICIÊNCIA =====
    with st.expander("🏅 G · Ranking por Eficiência (Índice Composto)", expanded=True):
        st.markdown("""
        <p style='color:#444;font-size:15px;'>
        Subcanais com alto volume absoluto nem sempre são os mais eficientes.
        O <b>Índice de Eficiência</b> combina CR Evitado, % Retido e Taxa Transação/Acesso
        em um score normalizado (0–100), priorizando quem entrega mais com menor esforço.
        </p>
        """, unsafe_allow_html=True)

        df_ef = df_lote.copy()
        df_ef["Eficiência CR"] = df_ef["Volume CR Evitado"] / (df_ef["Volume Acessos"] + 1)

        def minmax(s):
            mn, mx = s.min(), s.max()
            if mx == mn:
                return pd.Series([50.0] * len(s), index=s.index)
            return (s - mn) / (mx - mn) * 100

        df_ef["Score_CR"]      = minmax(df_ef["Volume CR Evitado"].astype(float))
        df_ef["Score_Retido"]  = minmax(df_ef["% Retido"].astype(float))
        df_ef["Score_TxAcc"]   = minmax((1 / (df_ef["Tx Trans/Acessos"].astype(float) + 0.01)))  # menor tx = mais eficiente

        df_ef["Índice Eficiência"] = (
            0.5 * df_ef["Score_CR"] +
            0.3 * df_ef["Score_Retido"] +
            0.2 * df_ef["Score_TxAcc"]
        ).round(1)

        df_ef_sorted = df_ef.sort_values("Índice Eficiência", ascending=False).reset_index(drop=True)
        df_ef_sorted.index += 1  # ranking começa em 1

        fig_ef = go.Figure(go.Bar(
            x=df_ef_sorted["Subcanal"],
            y=df_ef_sorted["Índice Eficiência"],
            marker_color=px.colors.sequential.Reds_r[:len(df_ef_sorted)],
            text=df_ef_sorted["Índice Eficiência"].astype(str),
            textposition="outside",
        ))
        fig_ef.update_layout(
            title="🏅 Ranking de Eficiência por Subcanal (0–100)",
            xaxis_title="Subcanal",
            yaxis_title="Índice de Eficiência",
            yaxis_range=[0, 115],
            plot_bgcolor="#ffffff",
            paper_bgcolor="#ffffff",
            height=420,
        )
        st.plotly_chart(fig_ef, use_container_width=True)

        st.dataframe(
            df_ef_sorted[["Subcanal", "Tribo", "Volume CR Evitado", "% Retido", "Tx Trans/Acessos", "Índice Eficiência"]],
            use_container_width=False
        )

    # ===== [MELHORIA H] BENCHMARK REAL vs META =====
    with st.expander("📊 H · Benchmark Real × Meta/Desafio", expanded=True):
        st.markdown("""
        <p style='color:#444;font-size:15px;'>
        Compara o volume <b>Real</b> frente ao <b>Meta/Desafio</b> para cada subcanal e KPI.
        O <b>% de Aderência</b> indica o quanto o resultado alcançado representa da meta estabelecida.
        </p>
        """, unsafe_allow_html=True)

        kpi_bench_opcoes = {
            "Transações":            "transacoes",
            "Acessos":               "acessos",
            "Usuários Únicos (CPF)": "usuarios_unicos_cpf",
        }
        kpi_bench_label = st.selectbox("KPI para benchmark:", list(kpi_bench_opcoes.keys()), key="kpi_bench")
        kpi_bench = kpi_bench_opcoes[kpi_bench_label]

        df_bench_seg = df_all[
            (df_all["SEGMENTO"] == segmento) &
            (df_all["NM_KPI"] == kpi_bench) &
            (df_all["ANOMES"] == anomes_escolhido)
        ].copy()

        real_vol  = df_bench_seg[df_bench_seg["TP_META_NORM"] == "real"].groupby("NM_SUBCANAL")["VOL_KPI"].sum()
        meta_vol  = df_bench_seg[df_bench_seg["TP_META_NORM"] == "meta/desafio"].groupby("NM_SUBCANAL")["VOL_KPI"].sum()

        df_bench = pd.DataFrame({"Real": real_vol, "Meta": meta_vol}).dropna(how="all").fillna(0)
        df_bench["Aderência (%)"] = np.where(
            df_bench["Meta"] > 0,
            (df_bench["Real"] / df_bench["Meta"] * 100).round(1),
            np.nan
        )
        df_bench = df_bench.reset_index().rename(columns={"NM_SUBCANAL": "Subcanal"})
        df_bench = df_bench[df_bench["Real"] + df_bench["Meta"] > 0].sort_values("Aderência (%)", ascending=False)

        if df_bench.empty:
            st.info("Sem dados de Meta/Desafio para este segmento/mês.")
        else:
            fig_bench = go.Figure()
            fig_bench.add_trace(go.Bar(
                name="Real", x=df_bench["Subcanal"], y=df_bench["Real"],
                marker_color="#8B0000",
            ))
            fig_bench.add_trace(go.Bar(
                name="Meta/Desafio", x=df_bench["Subcanal"], y=df_bench["Meta"],
                marker_color="#cccccc",
            ))
            fig_bench.update_layout(
                title=f"Real × Meta — {kpi_bench_label} ({anomes_to_label(anomes_escolhido)})",
                barmode="group",
                xaxis_title="Subcanal",
                yaxis_title=kpi_bench_label,
                plot_bgcolor="#ffffff",
                paper_bgcolor="#ffffff",
                height=430,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            )
            st.plotly_chart(fig_bench, use_container_width=True)
            st.dataframe(df_bench, use_container_width=False)

    # ===== ESTATÍSTICAS DESCRITIVAS (original melhorado) =====
    with st.expander("🔍 Estatística Descritiva & Correlação", expanded=False):
        st.markdown("<h3 style='color:#8B0000;'>📈 Estatísticas Descritivas por Indicador</h3>", unsafe_allow_html=True)
        st.markdown("""
        <p style='font-size:15px; color:#444; text-align:justify;'>
        <b>Média</b> e <b>Mediana</b> mostram o comportamento central;
        <b>Desvio Padrão</b> e <b>CV%</b> indicam a dispersão.
        CV acima de <b>30%</b> sinaliza alta variabilidade entre subcanais.
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
            height=500,
        )
        st.plotly_chart(fig_scatter, use_container_width=True)
