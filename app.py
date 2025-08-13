import streamlit as st
import pandas as pd
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from io import BytesIO
from datetime import datetime, timedelta
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

# Configuração de autenticação com Google Drive
SCOPES = ['https://www.googleapis.com/auth/drive']
CREDS_FILE = 'credentials/service-account-credentials.json'
creds = Credentials.from_service_account_file(CREDS_FILE, scopes=SCOPES)
drive_service = build('drive', 'v3', credentials=creds)

# IDs dos arquivos no Google Drive (substitua pelos IDs corretos)
DATA_FILE_ID = '1FPIRuTcFarRJzR3hfF5p9xsdvqBLJ-KQ'  # Substitua pelo ID de financas_alugueis.csv
VACANCY_FILE_ID = '1lU9CpCy_DcLH2D3fiqPKwEPp2GBmk9jV'  # Substitua pelo ID de vacancia_alugueis.csv

# Listas de categorias
RECEITA_CATEGORIAS = ["Aluguel", "Outros"]
DESPESAS_CATEGORIAS = ["Internet", "Administração", "Luz", "Água", "IPTU", "Manutenção", "Outros"]

# Função para carregar dados financeiros do Google Drive
def load_data():
    request = drive_service.files().get_media(fileId=DATA_FILE_ID)
    fh = BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
    fh.seek(0)
    return pd.read_csv(fh) if fh.getvalue() else pd.DataFrame(columns=["Data", "Apartamento", "Descrição", "Tipo", "Categoria", "Valor"])

# Função para carregar dados de vacância do Google Drive
def load_vacancy():
    request = drive_service.files().get_media(fileId=VACANCY_FILE_ID)
    fh = BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
    fh.seek(0)
    df = pd.read_csv(fh) if fh.getvalue() else pd.DataFrame(columns=["Data", "Apartamento", "Status"])
    df["Ocupado"] = df["Status"].str.lower() == "ocupado"  # Mapeia "Status" para "Ocupado" como booleano
    df["Data_Atualizacao"] = pd.to_datetime(df["Data"]).dt.date
    return df[["Apartamento", "Ocupado", "Data_Atualizacao"]]

# Função para salvar dados (localmente por enquanto, ajustar para Drive depois)
def save_data(df, file="financas_alugueis.csv"):
    df.to_csv(file, index=False, encoding='utf-8-sig')

# Função para gerar CSV com subtotais e totais
def generate_summary_csv(df):
    summary = []
    for apto in ["Comum"] + [f"Apto {i}" for i in range(1, 17)]:
        apto_data = df[df["Apartamento"] == apto]
        if not apto_data.empty:
            for tipo in ["Receita", "Despesa"]:
                tipo_data = apto_data[apto_data["Tipo"] == tipo]
                for cat in tipo_data["Categoria"].unique():
                    subtotal = tipo_data[tipo_data["Categoria"] == cat]["Valor"].sum()
                    summary.append({
                        "Apartamento": apto,
                        "Tipo": tipo,
                        "Categoria": cat,
                        "Subtotal": subtotal
                    })
    summary_df = pd.DataFrame(summary)
    total = df[df["Tipo"] == "Receita"]["Valor"].sum() - df[df["Tipo"] == "Despesa"]["Valor"].sum()
    total_row = pd.DataFrame([{
        "Apartamento": "Total Geral",
        "Tipo": "",
        "Categoria": "",
        "Subtotal": total
    }])
    summary_df = pd.concat([summary_df, total_row], ignore_index=True)
    return summary_df.to_csv(sep=",", index=False, encoding='utf-8-sig')

# Função para gerar Excel com todos os registros
def generate_full_records_excel(df):
    output = BytesIO()
    df.to_excel(output, index=False, engine='openpyxl')
    output.seek(0)
    return output

# Função para gerar PDF
def generate_pdf_report(df, vacancy_df, filtro_mes=None, filtro_ano=None, filtro_apto=None):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    c.setFont("Helvetica", 12)
    y = 750

    c.drawString(50, y, "Relatório de Aluguéis")
    y -= 30

    if filtro_mes and filtro_ano:
        c.drawString(50, y, f"Período: {filtro_mes}/{filtro_ano}")
        y -= 20
    if filtro_apto:
        c.drawString(50, y, f"Apartamento: {filtro_apto}")
        y -= 20

    total_receitas = df[df["Tipo"] == "Receita"]["Valor"].sum()
    total_despesas = df[df["Tipo"] == "Despesa"]["Valor"].sum()
    saldo = total_receitas - total_despesas
    c.drawString(50, y, f"Total Receitas: R$ {total_receitas:.2f}")
    y -= 20
    c.drawString(50, y, f"Total Despesas: R$ {total_despesas:.2f}")
    y -= 20
    c.drawString(50, y, f"Saldo: R$ {saldo:.2f}")
    y -= 30

    taxa_vacancia = (len(vacancy_df[vacancy_df["Ocupado"] == False]) / 16) * 100
    c.drawString(50, y, f"Taxa de Vacância: {taxa_vacancia:.2f}%")
    y -= 30

    c.drawString(50, y, "Resumo por Apartamento:")
    y -= 20
    for _, row in pd.DataFrame([
        {
            "Apartamento": apto,
            "Receitas": df[(df["Apartamento"] == apto) & (df["Tipo"] == "Receita")]["Valor"].sum(),
            "Despesas": df[(df["Apartamento"] == apto) & (df["Tipo"] == "Despesa")]["Valor"].sum(),
            "Status": "Ocupado" if vacancy_df[vacancy_df["Apartamento"] == apto]["Ocupado"].iloc[0] else "Vago"
        } for apto in [f"Apto {i}" for i in range(1, 17)]
    ]).iterrows():
        c.drawString(50, y, f"{row['Apartamento']}: Receitas R${row['Receitas']:.2f}, Despesas R${row['Despesas']:.2f}, {row['Status']}")
        y -= 20
        if y < 50:
            c.showPage()
            y = 750

    c.save()
    buffer.seek(0)
    return buffer

# Interface do app
st.title("Controle de Aluguéis - 16 Apartamentos")

# Estilização dos botões
st.markdown(
    """
    <style>
    div.stButton > button {
        background-color: #2E7D32; /* Verde escuro */
        color: white;
        border: none;
        padding: 5px 15px;
        border-radius: 5px;
    }
    div.stButton > button:hover {
        background-color: #1B5E20; /* Verde mais escuro ao passar o mouse */
        color: white;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# Carregar dados
df = load_data()
vacancy_df = load_vacancy()

# Filtros
st.subheader("Filtros")
col1, col2, col3 = st.columns(3)
with col1:
    filtro_mes = st.selectbox("Mês", ["Todos"] + [f"{i:02d}" for i in range(1, 13)], index=0)
with col2:
    filtro_ano = st.selectbox("Ano", ["Todos"] + [str(i) for i in range(2020, 2026)], index=0)
with col3:
    filtro_apto = st.selectbox("Apartamento", ["Todos"] + [f"Apto {i}" for i in range(1, 17)] + ["Comum"], index=0)

# Aplicar filtros
df_filtrado = df.copy()
if filtro_mes != "Todos":
    df_filtrado = df_filtrado[pd.to_datetime(df_filtrado["Data"]).dt.month == int(filtro_mes)]
if filtro_ano != "Todos":
    df_filtrado = df_filtrado[pd.to_datetime(df_filtrado["Data"]).dt.year == int(filtro_ano)]
if filtro_apto != "Todos":
    df_filtrado = df_filtrado[df_filtrado["Apartamento"] == filtro_apto]

# Inicializar estado do formulário
if "form_state" not in st.session_state:
    st.session_state.form_state = {"tipo": "Receita", "categoria": "Aluguel"}

# Formulário para entrada de receitas/despesas
st.subheader("Registrar Receita ou Despesa")
with st.form("entrada_form"):
    data = st.date_input("Data")
    apartamento = st.selectbox("Apartamento", ["Comum"] + [f"Apto {i}" for i in range(1, 17)])
    descricao = st.text_input("Descrição (ex.: Aluguel, Conta de Luz)")
    tipo = st.selectbox("Tipo", ["Receita", "Despesa"], key="tipo_select")
    categoria_options = RECEITA_CATEGORIAS if tipo == "Receita" else DESPESAS_CATEGORIAS
    categoria_index = categoria_options.index(st.session_state.form_state["categoria"]) if st.session_state.form_state["categoria"] in categoria_options else 0
    categoria = st.selectbox("Categoria", categoria_options, index=categoria_index, key="categoria_select")
    valor = st.number_input("Valor (R$)", min_value=0.0, format="%.2f")
    submit = st.form_submit_button("Adicionar")

    if submit:
        st.session_state.form_state["tipo"] = tipo
        st.session_state.form_state["categoria"] = categoria
        new_entry = pd.DataFrame({
            "Data": [data],
            "Apartamento": [apartamento],
            "Descrição": [descricao],
            "Tipo": [tipo],
            "Categoria": [categoria],
            "Valor": [valor]
        })
        df = pd.concat([df, new_entry], ignore_index=True)
        save_data(df)
        st.success("Registro adicionado com sucesso!")

# Formulário para gerenciar vacância
st.subheader("Gerenciar Vacância")
with st.form("vacancia_form", clear_on_submit=True):
    apartamento_vacancia = st.selectbox("Apartamento (Vacância)", [f"Apto {i}" for i in range(1, 17)])
    ocupado = st.checkbox("Ocupado?", value=vacancy_df[vacancy_df["Apartamento"] == apartamento_vacancia]["Ocupado"].iloc[0])
    submit_vacancia = st.form_submit_button("Atualizar Vacância")

    if submit_vacancia:
        vacancy_df.loc[vacancy_df["Apartamento"] == apartamento_vacancia, "Ocupado"] = ocupado
        vacancy_df.loc[vacancy_df["Apartamento"] == apartamento_vacancia, "Data_Atualizacao"] = datetime.now().date()
        # Para salvar no Google Drive, seria necessário atualizar o arquivo (ainda local por agora)
        save_data(vacancy_df, "vacancia_alugueis.csv")  # Salva localmente por enquanto
        st.success(f"Status de {apartamento_vacancia} atualizado!")

# Gerenciar lançamentos (editar/excluir)
st.subheader("Editar ou Excluir Lançamentos")
if not df_filtrado.empty:
    st.write("Clique em 'Atualizar Lista' após alterações para atualizar a tabela.")
    edit_buttons = []
    delete_buttons = []
    for idx, row in df_filtrado.iterrows():
        col1, col2, col3 = st.columns([4, 1, 1])
        with col1:
            st.write(f"{idx}: {row['Descrição']} - {row['Tipo']} - R${row['Valor']:.2f}")
        with col2:
            if st.button("✏️", key=f"edit_{idx}"):
                edit_buttons.append(idx)
        with col3:
            if st.button("🗑️", key=f"delete_{idx}"):
                delete_buttons.append(idx)

    if delete_buttons:
        for idx in delete_buttons:
            df = df.drop(idx).reset_index(drop=True)
            save_data(df)
            st.success(f"Lançamento {idx} excluído com sucesso!")
        st.rerun()

    if edit_buttons:
        for idx in edit_buttons:
            lancamento = df.iloc[idx]
            with st.form(f"editar_form_{idx}", clear_on_submit=True):
                edit_data = st.date_input("Data", value=pd.to_datetime(lancamento["Data"]).date())
                edit_apartamento = st.selectbox("Apartamento", ["Comum"] + [f"Apto {i}" for i in range(1, 17)], index=([f"Apto {i}" for i in range(1, 17)] + ["Comum"]).index(lancamento["Apartamento"]))
                edit_descricao = st.text_input("Descrição", value=lancamento["Descrição"])
                edit_tipo = st.selectbox("Tipo", ["Receita", "Despesa"], index=["Receita", "Despesa"].index(lancamento["Tipo"]))
                edit_categoria_options = RECEITA_CATEGORIAS if edit_tipo == "Receita" else DESPESAS_CATEGORIAS
                edit_categoria_index = edit_categoria_options.index(lancamento["Categoria"]) if lancamento["Categoria"] in edit_categoria_options else 0
                edit_categoria = st.selectbox("Categoria", edit_categoria_options, index=edit_categoria_index, key=f"categoria_edit_{idx}")
                edit_valor = st.number_input("Valor (R$)", min_value=0.0, value=float(lancamento["Valor"]), format="%.2f")
                submit_edit = st.form_submit_button("Salvar Alterações")

                if submit_edit:
                    df.iloc[idx] = {
                        "Data": edit_data,
                        "Apartamento": edit_apartamento,
                        "Descrição": edit_descricao,
                        "Tipo": edit_tipo,
                        "Categoria": edit_categoria,
                        "Valor": edit_valor
                    }
                    save_data(df)
                    st.success(f"Lançamento {idx} atualizado com sucesso!")
                    st.rerun()

    if st.button("Atualizar Lista"):
        st.rerun()

# Notificações de vacância prolongada
st.subheader("Notificações")
vagos_prolongados = vacancy_df[
    (vacancy_df["Ocupado"] == False) &
    ((datetime.now().date() - pd.to_datetime(vacancy_df["Data_Atualizacao"]).dt.date) > timedelta(days=30))
]
if not vagos_prolongados.empty:
    st.warning("Apartamentos vagos há mais de 30 dias:")
    for _, row in vagos_prolongados.iterrows():
        dias_vago = (datetime.now().date() - pd.to_datetime(row["Data_Atualizacao"]).date()).days
        st.write(f"- {row['Apartamento']}: Vago há {dias_vago} dias")

# Relatórios
st.subheader("Relatórios")
if not df_filtrado.empty:
    total_receitas = df_filtrado[df_filtrado["Tipo"] == "Receita"]["Valor"].sum()
    total_despesas = df_filtrado[df_filtrado["Tipo"] == "Despesa"]["Valor"].sum()
    saldo = total_receitas - total_despesas

    st.write(f"**Total de Receitas:** R$ {total_receitas:.2f}")
    st.write(f"**Total de Despesas:** R$ {total_despesas:.2f}")
    st.write(f"**Saldo:** R$ {saldo:.2f}")

    taxa_vacancia = (len(vacancy_df[vacancy_df["Ocupado"] == False]) / 16) * 100
    st.write(f"**Taxa de Vacância:** {taxa_vacancia:.2f}% ({len(vacancy_df[vacancy_df['Ocupado'] == False])} de 16 apartamentos vagos)")

    st.subheader("Resumo por Apartamento")
    resumo = [
        {
            "Apartamento": apto,
            "Receitas": df_filtrado[(df_filtrado["Apartamento"] == apto) & (df_filtrado["Tipo"] == "Receita")]["Valor"].sum(),
            "Despesas": df_filtrado[(df_filtrado["Apartamento"] == apto) & (df_filtrado["Tipo"] == "Despesa")]["Valor"].sum(),
            "Saldo": df_filtrado[(df_filtrado["Apartamento"] == apto) & (df_filtrado["Tipo"] == "Receita")]["Valor"].sum() -
                     df_filtrado[(df_filtrado["Apartamento"] == apto) & (df_filtrado["Tipo"] == "Despesa")]["Valor"].sum(),
            "Status": "Ocupado" if vacancy_df[vacancy_df["Apartamento"] == apto]["Ocupado"].iloc[0] else "Vago"
        } for apto in [f"Apto {i}" for i in range(1, 17)]
    ]
    resumo_df = pd.DataFrame(resumo)
    def highlight_vacant(val):
        return 'background-color: #FFCCCC' if val == "Vago" and isinstance(val, str) else ''
    styled_df = resumo_df.style.applymap(highlight_vacant, subset=['Status'])
    st.dataframe(styled_df)

    st.subheader("Gráficos")
    st.write("Receitas vs. Despesas por Categoria")
    chart_data = df_filtrado.groupby(["Tipo", "Categoria"])["Valor"].sum().unstack().fillna(0)
    st.bar_chart(chart_data)

    st.write("Vacância por Apartamento")
    vacancy_chart = vacancy_df.groupby("Ocupado").size().rename({True: "Ocupado", False: "Vago"}).reindex(["Ocupado", "Vago"], fill_value=0)
    st.bar_chart(vacancy_chart)

    pdf_buffer = generate_pdf_report(df_filtrado, vacancy_df, filtro_mes, filtro_ano, filtro_apto)
    st.download_button(
        label="Baixar Relatório em PDF",
        data=pdf_buffer,
        file_name="relatorio_alugueis.pdf",
        mime="application/pdf"
    )

# Exibir todos os registros
st.subheader("Todos os Registros")
st.dataframe(df_filtrado)

# Downloads
if not df.empty:
    st.download_button(
        label="Baixar dados financeiros como CSV",
        data=df.to_csv(index=False, encoding='utf-8-sig'),
        file_name="financas_alugueis.csv",
        mime="text/csv"
    )
    st.download_button(
        label="Baixar todos os registros (Excel)",
        data=generate_full_records_excel(df),
        file_name="todos_registros_alugueis.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    st.download_button(
        label="Baixar dados de vacância como CSV",
        data=vacancy_df.to_csv(index=False, encoding='utf-8-sig'),
        file_name="vacancia_alugueis.csv",
        mime="text/csv"
    )