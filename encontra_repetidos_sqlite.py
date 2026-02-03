import hashlib
import os
import signal
import sqlite3
import sys
from pathlib import Path

from file_exts import DOC_EXTS, IMG_EXTS, VIDEO_EXTS
from PIL import Image

# Set your target folder here
TARGET_ROOT = r'D:\Imagens'
# Set batch size for commits
BATCH_SIZE = 200

# Always place the database in the same folder as this script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, 'arquivos.db')
TABLE_NAME = 'arquivos'


def file_hash(path, chunk_size=8192):
    hasher = hashlib.sha256()
    with open(path, 'rb') as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def creation_date(path):
    import datetime
    import os

    from PIL import Image
    ext = os.path.splitext(str(path))[1].lower()
    # 1. Tenta EXIF para imagens
    if ext in IMG_EXTS:
        try:
            with Image.open(path) as img:
                try:
                    exif = img.getexif()
                except Exception:
                    exif = getattr(img, '_getexif', lambda: None)()
                if exif:
                    for tag, value in exif.items():
                        from PIL.ExifTags import TAGS
                        tag_name = TAGS.get(tag, tag)
                        if tag_name == 'DateTimeOriginal':
                            # Formato EXIF: 'YYYY:MM:DD HH:MM:SS'
                            try:
                                dt = datetime.datetime.strptime(
                                    value, '%Y:%m:%d %H:%M:%S')
                                return dt.strftime('%Y-%m-%d %H:%M:%S')
                            except Exception:
                                pass
        except Exception:
            pass
    # 2. Tenta metadata de vídeo (ffprobe, pymediainfo, etc.)
    if ext in VIDEO_EXTS:
        try:
            import json
            import subprocess
            cmd = [
                'ffprobe', '-v', 'error', '-select_streams', 'v:0',
                '-show_entries', 'format_tags=creation_time',
                '-of', 'json', str(path)
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=3)
            if result.returncode == 0:
                data = json.loads(result.stdout)
                tags = data.get('format', {}).get('tags', {})
                creation_time = tags.get('creation_time')
                if creation_time:
                    # Normaliza para formato ISO 8601
                    try:
                        dt = datetime.datetime.fromisoformat(
                            creation_time.replace('Z', '').replace('T', ' '))
                        return dt.strftime('%Y-%m-%d %H:%M:%S')
                    except Exception:
                        return creation_time[:19].replace('T', ' ')
        except Exception:
            pass
    # 3. Usa data do sistema (st_birthtime ou st_birthtime)
    stat = os.stat(path)
    ts = getattr(stat, 'st_birthtime', None)
    if ts is None:
        ts = stat.st_birthtime
    return datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')


def create_table(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS arquivos (
        id INTEGER PRIMARY KEY,
        nome TEXT,
        path TEXT,
        hash TEXT,
        tamanho INTEGER,
        data_criacao TEXT,
        corrompida BOOLEAN,
        ext TEXT,
        deletado BOOLEAN DEFAULT 0
    )''')
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_hash_tam_data ON arquivos (hash, tamanho, data_criacao)')
    conn.commit()


def insert_file(conn, info):
    # Garante que data_criacao é string
    data_criacao = info['data_criacao']
    if not isinstance(data_criacao, str):
        import datetime
        try:
            data_criacao = datetime.datetime.fromtimestamp(
                float(data_criacao)).strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            data_criacao = str(data_criacao)
    conn.execute('''INSERT INTO arquivos (nome, path, hash, tamanho, data_criacao, corrompida, ext, deletado)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                 (info['nome'], info['path'], info['hash'], info['tamanho'], data_criacao, bool(info['corrompida']), info['ext'], False))


def get_existing_paths(conn):
    cur = conn.cursor()
    cur.execute(f"SELECT path FROM {TABLE_NAME}")
    return set(row[0] for row in cur.fetchall())


def ask_reset_table(conn):
    print("\n[?] A tabela já contém dados.")
    print("[1] Apagar todos os dados e começar do zero")
    print("[2] Continuar de onde parou")
    print("[3] Atualizar apenas alterações (novos, modificados, removidos)")
    choice = input("Escolha uma opção (1, 2 ou 3): ").strip()
    if choice == '1':
        cur = conn.cursor()
        cur.execute(f"DELETE FROM {TABLE_NAME}")
        conn.commit()
        print("Todos os dados foram apagados. Nova coleta iniciada.")
        return set(), 0, 'full'
    elif choice == '2':
        print("Continuando de onde parou...")
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}")
        already = cur.fetchone()[0]
        return get_existing_paths(conn), already, 'continue'
    elif choice == '3':
        print("Atualizando apenas alterações...")
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}")
        already = cur.fetchone()[0]
        return get_existing_paths(conn), already, 'delta'
    else:
        print("Opção inválida. Abortando.")
        sys.exit(1)


def collect_metadata_to_db(root_folder, conn, processed_paths, start_count=0):
    total = sum(len(files) for _, _, files in os.walk(root_folder))
    count = start_count
    batch_count = 0
    for root, _, files in os.walk(root_folder):
        for name in files:
            path = Path(root) / name
            ext = path.suffix.lower()
            if ext not in IMG_EXTS and ext not in VIDEO_EXTS and ext not in DOC_EXTS:
                continue
            try:
                if sys.platform.startswith('win'):
                    path_str = str(path)
                else:
                    path_str = path.as_posix()
                if path_str in processed_paths:
                    continue  # já processado
                corrupted = False
                if ext in IMG_EXTS:
                    try:
                        with Image.open(path) as img:
                            img.verify()
                    except Exception:
                        corrupted = True
                # Para documentos, não verifica corrupção
                info = {
                    'nome': name,
                    'path': path_str,
                    'hash': file_hash(path),
                    'tamanho': path.stat().st_size,
                    'data_criacao': creation_date(path),
                    'corrompida': corrupted,
                    'ext': ext
                }
                insert_file(conn, info)
            except Exception as e:
                print(f'Falha ao obter metadados de : {path_str}')
                pass
            count += 1
            batch_count += 1
            if count % 10 == 0 or count == total:
                pct = 100 * count // total
                sys.stdout.write(
                    f"\033[F\033[KColetando metadados: {path_str}\n\033[KProgresso: {count}/{total} arquivos ({pct:.0f}%)")
                sys.stdout.flush()
            if batch_count >= BATCH_SIZE:
                conn.commit()
                batch_count = 0
    conn.commit()
    sys.stdout.write("\n")


def find_duplicates(conn, exts=None):
    if exts:
        q = '''SELECT hash, tamanho, data_criacao, COUNT(*) as qtd FROM arquivos WHERE ext IN ({}) GROUP BY hash, tamanho, data_criacao HAVING qtd > 1'''.format(
            ','.join(['?']*len(exts)))
        params = exts
    else:
        q = '''SELECT hash, tamanho, data_criacao, COUNT(*) as qtd FROM arquivos GROUP BY hash, tamanho, data_criacao HAVING qtd > 1'''
        params = []
    return conn.execute(q, params).fetchall()


def list_files_by_key(conn, hash_, tamanho, data_criacao):
    return conn.execute('''SELECT * FROM arquivos WHERE hash=? AND tamanho=? AND data_criacao=?''', (hash_, tamanho, data_criacao)).fetchall()


def update_only_changes(root_folder, conn):
    print("[i] Buscando arquivos atuais no disco...")
    disk_paths = set()
    for root, _, files in os.walk(root_folder):
        for name in files:
            path = Path(root) / name
            ext = path.suffix.lower()
            if ext not in IMG_EXTS and ext not in VIDEO_EXTS and ext not in DOC_EXTS:
                continue
            if sys.platform.startswith('win'):
                path_str = str(path)
            else:
                path_str = path.as_posix()
            disk_paths.add(path_str)
    db_paths = get_existing_paths(conn)
    # Remover do banco os que não existem mais
    to_remove = db_paths - disk_paths
    if to_remove:
        print(
            f"[i] Removendo {len(to_remove)} arquivos que não existem mais...\n")
        cur = conn.cursor()
        for p in to_remove:
            cur.execute(f"DELETE FROM {TABLE_NAME} WHERE path=?", (p,))
        conn.commit()
    # Inserir novos e atualizar modificados
    print("[i] Verificando novos e modificados...")
    cur = conn.cursor()
    # Calcular total de arquivos para barra de progresso
    total = sum(len(files) for _, _, files in os.walk(root_folder))
    count = 0
    for root, _, files in os.walk(root_folder):
        for name in files:
            path = Path(root) / name
            ext = path.suffix.lower()
            if ext not in IMG_EXTS and ext not in VIDEO_EXTS and ext not in DOC_EXTS:
                continue
            if sys.platform.startswith('win'):
                path_str = str(path)
            else:
                path_str = path.as_posix()
            stat = path.stat()
            cur.execute(
                f"SELECT tamanho, data_criacao, hash FROM {TABLE_NAME} WHERE path=?", (path_str,))
            row = cur.fetchone()
            if row is None:
                # Novo arquivo
                corrupted = False
                if ext in IMG_EXTS:
                    try:
                        with Image.open(path) as img:
                            img.verify()
                    except Exception:
                        corrupted = True
                # Para documentos, não verifica corrupção
                info = {
                    'nome': name,
                    'path': path_str,
                    'hash': file_hash(path),
                    'tamanho': stat.st_size,
                    'data_criacao': creation_date(path),
                    'corrompida': corrupted,
                    'ext': ext
                }
                insert_file(conn, info)
                msg = f"[+] Novo: {path_str}\n"
            else:
                tam_db, dt_db, hash_db = row
                tam_fs = stat.st_size
                dt_fs = creation_date(path)
                if tam_db != tam_fs or dt_db != dt_fs:
                    # Modificado
                    corrupted = False
                    if ext in IMG_EXTS:
                        try:
                            with Image.open(path) as img:
                                img.verify()
                        except Exception:
                            corrupted = True
                    hash_fs = file_hash(path)
                    # Garante que data_criacao é string
                    if not isinstance(dt_fs, str):
                        import datetime
                        try:
                            dt_fs = datetime.datetime.fromtimestamp(
                                float(dt_fs)).strftime('%Y-%m-%d %H:%M:%S')
                        except Exception:
                            dt_fs = str(dt_fs)
                    cur.execute(f"UPDATE {TABLE_NAME} SET tamanho=?, data_criacao=?, hash=?, corrompida=? WHERE path=?",
                                (tam_fs, dt_fs, hash_fs, corrupted, path_str))
                    msg = f"[*] Modificado: {path_str}\n"
                else:
                    msg = f"[i] Sem alteração: {path_str}"
            count += 1
            if count % 10 == 0 or count == total:
                pct = 100 * count // total
                # Sempre exibe duas linhas: path (ou vazio) e progresso, igual ao encontra_repetidos.py
                sys.stdout.write(
                    f"\033[F\033[K{msg}\n\033[KProgresso: {count}/{total} arquivos ({pct:.0f}%)")
                sys.stdout.flush()
    conn.commit()
    sys.stdout.write("\n")
    print("[✓] Atualização concluída.")


def main():
    conn = sqlite3.connect(DB_PATH)
    create_table(conn)
    cur = conn.cursor()
    cur.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}")
    count = cur.fetchone()[0]
    if count > 0:
        processed_paths, already, mode = ask_reset_table(conn)
    else:
        processed_paths = set()
        already = 0
        mode = 'full'

    # Handler para commit seguro no Ctrl+C
    def handle_sigint(signum, frame):
        print("\n[!] Interrompido pelo usuário. Salvando progresso...")
        conn.commit()
        conn.close()
        sys.exit(0)
    signal.signal(signal.SIGINT, handle_sigint)

    try:
        if mode == 'full':
            collect_metadata_to_db(
                TARGET_ROOT, conn, processed_paths, start_count=already)
        elif mode == 'continue':
            collect_metadata_to_db(
                TARGET_ROOT, conn, processed_paths, start_count=already)
        elif mode == 'delta':
            update_only_changes(TARGET_ROOT, conn)
    except KeyboardInterrupt:
        print("\n[!] Interrompido pelo usuário. Salvando progresso...")
        conn.commit()
        conn.close()
        sys.exit(0)
    conn.commit()
    conn.close()
    print("\n[✓] Coleta finalizada.")


if __name__ == '__main__':
    main()
