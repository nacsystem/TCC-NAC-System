"""
NAC System - backend em Flask (API + páginas do frontend)
Local usa SQLite, online usa PostgreSQL (variável DATABASE_URL)
"""

import hashlib
import math
import os
import re
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Flask, g, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash

# pastas do projeto
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(BACKEND_DIR)
FRONTEND_DIR = os.path.join(RAIZ, "frontend")

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
USA_POSTGRES = bool(DATABASE_URL)
DB_PATH = os.environ.get("NAC_DB_PATH", os.path.join(RAIZ, "nac-dados.db"))

TOKEN_HORAS = 12          # duração do login
MAX_FALHAS = 5            # erros de senha até bloquear
BLOQUEIO_MIN = 15         # minutos de bloqueio

SENHA_REGEX = re.compile(r"[0-9]{1,8}")
NUMERO_SALA_REGEX = re.compile(r"[0-9]{1,4}")

try:
    from zoneinfo import ZoneInfo

    FUSO = ZoneInfo(os.environ.get("NAC_TZ", "America/Sao_Paulo"))
except Exception:  # sem tzdata usa UTC-3 fixo
    FUSO = timezone(timedelta(hours=-3))


app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024

# atrás de proxy (Render) pra pegar o IP certo
if os.environ.get("TRUST_PROXY") == "1":
    from werkzeug.middleware.proxy_fix import ProxyFix

    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)


# =========================================================
# TEMPO
# =========================================================

# datas salvas como texto "AAAA-MM-DD HH:MM:SS"
def fmt(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def agora_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def agora_local():
    return datetime.now(FUSO).replace(tzinfo=None)


def data_hora_br(texto):
    """'2026-10-06 17:30:00' -> ('06/10/2026', '17:30:00')"""
    d, h = texto.split(" ")
    ano, mes, dia = d.split("-")
    return f"{dia}/{mes}/{ano}", h


# =========================================================
# BANCO DE DADOS (SQLite local / PostgreSQL online)
# =========================================================

class BD:
    """Deixa o mesmo SQL funcionar no SQLite e no Postgres."""

    def __init__(self):
        if USA_POSTGRES:
            import psycopg
            from psycopg.rows import dict_row

            self.con = psycopg.connect(DATABASE_URL, row_factory=dict_row)
        else:
            self.con = sqlite3.connect(DB_PATH)
            self.con.row_factory = sqlite3.Row
            self.con.execute("PRAGMA foreign_keys = ON")

    def exec(self, sql, params=()):
        if USA_POSTGRES:
            sql = sql.replace("?", "%s")
        return self.con.execute(sql, params)

    def um(self, sql, params=()):
        linha = self.exec(sql, params).fetchone()
        return dict(linha) if linha is not None else None

    def todos(self, sql, params=()):
        return [dict(l) for l in self.exec(sql, params).fetchall()]

    def mudar(self, sql, params=()):
        return self.exec(sql, params).rowcount

    def inserir(self, sql, params=()):
        return self.exec(sql + " RETURNING id", params).fetchone()["id"]

    def commit(self):
        self.con.commit()

    def rollback(self):
        self.con.rollback()

    def close(self):
        try:
            self.con.close()
        except Exception:
            pass


def erros_integridade():
    tipos = (sqlite3.IntegrityError,)
    if USA_POSTGRES:
        import psycopg

        tipos += (psycopg.IntegrityError,)
    return tipos


# uma conexão por requisição
def get_db():
    if "db" not in g:
        g.db = BD()
    return g.db


@app.teardown_appcontext
def fechar_db(_erro):
    db = g.pop("db", None)
    if db is not None:
        db.close()


PK = "BIGSERIAL PRIMARY KEY" if USA_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"

# tabelas
DDL = [
    f"""
    CREATE TABLE IF NOT EXISTS usuarios (
        id {PK},
        usuario TEXT NOT NULL,
        usuario_chave TEXT NOT NULL UNIQUE,
        senha_hash TEXT NOT NULL,
        senha_visivel TEXT,                  -- não é mais usada
        tipo TEXT NOT NULL CHECK (tipo IN ('ADMIN', 'OPERADOR')),
        ativo INTEGER NOT NULL DEFAULT 1
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS salas (
        id {PK},
        numero TEXT NOT NULL UNIQUE,
        producao INTEGER NOT NULL DEFAULT 1,
        grau TEXT,
        criada_em TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sala_operadores (
        sala_id BIGINT NOT NULL REFERENCES salas(id) ON DELETE CASCADE,
        usuario_id BIGINT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
        PRIMARY KEY (sala_id, usuario_id)
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS envases (
        id {PK},
        sala_id BIGINT NOT NULL REFERENCES salas(id) ON DELETE CASCADE,
        p05 DOUBLE PRECISION NOT NULL,
        p50 DOUBLE PRECISION NOT NULL,
        lote TEXT,                           -- não é mais usado
        observacao TEXT,
        grau TEXT,                           -- grau da sala na hora do envase
        data_hora TEXT NOT NULL,
        registrado_por_id BIGINT REFERENCES usuarios(id) ON DELETE SET NULL,
        registrado_por TEXT NOT NULL,
        cancelado_em TEXT,
        cancelado_por TEXT,
        motivo_cancelamento TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_envases_sala ON envases (sala_id, data_hora)",
    "CREATE INDEX IF NOT EXISTS idx_envases_data ON envases (data_hora)",
    """
    CREATE TABLE IF NOT EXISTS sessoes (
        token_hash TEXT PRIMARY KEY,
        usuario_id BIGINT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
        expira_em TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tentativas_login (
        chave TEXT PRIMARY KEY,
        falhas INTEGER NOT NULL,
        bloqueado_ate TEXT,
        atualizado_em TEXT NOT NULL
    )
    """,
]

# salas de exemplo (só no SQLite local)
SALAS_DEMO = [
    ("506", 1, "A", 701, 63.3, "2025-04-09", "16:45:31"),
    ("701", 1, "B", 408, 89.9, "2026-10-27", "20:45:32"),
    ("309", 0, "C", 421, 80.9, "2026-01-18", "10:31:07"),
    ("890", 1, "B", 387, 79.6, "2026-07-30", "18:12:54"),
    ("580", 1, "C", 395, 76.2, "2026-08-15", "17:22:14"),
    ("362", 0, "B", 450, 92.1, "2026-08-21", "14:18:09"),
]


def semear(db):
    # primeiro admin
    if not db.um("SELECT 1 AS x FROM usuarios WHERE tipo = 'ADMIN'"):
        usuario = os.environ.get("ADMIN_USUARIO", "admin").strip() or "admin"
        senha = os.environ.get("ADMIN_SENHA", "").strip()

        if not senha:
            if USA_POSTGRES:
                senha = "".join(secrets.choice("0123456789") for _ in range(8))
                print(
                    "\n" + "=" * 60
                    + f"\n ADMIN_SENHA não definida. Senha inicial gerada para '{usuario}': {senha}"
                    + "\n Troque em Configurações depois do primeiro login."
                    + "\n" + "=" * 60 + "\n",
                    flush=True,
                )
            else:
                senha = "1234"

        if not SENHA_REGEX.fullmatch(senha):
            raise SystemExit("ADMIN_SENHA deve conter só números (de 1 a 8 dígitos).")

        db.mudar(
            "INSERT INTO usuarios (usuario, usuario_chave, senha_hash, tipo) "
            "VALUES (?, ?, ?, 'ADMIN') ON CONFLICT (usuario_chave) DO NOTHING",
            (usuario, usuario.lower(), generate_password_hash(senha)),
        )

    # dados de exemplo
    demo = (not USA_POSTGRES) and os.environ.get("NAC_DEMO", "1") != "0"
    if demo and not db.um("SELECT 1 AS x FROM salas") and not db.um(
        "SELECT 1 AS x FROM usuarios WHERE tipo = 'OPERADOR'"
    ):
        op_id = db.inserir(
            "INSERT INTO usuarios (usuario, usuario_chave, senha_hash, tipo) "
            "VALUES (?, ?, ?, 'OPERADOR')",
            ("operador", "operador", generate_password_hash("1234")),
        )

        for numero, producao, grau, p05, p50, data, hora in SALAS_DEMO:
            sala_id = db.inserir(
                "INSERT INTO salas (numero, producao, grau, criada_em) VALUES (?, ?, ?, ?)",
                (numero, producao, grau, fmt(agora_local())),
            )
            db.inserir(
                "INSERT INTO envases (sala_id, p05, p50, grau, data_hora, registrado_por, registrado_por_id) "
                "VALUES (?, ?, ?, ?, ?, ?, NULL)",
                (sala_id, p05, p50, grau, f"{data} {hora}", "admin"),
            )
            if numero in ("506", "701"):
                db.mudar(
                    "INSERT INTO sala_operadores (sala_id, usuario_id) VALUES (?, ?)",
                    (sala_id, op_id),
                )


# colunas adicionadas depois (pra atualizar banco antigo)
COLUNAS_NOVAS = [
    ("salas", "grau", "TEXT"),
    ("envases", "grau", "TEXT"),
    ("envases", "cancelado_em", "TEXT"),
    ("envases", "cancelado_por", "TEXT"),
    ("envases", "motivo_cancelamento", "TEXT"),
    ("usuarios", "ativo", "INTEGER NOT NULL DEFAULT 1"),
]


def migrar(db):
    for tabela, coluna, tipo in COLUNAS_NOVAS:
        if USA_POSTGRES:
            db.exec(f"ALTER TABLE {tabela} ADD COLUMN IF NOT EXISTS {coluna} {tipo}")
        else:
            colunas = [c["name"] for c in db.todos(f"PRAGMA table_info({tabela})")]
            if coluna not in colunas:
                db.exec(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")

    # limpa senhas antigas salvas em texto
    db.exec("UPDATE usuarios SET senha_visivel = NULL WHERE senha_visivel IS NOT NULL")


def iniciar_banco():
    db = BD()
    try:
        if USA_POSTGRES:
            db.exec("SELECT pg_advisory_lock(727274)")
        for comando in DDL:
            db.exec(comando)
        migrar(db)
        db.commit()
        semear(db)
        db.commit()
        if USA_POSTGRES:
            db.exec("SELECT pg_advisory_unlock(727274)")
            db.commit()
    finally:
        db.close()


# =========================================================
# RESPOSTAS / CABEÇALHOS / ERROS
# =========================================================

CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "" if USA_POSTGRES else "*").strip()


@app.after_request
def cabecalhos(resposta):
    if CORS_ORIGINS:
        origem = request.headers.get("Origin", "")
        if CORS_ORIGINS == "*":
            resposta.headers["Access-Control-Allow-Origin"] = "*"
        elif origem in [o.strip() for o in CORS_ORIGINS.split(",")]:
            resposta.headers["Access-Control-Allow-Origin"] = origem
            resposta.headers["Vary"] = "Origin"
        resposta.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        resposta.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"

    resposta.headers["X-Content-Type-Options"] = "nosniff"
    resposta.headers["X-Frame-Options"] = "DENY"
    resposta.headers["Referrer-Policy"] = "same-origin"

    if request.path.startswith("/api/"):
        resposta.headers["Cache-Control"] = "no-store"

    return resposta


# erros sempre voltam como {"erro": "..."}
@app.errorhandler(HTTPException)
def erro_http(e):
    return jsonify(erro=e.description or e.name), e.code


@app.errorhandler(Exception)
def erro_interno(e):
    app.logger.exception(e)
    return jsonify(erro="Erro interno no servidor."), 500


def erro(mensagem, codigo=400):
    return jsonify(erro=mensagem), codigo


# =========================================================
# AUTENTICAÇÃO
# =========================================================

HASH_FALSO = generate_password_hash("senha-falsa")


def hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


def criar_sessao(db, usuario_id):
    token = secrets.token_urlsafe(32)
    db.mudar("DELETE FROM sessoes WHERE expira_em < ?", (fmt(agora_utc()),))
    db.mudar(
        "INSERT INTO sessoes (token_hash, usuario_id, expira_em) VALUES (?, ?, ?)",
        (hash_token(token), usuario_id, fmt(agora_utc() + timedelta(hours=TOKEN_HORAS))),
    )
    db.commit()
    return token


def usuario_do_token():
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None

    token = auth[7:]
    db = get_db()
    linha = db.um(
        "SELECT u.id, u.usuario, u.tipo, s.expira_em "
        "FROM sessoes s JOIN usuarios u ON u.id = s.usuario_id "
        "WHERE s.token_hash = ? AND u.ativo = 1",
        (hash_token(token),),
    )
    if not linha:
        return None

    if linha["expira_em"] < fmt(agora_utc()):
        db.mudar("DELETE FROM sessoes WHERE token_hash = ?", (hash_token(token),))
        db.commit()
        return None

    return {
        "id": linha["id"],
        "usuario": linha["usuario"],
        "tipo": linha["tipo"],
        "token_hash": hash_token(token),
    }


def login_obrigatorio(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        usuario = usuario_do_token()
        if not usuario:
            return erro("Não autenticado.", 401)
        g.usuario = usuario
        return f(*args, **kwargs)

    return wrapper


def admin_obrigatorio(f):
    @wraps(f)
    @login_obrigatorio
    def wrapper(*args, **kwargs):
        if g.usuario["tipo"] != "ADMIN":
            return erro("Acesso restrito ao administrador.", 403)
        return f(*args, **kwargs)

    return wrapper


def eh_admin():
    return g.usuario["tipo"] == "ADMIN"


# ----- bloqueio contra tentativas de adivinhar a senha -----

def chave_tentativa(usuario):
    return (usuario.lower()[:40] + "|" + (request.remote_addr or "?"))[:100]


def minutos_bloqueado(db, chave):
    linha = db.um("SELECT bloqueado_ate FROM tentativas_login WHERE chave = ?", (chave,))
    if linha and linha["bloqueado_ate"] and linha["bloqueado_ate"] > fmt(agora_utc()):
        restante = datetime.strptime(linha["bloqueado_ate"], "%Y-%m-%d %H:%M:%S") - agora_utc()
        return max(1, math.ceil(restante.total_seconds() / 60))
    return 0


def registrar_falha(db, chave):
    agora = fmt(agora_utc())
    linha = db.um("SELECT falhas FROM tentativas_login WHERE chave = ?", (chave,))

    if linha is None:
        try:
            db.mudar(
                "INSERT INTO tentativas_login (chave, falhas, bloqueado_ate, atualizado_em) "
                "VALUES (?, 1, NULL, ?)",
                (chave, agora),
            )
        except erros_integridade():
            db.rollback()
        db.commit()
        return

    falhas = linha["falhas"] + 1
    bloqueado_ate = None
    if falhas >= MAX_FALHAS:
        bloqueado_ate = fmt(agora_utc() + timedelta(minutes=BLOQUEIO_MIN))
        falhas = 0

    db.mudar(
        "UPDATE tentativas_login SET falhas = ?, bloqueado_ate = ?, atualizado_em = ? WHERE chave = ?",
        (falhas, bloqueado_ate, agora, chave),
    )
    db.commit()


@app.post("/api/login")
def login():
    d = request.get_json(silent=True) or {}
    usuario = str(d.get("usuario", "")).strip()
    senha = str(d.get("senha", ""))
    tipo = str(d.get("tipo", "")).upper()

    if tipo not in ("ADMIN", "OPERADOR"):
        return erro("Tipo de acesso inválido.")
    if not usuario or not senha:
        return erro("Informe usuário e senha.")

    db = get_db()
    chave = chave_tentativa(usuario)

    minutos = minutos_bloqueado(db, chave)
    if minutos:
        return erro(f"Muitas tentativas. Tente novamente em {minutos} min.", 429)

    linha = db.um(
        "SELECT * FROM usuarios WHERE usuario_chave = ? AND tipo = ?",
        (usuario.lower(), tipo),
    )

    if linha:
        senha_ok = check_password_hash(linha["senha_hash"], senha)
    else:
        check_password_hash(HASH_FALSO, senha)  # mesmo tempo de resposta
        senha_ok = False

    if not senha_ok:
        registrar_falha(db, chave)
        return erro("Usuário ou senha incorretos.", 401)

    db.mudar("DELETE FROM tentativas_login WHERE chave = ?", (chave,))

    if not linha["ativo"]:
        db.commit()
        return erro("Este usuário está desativado. Fale com o administrador.", 403)

    token = criar_sessao(db, linha["id"])
    return jsonify(token=token, usuario=linha["usuario"], tipo=linha["tipo"])


@app.post("/api/logout")
@login_obrigatorio
def logout():
    db = get_db()
    db.mudar("DELETE FROM sessoes WHERE token_hash = ?", (g.usuario["token_hash"],))
    db.commit()
    return jsonify(ok=True)


@app.get("/api/me")
@login_obrigatorio
def me():
    return jsonify(id=g.usuario["id"], usuario=g.usuario["usuario"], tipo=g.usuario["tipo"])


@app.get("/healthz")
def healthz():
    get_db().um("SELECT 1 AS ok")
    return jsonify(ok=True)


# =========================================================
# FORMATAÇÃO
# =========================================================

def num(valor):
    if valor is None:
        return None
    valor = float(valor)
    return int(valor) if valor.is_integer() else valor


# limite de partículas por m³ em operação (0,5 µm, 5,0 µm) - IN 35/2019 ANVISA
LIMITES_GRAU = {
    "A": (3_520, 20),
    "B": (352_000, 2_900),
    "C": (3_520_000, 29_000),
}


def ler_grau(valor):
    """'b' -> 'B'; devolve None se não for A, B ou C."""
    grau = str(valor or "").strip().upper()
    return grau if grau in LIMITES_GRAU else None


def classificar(p05, p50, grau):
    # passou de qualquer um dos limites = contaminada
    if p05 is None or p50 is None:
        return None
    limites = LIMITES_GRAU.get(grau or "")
    if not limites:
        return "INDEFINIDO"
    if p05 > limites[0] or p50 > limites[1]:
        return "CONTAMINADA"
    return "ESTÉRIL"


# sala + último envase dela
SELECT_SALAS = """
    SELECT s.id, s.numero, s.producao, s.grau AS grau,
           e.p05 AS p05, e.p50 AS p50, e.data_hora AS data_hora,
           COALESCE(e.grau, s.grau) AS grau_envase,
           (SELECT COUNT(*) FROM envases c WHERE c.sala_id = s.id AND c.cancelado_em IS NULL) AS total_envases
    FROM salas s
    LEFT JOIN envases e ON e.id = (
        SELECT e2.id FROM envases e2
        WHERE e2.sala_id = s.id AND e2.cancelado_em IS NULL
        ORDER BY e2.data_hora DESC, e2.id DESC
        LIMIT 1
    )
"""

FILTRO_SALAS_DO_OPERADOR = " WHERE s.id IN (SELECT sala_id FROM sala_operadores WHERE usuario_id = ?)"


def sala_json(r, operadores=None):
    p05, p50 = num(r["p05"]), num(r["p50"])
    data, hora = data_hora_br(r["data_hora"]) if r["data_hora"] else (None, None)

    saida = {
        "numero": r["numero"],
        "producao": bool(r["producao"]),
        "grau": r["grau"] or "",
        "p05": p05,
        "p50": p50,
        "data": data,
        "hora": hora,
        "classificacao": classificar(p05, p50, r["grau_envase"]),
        "total_envases": r["total_envases"],
    }
    if operadores is not None:
        saida["operadores"] = operadores
    return saida


SELECT_ENVASES = """
    SELECT e.id, s.numero AS sala, s.producao AS producao, e.p05, e.p50,
           e.observacao, COALESCE(e.grau, s.grau) AS grau, e.data_hora, e.registrado_por,
           e.cancelado_em, e.cancelado_por, e.motivo_cancelamento
    FROM envases e
    JOIN salas s ON s.id = e.sala_id
"""


def envase_json(r):
    p05, p50 = num(r["p05"]), num(r["p50"])
    data, hora = data_hora_br(r["data_hora"])
    return {
        "id": r["id"],
        "sala": r["sala"],
        "producao": bool(r["producao"]),
        "p05": p05,
        "p50": p50,
        "observacao": r["observacao"] or "",
        "grau": r["grau"] or "",
        "data": data,
        "hora": hora,
        "registrado_por": r["registrado_por"],
        "classificacao": classificar(p05, p50, r["grau"]),
        "cancelado": bool(r["cancelado_em"]),
        "cancelado_em": " ".join(data_hora_br(r["cancelado_em"])) if r["cancelado_em"] else "",
        "cancelado_por": r["cancelado_por"] or "",
        "motivo_cancelamento": r["motivo_cancelamento"] or "",
    }


def operadores_por_sala(db):
    mapa = {}
    for l in db.todos(
        "SELECT so.sala_id, u.usuario FROM sala_operadores so "
        "JOIN usuarios u ON u.id = so.usuario_id WHERE u.ativo = 1 ORDER BY u.usuario_chave"
    ):
        mapa.setdefault(l["sala_id"], []).append(l["usuario"])
    return mapa


# =========================================================
# SALAS (cadastro: somente admin)
# =========================================================

@app.get("/api/salas")
@login_obrigatorio
def listar_salas():
    db = get_db()

    if eh_admin():
        linhas = db.todos(SELECT_SALAS + " ORDER BY s.id")
        ops = operadores_por_sala(db)
        return jsonify([sala_json(l, ops.get(l["id"], [])) for l in linhas])

    linhas = db.todos(
        SELECT_SALAS + FILTRO_SALAS_DO_OPERADOR + " ORDER BY s.id", (g.usuario["id"],)
    )
    return jsonify([sala_json(l) for l in linhas])


def sala_acessivel(db, numero):
    """Devolve (sala, None) ou (None, erro)."""
    sala = db.um("SELECT id, numero, producao, grau FROM salas WHERE numero = ?", (numero,))
    if not sala:
        return None, erro("Sala não encontrada.", 404)

    if not eh_admin():
        vinculo = db.um(
            "SELECT 1 AS x FROM sala_operadores WHERE sala_id = ? AND usuario_id = ?",
            (sala["id"], g.usuario["id"]),
        )
        if not vinculo:
            return None, erro("Você não tem acesso a esta sala.", 403)

    return sala, None


@app.get("/api/salas/<numero>")
@login_obrigatorio
def obter_sala(numero):
    db = get_db()
    sala, falha = sala_acessivel(db, numero)
    if falha:
        return falha

    linha = db.um(SELECT_SALAS + " WHERE s.id = ?", (sala["id"],))
    ops = operadores_por_sala(db).get(sala["id"], []) if eh_admin() else None
    return jsonify(sala_json(linha, ops))


def ler_envase(d):
    """Valida o envase. Devolve (dados, None) ou (None, erro)."""
    try:
        p05 = float(str(d.get("p05")).replace(",", "."))
        p50 = float(str(d.get("p50")).replace(",", "."))
    except (TypeError, ValueError):
        return None, "Informe valores numéricos para as partículas."

    if not (math.isfinite(p05) and math.isfinite(p50)):
        return None, "Informe valores numéricos para as partículas."
    if p05 < 0 or p50 < 0 or p05 > 9_999_999 or p50 > 9_999_999:
        return None, "Os valores de partículas devem estar entre 0 e 9.999.999."

    observacao = str(d.get("observacao") or "").strip()
    if len(observacao) > 200:
        return None, "A observação deve ter no máximo 200 caracteres."

    data = str(d.get("data") or "").strip()
    hora = str(d.get("hora") or "").strip()

    if data or hora:
        if not data or not hora:
            return None, "Informe data e hora do envase (ou deixe os dois em branco)."
        dt = None
        for formato in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M"):
            try:
                dt = datetime.strptime(f"{data} {hora}", formato)
                break
            except ValueError:
                pass
        if dt is None:
            return None, "Data ou hora inválida."
        if dt > agora_local() + timedelta(minutes=5):
            return None, "A data/hora do envase não pode estar no futuro."
    else:
        dt = agora_local()

    return {
        "p05": p05,
        "p50": p50,
        "observacao": observacao,
        "data_hora": fmt(dt),
    }, None


def gravar_envase(db, sala_id, grau, dados):
    # salva o grau atual da sala junto com o envase
    return db.inserir(
        "INSERT INTO envases (sala_id, p05, p50, observacao, grau, data_hora, "
        "registrado_por_id, registrado_por) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            sala_id,
            dados["p05"],
            dados["p50"],
            dados["observacao"],
            grau,
            dados["data_hora"],
            g.usuario["id"],
            g.usuario["usuario"],
        ),
    )


@app.post("/api/salas")
@admin_obrigatorio
def criar_sala():
    d = request.get_json(silent=True) or {}

    numero = str(d.get("numero", "")).strip()
    if not NUMERO_SALA_REGEX.fullmatch(numero):
        return erro("O número da sala deve ter de 1 a 4 dígitos.")

    producao = 1 if d.get("producao") else 0

    grau = ler_grau(d.get("grau"))
    if not grau:
        return erro("Escolha o grau da sala (A, B ou C).")

    # Leitura inicial opcional: vira o primeiro envase da sala.
    p05_txt = str(d.get("p05") if d.get("p05") is not None else "").strip()
    p50_txt = str(d.get("p50") if d.get("p50") is not None else "").strip()
    primeiro = None

    if p05_txt or p50_txt:
        if not p05_txt or not p50_txt:
            return erro("Informe as duas contagens de partículas (0,5 µm e 5,0 µm).")
        primeiro, mensagem = ler_envase(d)
        if mensagem:
            return erro(mensagem)

    db = get_db()
    try:
        sala_id = db.inserir(
            "INSERT INTO salas (numero, producao, grau, criada_em) VALUES (?, ?, ?, ?)",
            (numero, producao, grau, fmt(agora_local())),
        )
    except erros_integridade():
        db.rollback()
        return erro("Essa sala já está cadastrada.", 409)

    if primeiro:
        gravar_envase(db, sala_id, grau, primeiro)

    db.commit()

    linha = db.um(SELECT_SALAS + " WHERE s.id = ?", (sala_id,))
    return jsonify(sala_json(linha, [])), 201


@app.put("/api/salas/<numero>/producao")
@admin_obrigatorio
def alterar_producao(numero):
    d = request.get_json(silent=True) or {}
    if "producao" not in d:
        return erro("Informe o status de produção.")

    db = get_db()
    sala = db.um("SELECT id FROM salas WHERE numero = ?", (numero,))
    if not sala:
        return erro("Sala não encontrada.", 404)

    db.mudar("UPDATE salas SET producao = ? WHERE id = ?", (1 if d.get("producao") else 0, sala["id"]))
    db.commit()

    linha = db.um(SELECT_SALAS + " WHERE s.id = ?", (sala["id"],))
    return jsonify(sala_json(linha, operadores_por_sala(db).get(sala["id"], [])))


@app.put("/api/salas/<numero>")
@admin_obrigatorio
def editar_sala(numero):
    # muda número e/ou grau da sala
    d = request.get_json(silent=True) or {}

    db = get_db()
    sala = db.um("SELECT id, numero, grau FROM salas WHERE numero = ?", (numero,))
    if not sala:
        return erro("Sala não encontrada.", 404)

    novo_numero = str(d.get("numero", sala["numero"])).strip()
    if not NUMERO_SALA_REGEX.fullmatch(novo_numero):
        return erro("O número da sala deve ter de 1 a 4 dígitos.")

    novo_grau = ler_grau(d.get("grau", sala["grau"]))
    if not novo_grau:
        return erro("Escolha o grau da sala (A, B ou C).")

    if novo_numero != sala["numero"] and db.um("SELECT 1 AS x FROM salas WHERE numero = ?", (novo_numero,)):
        return erro("Já existe uma sala com esse número.", 409)

    # envases antigos ficam com o grau de antes
    if sala["grau"] and novo_grau != sala["grau"]:
        db.mudar("UPDATE envases SET grau = ? WHERE sala_id = ? AND grau IS NULL", (sala["grau"], sala["id"]))

    db.mudar("UPDATE salas SET numero = ?, grau = ? WHERE id = ?", (novo_numero, novo_grau, sala["id"]))
    db.commit()

    linha = db.um(SELECT_SALAS + " WHERE s.id = ?", (sala["id"],))
    return jsonify(sala_json(linha, operadores_por_sala(db).get(sala["id"], [])))


@app.put("/api/salas/<numero>/operadores")
@admin_obrigatorio
def definir_operadores_da_sala(numero):
    # {"operadores": [id, id]}
    d = request.get_json(silent=True) or {}
    ids = d.get("operadores")

    if not isinstance(ids, list) or not all(isinstance(i, int) and not isinstance(i, bool) for i in ids):
        return erro("Envie a lista de operadores.")

    db = get_db()
    sala = db.um("SELECT id FROM salas WHERE numero = ?", (numero,))
    if not sala:
        return erro("Sala não encontrada.", 404)

    ids = list(dict.fromkeys(ids))
    for operador_id in ids:
        if not db.um("SELECT 1 AS x FROM usuarios WHERE id = ? AND tipo = 'OPERADOR'", (operador_id,)):
            return erro("Operador não encontrado.")

    db.mudar("DELETE FROM sala_operadores WHERE sala_id = ?", (sala["id"],))
    for operador_id in ids:
        db.mudar(
            "INSERT INTO sala_operadores (sala_id, usuario_id) VALUES (?, ?) ON CONFLICT DO NOTHING",
            (sala["id"], operador_id),
        )
    db.commit()
    return jsonify(ok=True, operadores=len(ids))


@app.delete("/api/salas/<numero>")
@admin_obrigatorio
def apagar_sala(numero):
    db = get_db()
    sala = db.um("SELECT id FROM salas WHERE numero = ?", (numero,))
    if not sala:
        return erro("Sala não encontrada.", 404)

    db.mudar("DELETE FROM envases WHERE sala_id = ?", (sala["id"],))
    db.mudar("DELETE FROM sala_operadores WHERE sala_id = ?", (sala["id"],))
    db.mudar("DELETE FROM salas WHERE id = ?", (sala["id"],))
    db.commit()
    return jsonify(ok=True)


# =========================================================
# ENVASES (admin: qualquer sala | operador: só as suas)
# =========================================================

@app.get("/api/salas/<numero>/envases")
@login_obrigatorio
def listar_envases_da_sala(numero):
    db = get_db()
    sala, falha = sala_acessivel(db, numero)
    if falha:
        return falha

    try:
        limite = min(max(int(request.args.get("limite", 50)), 1), 1000)
    except ValueError:
        limite = 50

    linhas = db.todos(
        SELECT_ENVASES + " WHERE e.sala_id = ? ORDER BY e.data_hora DESC, e.id DESC LIMIT ?",
        (sala["id"], limite),
    )
    return jsonify([envase_json(l) for l in linhas])


def registrar_envase_na_sala(numero, corpo):
    db = get_db()
    sala, falha = sala_acessivel(db, str(numero or "").strip())
    if falha:
        return falha

    dados, mensagem = ler_envase(corpo)
    if mensagem:
        return erro(mensagem)

    if not sala["grau"]:
        return erro("Esta sala ainda não tem grau definido. Peça ao administrador para definir em Cadastrar Sala.")

    envase_id = gravar_envase(db, sala["id"], sala["grau"], dados)
    db.commit()

    linha = db.um(SELECT_ENVASES + " WHERE e.id = ?", (envase_id,))
    return jsonify(envase_json(linha)), 201


@app.post("/api/salas/<numero>/envases")
@login_obrigatorio
def criar_envase(numero):
    return registrar_envase_na_sala(numero, request.get_json(silent=True) or {})


@app.post("/api/envases")
@login_obrigatorio
def criar_envase_geral():
    # igual a de cima, mas com a sala no corpo
    corpo = request.get_json(silent=True) or {}
    return registrar_envase_na_sala(corpo.get("sala"), corpo)


@app.post("/api/envases/<int:envase_id>/cancelar")
@admin_obrigatorio
def cancelar_envase(envase_id):
    # não apaga, só marca como cancelado com o motivo
    motivo = str((request.get_json(silent=True) or {}).get("motivo") or "").strip()
    if len(motivo) < 5:
        return erro("Escreva o motivo do cancelamento (pelo menos 5 caracteres).")
    if len(motivo) > 200:
        return erro("O motivo deve ter no máximo 200 caracteres.")

    db = get_db()
    envase = db.um("SELECT cancelado_em FROM envases WHERE id = ?", (envase_id,))
    if not envase:
        return erro("Envase não encontrado.", 404)
    if envase["cancelado_em"]:
        return erro("Este envase já foi cancelado.", 409)

    db.mudar(
        "UPDATE envases SET cancelado_em = ?, cancelado_por = ?, motivo_cancelamento = ? WHERE id = ?",
        (fmt(agora_local()), g.usuario["usuario"], motivo, envase_id),
    )
    db.commit()

    linha = db.um(SELECT_ENVASES + " WHERE e.id = ?", (envase_id,))
    return jsonify(envase_json(linha))


DATA_ISO = re.compile(r"\d{4}-\d{2}-\d{2}")


@app.get("/api/envases")
@login_obrigatorio
def historico():
    """Filtros: ?sala=506&de=2026-10-01&ate=2026-10-31"""
    db = get_db()

    condicoes, params = [], []

    if not eh_admin():
        condicoes.append("s.id IN (SELECT sala_id FROM sala_operadores WHERE usuario_id = ?)")
        params.append(g.usuario["id"])

    sala = request.args.get("sala", "").strip()
    if sala:
        condicoes.append("s.numero = ?")
        params.append(sala)

    de = request.args.get("de", "").strip()
    if de:
        if not DATA_ISO.fullmatch(de):
            return erro("Data inicial inválida.")
        condicoes.append("e.data_hora >= ?")
        params.append(de + " 00:00:00")

    ate = request.args.get("ate", "").strip()
    if ate:
        if not DATA_ISO.fullmatch(ate):
            return erro("Data final inválida.")
        condicoes.append("e.data_hora <= ?")
        params.append(ate + " 23:59:59")

    sql = SELECT_ENVASES
    if condicoes:
        sql += " WHERE " + " AND ".join(condicoes)
    sql += " ORDER BY e.data_hora DESC, e.id DESC LIMIT 5000"

    return jsonify([envase_json(l) for l in db.todos(sql, tuple(params))])


# =========================================================
# OPERADORES, ATRIBUIÇÃO DE SALAS E SENHA DO ADMIN (somente admin)
# =========================================================

def salas_por_operador(db):
    mapa = {}
    for l in db.todos(
        "SELECT so.usuario_id, s.numero FROM sala_operadores so "
        "JOIN salas s ON s.id = so.sala_id ORDER BY s.id"
    ):
        mapa.setdefault(l["usuario_id"], []).append(l["numero"])
    return mapa


@app.get("/api/operadores")
@admin_obrigatorio
def listar_operadores():
    db = get_db()
    mapa = salas_por_operador(db)
    linhas = db.todos(
        "SELECT u.id, u.usuario, u.ativo, "
        "(SELECT COUNT(*) FROM envases e WHERE e.registrado_por_id = u.id) AS envases "
        "FROM usuarios u WHERE u.tipo = 'OPERADOR' ORDER BY u.ativo DESC, u.usuario_chave"
    )
    return jsonify(
        [
            {
                "id": l["id"],
                "usuario": l["usuario"],
                "ativo": bool(l["ativo"]),
                "envases": l["envases"],
                "salas": mapa.get(l["id"], []),
            }
            for l in linhas
        ]
    )


@app.post("/api/operadores")
@admin_obrigatorio
def criar_operador():
    d = request.get_json(silent=True) or {}
    usuario = str(d.get("usuario", "")).strip()
    senha = str(d.get("senha", ""))

    if not usuario or len(usuario) > 15:
        return erro("O usuário deve ter de 1 a 15 caracteres.")
    if not SENHA_REGEX.fullmatch(senha):
        return erro("A senha deve conter somente números (máximo 8).")

    db = get_db()
    try:
        novo_id = db.inserir(
            "INSERT INTO usuarios (usuario, usuario_chave, senha_hash, tipo) "
            "VALUES (?, ?, ?, 'OPERADOR')",
            (usuario, usuario.lower(), generate_password_hash(senha)),
        )
    except erros_integridade():
        db.rollback()
        return erro("Esse usuário já existe.", 409)

    db.commit()
    return jsonify(id=novo_id, usuario=usuario), 201


@app.put("/api/operadores/<int:operador_id>")
@admin_obrigatorio
def editar_operador(operador_id):
    # senha em branco = mantém a atual
    d = request.get_json(silent=True) or {}

    db = get_db()
    operador = db.um("SELECT id, usuario FROM usuarios WHERE id = ? AND tipo = 'OPERADOR'", (operador_id,))
    if not operador:
        return erro("Operador não encontrado.", 404)

    usuario = str(d.get("usuario", operador["usuario"])).strip()
    if not usuario or len(usuario) > 15:
        return erro("O usuário deve ter de 1 a 15 caracteres.")

    senha = str(d.get("senha") or "")
    if senha and not SENHA_REGEX.fullmatch(senha):
        return erro("A senha deve conter somente números (máximo 8).")

    outro = db.um("SELECT id FROM usuarios WHERE usuario_chave = ?", (usuario.lower(),))
    if outro and outro["id"] != operador_id:
        return erro("Esse usuário já existe.", 409)

    db.mudar(
        "UPDATE usuarios SET usuario = ?, usuario_chave = ? WHERE id = ?",
        (usuario, usuario.lower(), operador_id),
    )
    if senha:
        db.mudar("UPDATE usuarios SET senha_hash = ? WHERE id = ?", (generate_password_hash(senha), operador_id))
        db.mudar("DELETE FROM sessoes WHERE usuario_id = ?", (operador_id,))
    db.commit()
    return jsonify(ok=True, usuario=usuario, senha_alterada=bool(senha))


@app.put("/api/operadores/<int:operador_id>/ativo")
@admin_obrigatorio
def ativar_operador(operador_id):
    # desativado não entra, mas continua no histórico
    ativo = 1 if (request.get_json(silent=True) or {}).get("ativo") else 0

    db = get_db()
    if not db.um("SELECT 1 AS x FROM usuarios WHERE id = ? AND tipo = 'OPERADOR'", (operador_id,)):
        return erro("Operador não encontrado.", 404)

    db.mudar("UPDATE usuarios SET ativo = ? WHERE id = ?", (ativo, operador_id))
    if not ativo:
        db.mudar("DELETE FROM sessoes WHERE usuario_id = ?", (operador_id,))
    db.commit()
    return jsonify(ok=True, ativo=bool(ativo))


@app.delete("/api/operadores/<int:operador_id>")
@admin_obrigatorio
def excluir_operador(operador_id):
    # só apaga quem nunca registrou envase
    db = get_db()
    if not db.um("SELECT 1 AS x FROM usuarios WHERE id = ? AND tipo = 'OPERADOR'", (operador_id,)):
        return erro("Operador não encontrado.", 404)

    if db.um("SELECT 1 AS x FROM envases WHERE registrado_por_id = ? LIMIT 1", (operador_id,)):
        return erro("Este operador já registrou envases e não pode ser apagado. Desative-o.", 409)

    db.mudar("DELETE FROM sala_operadores WHERE usuario_id = ?", (operador_id,))
    db.mudar("DELETE FROM sessoes WHERE usuario_id = ?", (operador_id,))
    db.mudar("DELETE FROM usuarios WHERE id = ?", (operador_id,))
    db.commit()
    return jsonify(ok=True)


@app.get("/api/atribuicoes")
@admin_obrigatorio
def listar_atribuicoes():
    db = get_db()
    mapa = salas_por_operador(db)
    operadores = db.todos(
        "SELECT id, usuario FROM usuarios WHERE tipo = 'OPERADOR' AND ativo = 1 ORDER BY usuario_chave"
    )
    return jsonify(
        [{"id": o["id"], "usuario": o["usuario"], "salas": mapa.get(o["id"], [])} for o in operadores]
    )


@app.put("/api/operadores/<int:operador_id>/salas")
@admin_obrigatorio
def definir_salas_do_operador(operador_id):
    d = request.get_json(silent=True) or {}
    numeros = d.get("salas")

    if not isinstance(numeros, list) or not all(isinstance(n, (str, int)) for n in numeros):
        return erro("Envie a lista de salas.")

    db = get_db()
    if not db.um("SELECT 1 AS x FROM usuarios WHERE id = ? AND tipo = 'OPERADOR'", (operador_id,)):
        return erro("Operador não encontrado.", 404)

    ids = []
    for numero in dict.fromkeys(str(n).strip() for n in numeros):
        sala = db.um("SELECT id FROM salas WHERE numero = ?", (numero,))
        if not sala:
            return erro(f"A sala {numero} não existe.")
        ids.append(sala["id"])

    db.mudar("DELETE FROM sala_operadores WHERE usuario_id = ?", (operador_id,))
    for sala_id in ids:
        db.mudar(
            "INSERT INTO sala_operadores (sala_id, usuario_id) VALUES (?, ?) ON CONFLICT DO NOTHING",
            (sala_id, operador_id),
        )
    db.commit()
    return jsonify(ok=True, salas=len(ids))


@app.put("/api/admin/senha")
@admin_obrigatorio
def alterar_senha_admin():
    d = request.get_json(silent=True) or {}
    nova = str(d.get("senha", ""))

    if not SENHA_REGEX.fullmatch(nova):
        return erro("A senha deve conter somente números e ter no máximo 8 caracteres.")

    db = get_db()
    db.mudar(
        "UPDATE usuarios SET senha_hash = ? WHERE id = ?",
        (generate_password_hash(nova), g.usuario["id"]),
    )
    # encerra as outras sessões abertas desse administrador
    db.mudar(
        "DELETE FROM sessoes WHERE usuario_id = ? AND token_hash <> ?",
        (g.usuario["id"], g.usuario["token_hash"]),
    )
    db.commit()
    return jsonify(ok=True)


# =========================================================
# FRONT-END (arquivos estáticos)
# =========================================================

EXTENSOES_PUBLICAS = {".html", ".css", ".js", ".jpg", ".jpeg", ".png", ".svg", ".ico"}


@app.get("/")
def raiz():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.get("/<path:arquivo>")
def arquivos_front(arquivo):
    if arquivo.startswith("api/"):
        return erro("Rota não encontrada.", 404)
    if os.path.splitext(arquivo)[1].lower() not in EXTENSOES_PUBLICAS:
        return erro("Arquivo não encontrado.", 404)
    return send_from_directory(FRONTEND_DIR, arquivo)


iniciar_banco()

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=os.environ.get("NAC_DEBUG") == "1",
    )
