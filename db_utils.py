import sqlite3
from pathlib import Path

from file_exts import DOC_EXTS, IMG_EXTS, VIDEO_EXTS


def ensure_ignorado_column(conn):
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(arquivos)")
    columns = [row[1] for row in cur.fetchall()]
    if 'ignorado' not in columns:
        cur.execute(
            "ALTER TABLE arquivos ADD COLUMN ignorado INTEGER DEFAULT 0")
        conn.commit()


def marcar_ignorado(conn, path):
    cur = conn.cursor()
    cur.execute(
        "UPDATE arquivos SET ignorado = NOT IFNULL(ignorado,0) WHERE path=?", (path,))
    conn.commit()


def total_deletados_count(conn):
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM arquivos WHERE deletado=1")
    return cur.fetchone()[0] or 0


def buscar_corrompidos(conn, contexto=None):
    if contexto == 'imagens':
        exts = IMG_EXTS
    elif contexto == 'videos':
        exts = VIDEO_EXTS
    else:
        exts = IMG_EXTS + VIDEO_EXTS
    q = '''SELECT * FROM arquivos WHERE corrompida=1 AND ext IN ({})'''.format(
        ','.join(['?']*len(exts)))
    return conn.execute(q, exts).fetchall()


def get_connection(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def buscar_duplicadas(conn, contexto, considerar_data_criacao=True, considerar_deletados=True, considerar_ignorados=True):
    if contexto == 'imagens':
        exts = IMG_EXTS
    elif contexto == 'videos':
        exts = VIDEO_EXTS
    elif contexto == 'documentos':
        exts = DOC_EXTS
    else:
        exts = IMG_EXTS + VIDEO_EXTS + DOC_EXTS
    if considerar_data_criacao:
        group_by = 'hash, tamanho, data_criacao'
        select = 'hash, tamanho, data_criacao, COUNT(*) as qtd'
        having = 'HAVING qtd > 1'
    else:
        group_by = 'hash, tamanho'
        select = 'hash, tamanho, COUNT(*) as qtd'
        having = 'HAVING qtd > 1'
    where = f"ext IN ({','.join(['?']*len(exts))})"
    if not considerar_deletados:
        where += " AND (deletado=0 OR deletado IS NULL)"
    if not considerar_ignorados:
        where += " AND (ignorado=0 OR ignorado IS NULL)"
    q = f'''SELECT {select} FROM arquivos WHERE {where} GROUP BY {group_by} {having}'''
    rows = conn.execute(q, exts).fetchall()
    grupos = []
    for row in rows:
        if considerar_data_criacao:
            hash_, tamanho, data_criacao, qtd = row
            # Garante que data_criacao é string
            if not isinstance(data_criacao, str):
                import datetime
                try:
                    data_criacao = datetime.datetime.fromtimestamp(
                        float(data_criacao)).strftime('%Y-%m-%d %H:%M:%S')
                except Exception:
                    data_criacao = str(data_criacao)
            files_q = '''SELECT * FROM arquivos WHERE hash=? AND tamanho=? AND data_criacao=?'''
            files_params = [hash_, tamanho, data_criacao]
            if not considerar_deletados:
                files_q += " AND (deletado=0 OR deletado IS NULL)"
            if not considerar_ignorados:
                files_q += " AND (ignorado=0 OR ignorado IS NULL)"
            files = conn.execute(files_q, files_params).fetchall()
        else:
            hash_, tamanho, qtd = row
            files_q = '''SELECT * FROM arquivos WHERE hash=? AND tamanho=?'''
            files_params = [hash_, tamanho]
            if not considerar_deletados:
                files_q += " AND (deletado=0 OR deletado IS NULL)"
            if not considerar_ignorados:
                files_q += " AND (ignorado=0 OR ignorado IS NULL)"
            files = conn.execute(files_q, files_params).fetchall()
        grupos.append(files)
    return grupos


def marcar_deletado(conn, path):
    conn.execute("UPDATE arquivos SET deletado=1 WHERE path=?", (path,))
    conn.commit()


def total_deletado_mb(conn):
    cur = conn.cursor()
    cur.execute("SELECT SUM(tamanho) FROM arquivos WHERE deletado=1")
    total_bytes = cur.fetchone()[0] or 0
    return total_bytes / 1024 / 1024
