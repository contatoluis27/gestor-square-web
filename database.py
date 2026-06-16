# ============================================================
# database.py
# Responsável por CRIAR e GERENCIAR o banco de dados do sistema
# ============================================================

import sqlite3

NOME_BANCO = "gestor_cotas.db"


def conectar():
    conexao = sqlite3.connect(NOME_BANCO)
    return conexao


def criar_tabelas():
    conn = conectar()
    cursor = conn.cursor()

    # ========================================================
    # TABELA 1: USUARIOS
    # ========================================================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        senha_hash TEXT NOT NULL,
        perfil TEXT NOT NULL DEFAULT 'operador',
        criado_em TEXT DEFAULT (datetime('now', 'localtime'))
    )
    """)

    # ========================================================
    # TABELA 2: FUNDOS
    # ========================================================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS fundos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cnpj TEXT NOT NULL UNIQUE,
        nome TEXT NOT NULL,
        tipo TEXT,
        ativo INTEGER DEFAULT 1,
        criado_em TEXT DEFAULT (datetime('now', 'localtime'))
    )
    """)

    # ========================================================
    # TABELA 3: COTAS
    # ========================================================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS cotas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fundo_id INTEGER NOT NULL,
        data_cota TEXT NOT NULL,
        valor_cota REAL NOT NULL,
        inserido_por INTEGER,
        inserido_em TEXT DEFAULT (datetime('now', 'localtime')),
        FOREIGN KEY (fundo_id) REFERENCES fundos(id),
        FOREIGN KEY (inserido_por) REFERENCES usuarios(id),
        UNIQUE(fundo_id, data_cota)
    )
    """)

    # ========================================================
    # TABELA 4: CARTEIRAS (relacionamento pai → filho)
    # ========================================================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS carteiras (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fundo_pai_id INTEGER NOT NULL,
        fundo_filho_id INTEGER NOT NULL,
        ativo_desde TEXT DEFAULT (date('now', 'localtime')),
        FOREIGN KEY (fundo_pai_id) REFERENCES fundos(id),
        FOREIGN KEY (fundo_filho_id) REFERENCES fundos(id),
        UNIQUE(fundo_pai_id, fundo_filho_id)
    )
    """)
    # 🗨️ UNIQUE garante que o mesmo filho não aparece duas vezes no mesmo pai
    # 🗨️ Mas permite que o mesmo filho apareça em vários pais diferentes

    # ========================================================
    # TABELA 5: AMORTIZACOES
    # ========================================================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS amortizacoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fundo_id INTEGER NOT NULL,
        data_amortizacao TEXT NOT NULL,
        valor_amortizacao REAL NOT NULL,
        observacao TEXT,
        criado_em TEXT DEFAULT (datetime('now', 'localtime')),
        FOREIGN KEY (fundo_id) REFERENCES fundos(id)
    )
    """)
    # 🗨️ Essa tabela guarda os pagamentos/amortizações
    # 🗨️ Assim o sistema consegue diferenciar queda real de distribuição

    conn.commit()
    conn.close()
    print("✅ Tabelas criadas com sucesso!")


def criar_admin_padrao():
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM usuarios WHERE perfil = 'admin'")
    if cursor.fetchone():
        conn.close()
        return

    # 🗨️ Coluna correta é senha_hash!
    cursor.execute("""
    INSERT INTO usuarios (nome, email, senha_hash, perfil)
    VALUES (?, ?, ?, ?)
    """, ("Administrador", "admin", "123", "admin"))

    conn.commit()
    conn.close()
    print("✅ Admin criado!")


def _migrar_banco():
    """🗨️ Adiciona colunas novas sem destruir dados existentes (ALTER TABLE seguro)"""
    conn = conectar()
    cursor = conn.cursor()

    migracoes = [
        # 🗨️ Formato: (tabela, coluna, definição SQL)
        ("fundos", "var_min", "REAL DEFAULT NULL"),
        ("fundos", "var_max", "REAL DEFAULT NULL"),
        ("fundos", "classe_cota", "TEXT DEFAULT 'sub'"),
    ]

    for tabela, coluna, definicao in migracoes:
        cursor.execute(f"PRAGMA table_info({tabela})")
        colunas_existentes = [row[1] for row in cursor.fetchall()]

        if coluna not in colunas_existentes:
            cursor.execute(
                f"ALTER TABLE {tabela} ADD COLUMN {coluna} {definicao}"
            )
            print(f"✅ Coluna '{coluna}' adicionada em '{tabela}'")

    conn.commit()
    conn.close()


# ============================================================
# FUNÇÕES AUXILIARES DE NEGÓCIO
# ============================================================

def buscar_classe_cota(fundo_id):
    """🗨️ Retorna a classe da cota do fundo: sub, senior ou mezanino"""
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT classe_cota
    FROM fundos
    WHERE id = ?
    """, (fundo_id,))
    row = cursor.fetchone()

    conn.close()

    if not row or not row[0]:
        return "sub"

    return str(row[0]).strip().lower()


def somar_amortizacoes(fundo_id, data_ini, data_fim):
    """
    🗨️ Soma as amortizações do fundo dentro do período informado
    🗨️ Regra: considera amortizações depois da data inicial
    🗨️ e até a data final, inclusive
    """
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT COALESCE(SUM(valor_amortizacao), 0)
    FROM amortizacoes
    WHERE fundo_id = ?
      AND data_amortizacao > ?
      AND data_amortizacao <= ?
    """, (fundo_id, data_ini, data_fim))

    total = cursor.fetchone()[0] or 0
    conn.close()
    return float(total)


def calcular_variacao_simples(valor_inicial, valor_final):
    """🗨️ Fórmula tradicional: usada principalmente para cotas sub"""
    if valor_inicial is None or valor_inicial == 0 or valor_final is None:
        return None

    return ((valor_final - valor_inicial) / valor_inicial) * 100


def calcular_variacao_ajustada(fundo_id, data_ini, data_fim, valor_inicial, valor_final):
    """
    🗨️ Calcula a variação correta da cota considerando amortização
    🗨️ Para classe 'sub': usa conta simples
    🗨️ Para 'senior' e 'mezanino': soma amortizações no período
    """
    if valor_inicial is None or valor_inicial == 0 or valor_final is None:
        return None

    classe = buscar_classe_cota(fundo_id)

    # 🗨️ Cota sub continua com cálculo simples
    if classe == "sub":
        return calcular_variacao_simples(valor_inicial, valor_final)

    # 🗨️ Cotas senior e mezanino precisam considerar amortização
    total_amort = somar_amortizacoes(fundo_id, data_ini, data_fim)

    return (((valor_final + total_amort) / valor_inicial) - 1) * 100


def listar_amortizacoes(fundo_id, data_ini=None, data_fim=None):
    """🗨️ Função auxiliar para consultar amortizações de um fundo"""
    conn = conectar()
    cursor = conn.cursor()

    query = """
    SELECT id, data_amortizacao, valor_amortizacao, observacao
    FROM amortizacoes
    WHERE fundo_id = ?
    """
    params = [fundo_id]

    if data_ini:
        query += " AND data_amortizacao >= ?"
        params.append(data_ini)

    if data_fim:
        query += " AND data_amortizacao <= ?"
        params.append(data_fim)

    query += " ORDER BY data_amortizacao ASC"

    cursor.execute(query, params)
    dados = cursor.fetchall()
    conn.close()

    return dados


def cadastrar_amortizacao(fundo_id, data_amortizacao, valor_amortizacao, observacao=""):
    """🗨️ Cadastra uma amortização manualmente no banco"""
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO amortizacoes (
        fundo_id, data_amortizacao, valor_amortizacao, observacao
    )
    VALUES (?, ?, ?, ?)
    """, (fundo_id, data_amortizacao, valor_amortizacao, observacao))

    conn.commit()
    conn.close()


def inicializar_banco():
    print("🔄 Inicializando banco de dados...")
    criar_tabelas()
    _migrar_banco()  # 🗨️ Roda migrações seguras após criar tabelas
    criar_admin_padrao()
    print("🎉 Banco de dados pronto!\n")


if __name__ == "__main__":
    inicializar_banco()