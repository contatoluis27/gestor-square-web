import streamlit as st
from datetime import datetime, timedelta
from database import conectar
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import os # 🗨️ Para verificar se o arquivo do banco existe

# ============================================================
# CONFIGURAÇÃO INICIAL DO STREAMLIT
# ============================================================
st.set_page_config(
    page_title="Gestor Square Web",
    page_icon="📊", # 🗨️ Ícone que aparece na aba do navegador
    layout="wide",   # 🗨️ Usa a largura total da tela
    initial_sidebar_state="expanded" # 🗨️ Barra lateral expandida por padrão
)

# 🗨️ Adicione um título principal com um ícone
st.title("📊 Gestor Square - Relatórios Web")

# 🗨️ Adicione um logo (opcional, se tiver um arquivo logo.png no GitHub)
# from PIL import Image
# try:
# logo = Image.open("logo.png") # 🗨️ Assumindo que você tem uma pasta assets
# st.image(logo, width=100)
# except FileNotFoundError:
# st.warning("Logo não encontrado em 'assets/logo.png'.")

# ============================================================
# FUNÇÕES AUXILIARES (do seu tela_relatorios.py)
# ============================================================

def _calc_var(atual, anterior):
    if anterior is None or anterior == 0:
        return None
    return ((atual - anterior) / anterior) * 100

def _fmt_var(var):
    if var is None:
        return "—"
    sinal = "+" if var >= 0 else ""
    return f"{sinal}{var:.4f}%"

def _fmt_moeda(valor):
    if valor is None:
        return "—"
    return f"R$ {valor:,.6f}".replace(",", "X").replace(".", ",").replace("X", ".")

def _buscar_dados_geral(data_ref):
    """🗨️ Adapta a lógica de busca da aba Geral para retornar um DataFrame"""
    dados_para_df = []
    data_ref_bd = data_ref.strftime("%Y-%m-%d")

    conn   = conectar()
    cursor = conn.cursor()
    cursor.execute("SELECT id, nome FROM fundos WHERE ativo = 1 ORDER BY nome")
    fundos = cursor.fetchall()

    if not fundos:
        conn.close()
        return pd.DataFrame(columns=["Nome do Fundo", "Data da Cota", "Var. Dia", "Var. Mês", "Var. Ano"])

    for fundo_id, nome in fundos:
        cursor.execute("""
            SELECT valor_cota, data_cota FROM cotas
            WHERE fundo_id = ? AND data_cota <= ?
            ORDER BY data_cota DESC LIMIT 1
        """, (fundo_id, data_ref_bd))
        ref = cursor.fetchone()

        if not ref:
            dados_para_df.append([nome, "—", "—", "—", "—"])
            continue

        val_ref, data_cota_real = ref

        cursor.execute("""
            SELECT valor_cota FROM cotas
            WHERE fundo_id = ? AND data_cota < ?
            ORDER BY data_cota DESC LIMIT 1
        """, (fundo_id, data_cota_real))
        ant = cursor.fetchone()
        var_dia = _calc_var(val_ref, ant[0] if ant else None)

        primeiro_mes = data_ref.replace(day=1).strftime("%Y-%m-%d")
        cursor.execute("""
            SELECT valor_cota FROM cotas
            WHERE fundo_id = ?
              AND data_cota >= ? AND data_cota <= ?
            ORDER BY data_cota ASC LIMIT 1
        """, (fundo_id, primeiro_mes, data_ref_bd))
        ini_mes = cursor.fetchone()
        var_mes = _calc_var(val_ref, ini_mes[0] if ini_mes else None)

        primeiro_ano = data_ref.replace(
            month=1, day=1
        ).strftime("%Y-%m-%d")
        cursor.execute("""
            SELECT valor_cota FROM cotas
            WHERE fundo_id = ?
              AND data_cota >= ? AND data_cota <= ?
            ORDER BY data_cota ASC LIMIT 1
        """, (fundo_id, primeiro_ano, data_ref_bd))
        ini_ano = cursor.fetchone()
        var_ano = _calc_var(val_ref, ini_ano[0] if ini_ano else None)

        data_fmt = datetime.strptime(
            data_cota_real, "%Y-%m-%d"
        ).strftime("%d/%m/%Y")
        if data_cota_real != data_ref_bd:
            data_fmt += " *"

        dados_para_df.append([
            nome,
            data_fmt,
            _fmt_var(var_dia),
            _fmt_var(var_mes),
            _fmt_var(var_ano),
        ])

    conn.close()
    return pd.DataFrame(dados_para_df, columns=["Nome do Fundo", "Data da Cota", "Var. Dia", "Var. Mês", "Var. Ano"])

def _carregar_mapa_fundos():
    """🗨️ Carrega o mapa de fundos para os combos"""
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT f.id, f.nome
        FROM fundos f
        INNER JOIN cotas c ON c.fundo_id = f.id
        WHERE f.ativo = 1 ORDER BY f.nome
    """)
    fundos = cursor.fetchall()
    conn.close()
    return {nome: id_f for id_f, nome in fundos}

def _buscar_cotas_grafico(fundo_id, periodo_str, data_ini_personalizada=None, data_fim_personalizada=None):
    """🗨️ Busca cotas para o gráfico"""
    hoje = datetime.today()
    data_ini = None
    data_fim = None

    if periodo_str == "Personalizado":
        data_ini = data_ini_personalizada
        data_fim = data_fim_personalizada
    else:
        mapa = {
            "Últimos 30 dias": hoje - timedelta(days=30),
            "Últimos 3 meses": hoje - timedelta(days=90),
            "Últimos 6 meses": hoje - timedelta(days=180),
            "Último ano":      hoje - timedelta(days=365),
            "Tudo":            None,
        }
        data_ini = mapa.get(periodo_str)
        data_fim = hoje

    query  = "SELECT data_cota, valor_cota FROM cotas WHERE fundo_id = ?"
    params = [fundo_id]

    if data_ini:
        query += " AND data_cota >= ?"
        params.append(data_ini.strftime("%Y-%m-%d"))
    if data_fim:
        query += " AND data_cota <= ?"
        params.append(data_fim.strftime("%Y-%m-%d"))
    query += " ORDER BY data_cota ASC"

    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(query, params)
    cotas = cursor.fetchall()
    conn.close()
    return cotas

# ============================================================
# INTERFACE STREAMLIT
# ============================================================

# 🗨️ Cria abas para organizar o conteúdo
tab1, tab2, tab3 = st.tabs(["🌐 Geral", "📈 Gráfico", "🆚 Comparação"])

# --- ABA GERAL ---
with tab1:
    st.header("Visão consolidada de todos os fundos")

    col1, col2 = st.columns([0.3, 0.7])

    with col1:
        data_ref_geral = st.date_input(
            "Data de referência:",
            value=datetime.today(),
            format="DD/MM/YYYY"
        )
        st.info("* cota anterior ao dia selecionado")

    with col2:
        st.write("---") # 🗨️ Espaçador visual
        if st.button("🔄 Atualizar Tabela Geral"):
            st.session_state['dados_geral'] = _buscar_dados_geral(data_ref_geral)
            st.success("Tabela atualizada!")

    # 🗨️ Inicializa o estado da sessão para os dados da tabela
    if 'dados_geral' not in st.session_state:
        st.session_state['dados_geral'] = _buscar_dados_geral(datetime.today())

    st.subheader("Tabela de Fundos")
    st.dataframe(st.session_state['dados_geral'], use_container_width=True, hide_index=True)

    st.subheader("Exportar Dados")
    col_exp1, col_exp2, col_exp3 = st.columns(3)

    with col_exp1:
        if st.button("📊 Exportar para Excel (Geral)"):
            if not st.session_state['dados_geral'].empty:
                # 🗨️ Para exportar para Excel, precisamos de uma biblioteca como xlsxwriter
                # e criar o arquivo em memória. Streamlit não tem um 'exportar_excel' direto.
                # Vamos simular com CSV por enquanto, ou você pode integrar sua função exportador.py
                # Para integrar exportador.py, você precisaria salvar o arquivo temporariamente
                # e depois oferecer para download.
                csv = st.session_state['dados_geral'].to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="Download Excel (CSV)", # 🗨️ Mudado para CSV para simplicidade
                    data=csv,
                    file_name=f"relatorio_geral_{data_ref_geral.strftime('%d%m%Y')}.csv",
                    mime="text/csv"
                )
            else:
                st.warning("Nenhum dado para exportar!")
    with col_exp2:
        st.write("PDF e Imagem exigem mais customização para Streamlit.")
    with col_exp3:
        st.write("---") # 🗨️ Espaçador

# --- ABA GRÁFICO ---
with tab2:
    st.header("Gráfico de Performance de Fundo")

    mapa_fundos = _carregar_mapa_fundos()
    nomes_fundos = list(mapa_fundos.keys())

    if not nomes_fundos:
        st.warning("Nenhum fundo cadastrado ou com cotas para exibir gráficos.")
    else:
        col_g1, col_g2 = st.columns([0.4, 0.6])

        with col_g1:
            fundo_selecionado_nome = st.selectbox(
                "Selecione o Fundo:",
                options=nomes_fundos,
                key="fundo_grafico_select"
            )
            fundo_id_grafico = mapa_fundos.get(fundo_selecionado_nome)

            periodo_grafico = st.selectbox(
                "Selecione o Período:",
                options=["Últimos 30 dias", "Últimos 3 meses",
                         "Últimos 6 meses", "Último ano",
                         "Tudo", "Personalizado"],
                key="periodo_grafico_select"
            )

            data_ini_grafico = None
            data_fim_grafico = None
            if periodo_grafico == "Personalizado":
                data_ini_grafico = st.date_input("Data de Início:", value=datetime.today() - timedelta(days=30), format="DD/MM/YYYY")
                data_fim_grafico = st.date_input("Data de Fim:", value=datetime.today(), format="DD/MM/YYYY")

            st.subheader("Escala do Gráfico")
            col_y1, col_y2 = st.columns(2)
            with col_y1:
                y_min_str = st.text_input("Mínimo Y (ex: 1.000000)", value="", key="y_min_grafico")
            with col_y2:
                y_max_str = st.text_input("Máximo Y (ex: 1.000000)", value="", key="y_max_grafico")

            intervalo_x = st.selectbox(
                "Intervalo do Eixo X:",
                options=["Auto", "Diário", "Semanal", "Quinzenal", "Mensal", "Bimestral"],
                key="intervalo_x_grafico"
            )

            if st.button("🔄 Atualizar Gráfico"):
                cotas_grafico = _buscar_cotas_grafico(
                    fundo_id_grafico, periodo_grafico,
                    data_ini_grafico, data_fim_grafico
                )
                if cotas_grafico:
                    st.session_state['cotas_grafico'] = cotas_grafico
                    st.session_state['fundo_grafico_nome'] = fundo_selecionado_nome
                    st.session_state['periodo_grafico_display'] = periodo_grafico
                    st.session_state['y_min_grafico_val'] = float(y_min_str.replace(",", ".")) if y_min_str else None
                    st.session_state['y_max_grafico_val'] = float(y_max_str.replace(",", ".")) if y_max_str else None
                    st.session_state['intervalo_x_grafico_val'] = intervalo_x
                else:
                    st.warning("Nenhuma cota encontrada para o período selecionado.")
                    st.session_state['cotas_grafico'] = []

        with col_g2:
            st.subheader("Cards de Desempenho")
            if 'cotas_grafico' in st.session_state and st.session_state['cotas_grafico']:
                cotas = st.session_state['cotas_grafico']
                valores = [c[1] for c in cotas]
                ultima = valores[-1]
                primeira = valores[0]

                rent = _calc_var(ultima, primeira)
                txt_rent = _fmt_var(rent) if rent is not None else "—"

                col_card1, col_card2, col_card3 = st.columns(3)
                with col_card1:
                    st.metric("💰 Última Cota", _fmt_moeda(ultima))
                with col_card2:
                    st.metric("📈 Rentabilidade", txt_rent)
                with col_card3:
                    st.metric("📋 Registros", len(valores))

                col_card4, col_card5 = st.columns(2)
                with col_card4:
                    st.metric("📉 Menor Cota", _fmt_moeda(min(valores)))
                with col_card5:
                    st.metric("📈 Maior Cota", _fmt_moeda(max(valores)))

                st.subheader("Gráfico de Cotações")
                datas = [datetime.strptime(c[0], "%Y-%m-%d") for c in cotas]
                valores = [c[1] for c in cotas]

                plt.style.use("dark_background")
                fig, ax = plt.subplots(figsize=(10, 5), dpi=100)
                fig.patch.set_facecolor("#2b2b2b")
                ax.set_facecolor("#2b2b2b")

                ax.plot(datas, valores, color="#4a9eff", linewidth=2,
                        marker="o", markersize=3, markerfacecolor="#ffffff", zorder=3)
                ax.fill_between(datas, valores, alpha=0.15, color="#4a9eff")
                ax.axhline(y=valores[0], color="#888888", linewidth=0.8,
                           linestyle="--",
                           label=f"Início: {_fmt_moeda(valores[0])}")

                y_min = st.session_state.get('y_min_grafico_val')
                y_max = st.session_state.get('y_max_grafico_val')
                if y_min is not None or y_max is not None:
                    ax.set_ylim(
                        bottom=y_min if y_min is not None else min(valores)*0.995,
                        top=y_max    if y_max is not None else max(valores)*1.005
                    )

                intervalo = st.session_state.get('intervalo_x_grafico_val')
                mapa_x = {
                    "Diário":    mdates.DayLocator(interval=1),
                    "Semanal":   mdates.WeekdayLocator(interval=1),
                    "Quinzenal": mdates.DayLocator(interval=15),
                    "Mensal":    mdates.MonthLocator(interval=1),
                    "Bimestral": mdates.MonthLocator(interval=2),
                }
                if intervalo in mapa_x:
                    ax.xaxis.set_major_locator(mapa_x[intervalo])

                ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m/%y"))
                fig.autofmt_xdate(rotation=35)
                ax.yaxis.set_major_formatter(
                    plt.FuncFormatter(
                        lambda x, _: _fmt_moeda(x)
                    )
                )
                ax.grid(True, linestyle="--", alpha=0.2, color="#888888")
                ax.tick_params(colors="#cccccc", labelsize=8)
                for spine in ax.spines.values():
                    spine.set_edgecolor("#444444")
                ax.legend(fontsize=9, facecolor="#3a3a3a",
                          edgecolor="#555555", labelcolor="#cccccc")

                ax.set_title(
                    f"{st.session_state['fundo_grafico_nome']}  —  {st.session_state['periodo_grafico_display']}",
                    color="#ffffff", fontsize=11, pad=10
                )
                plt.tight_layout()
                st.pyplot(fig)
                plt.close(fig) # 🗨️ Fecha a figura para liberar memória
            else:
                st.info("Selecione um fundo e clique em 'Atualizar Gráfico' para ver os dados.")

# --- ABA COMPARAÇÃO (Vazia por enquanto, para você preencher) ---
with tab3:
    st.header("Comparação de Fundos")
    st.info("Esta aba será desenvolvida em breve para comparar múltiplos fundos.")
    # 🗨️ Aqui você pode adicionar a lógica da sua aba de comparação,
    # usando os mesmos princípios de seleção de fundos, período e exibição de dados/gráficos.
