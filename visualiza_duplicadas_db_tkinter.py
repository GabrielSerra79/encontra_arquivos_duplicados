import contextlib
import os
import sqlite3
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from PIL import Image, ImageTk
from send2trash import send2trash
from video_thumb_utils import get_video_thumbnail

DB_PATH = os.path.join(os.path.dirname(
    os.path.abspath(__file__)), 'arquivos.db')
IMG_EXTS = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
VIDEO_EXTS = ['.mp4', '.avi', '.mov', '.mkv',
              '.wmv', '.flv', '.mpeg', '.mpg', '.webm']


class DuplicadasDBApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Visualizador de Duplicadas (DB)')
        self.conn = sqlite3.connect(DB_PATH)
        self.contexto = 'imagens'  # ou 'videos'
        self.per_page = 20
        self.page = 0
        self.thumb_size = 128
        self.img_refs = []
        self.check_vars = []
        self._build_ui()
        self._load_duplicadas()

    def _build_ui(self):
        self.geometry('1200x800')
        top_frame = tk.Frame(self)
        top_frame.pack(side=tk.TOP, fill=tk.X)
        # Toggle contexto
        toggle_frame = tk.Frame(top_frame)
        toggle_frame.pack(side=tk.LEFT, padx=5)
        tk.Label(toggle_frame, text='Contexto:').pack(side=tk.LEFT)
        self.var_contexto = tk.StringVar(value=self.contexto)
        tk.Radiobutton(toggle_frame, text='Imagens', variable=self.var_contexto,
                       value='imagens', command=self._on_contexto_change).pack(side=tk.LEFT)
        tk.Radiobutton(toggle_frame, text='Vídeos', variable=self.var_contexto,
                       value='videos', command=self._on_contexto_change).pack(side=tk.LEFT)
        # Título e botão de refresh
        title_frame = tk.Frame(top_frame)
        title_frame.pack(side=tk.LEFT, padx=5)
        tk.Label(title_frame, text='Visualizador de Duplicadas (DB)',
                 font=("Arial", 14, "bold")).pack(side=tk.LEFT)
        btn_refresh = tk.Button(title_frame, text='⟳', font=(
            "Arial", 12, "bold"), command=self._refresh)
        btn_refresh.pack(side=tk.LEFT, padx=8)
        # Contador de duplicados
        self.lbl_total_duplicados = tk.Label(
            top_frame, text='', font=("Arial", 12, "bold"), fg='blue')
        self.lbl_total_duplicados.pack(side=tk.LEFT, padx=10)
        # Total deletado
        self.lbl_total_deletado = tk.Label(
            top_frame, text='', font=("Arial", 12), fg='green')
        self.lbl_total_deletado.pack(side=tk.LEFT, padx=10)
        # Opções de exibição
        tk.Label(top_frame, text='Arquivos por página:').pack(
            side=tk.LEFT, padx=5)
        self.var_per_page = tk.StringVar(value=str(self.per_page))
        per_page_menu = ttk.Combobox(top_frame, textvariable=self.var_per_page, values=[
            "20", "30", "50"], width=5, state='readonly')
        per_page_menu.pack(side=tk.LEFT)
        per_page_menu.bind('<<ComboboxSelected>>', self._on_per_page_change)
        self.page_label = tk.Label(top_frame, text='')
        self.page_label.pack(side=tk.LEFT, padx=10)
        btn_prev = tk.Button(top_frame, text='Anterior',
                             command=self._prev_page)
        btn_prev.pack(side=tk.LEFT, padx=5)
        btn_next = tk.Button(top_frame, text='Próxima',
                             command=self._next_page)
        btn_next.pack(side=tk.LEFT, padx=5)
        tk.Label(top_frame, text='Tamanho miniatura:').pack(
            side=tk.LEFT, padx=10)
        self.var_thumb_size = tk.IntVar(value=self.thumb_size)
        thumb_slider = tk.Scale(top_frame, from_=100, to=400, orient=tk.HORIZONTAL,
                                variable=self.var_thumb_size, command=self._on_thumb_size_change)
        thumb_slider.pack(side=tk.LEFT)
        btn_excluir = tk.Button(self, text="Excluir Selecionados",
                                command=self.excluir_selecionados, bg='#c00', fg='white')
        btn_excluir.pack(side=tk.BOTTOM, fill=tk.X)
        # Canvas e scrollbar para exibição das imagens
        self.scroll_canvas = tk.Canvas(self)
        self.scroll_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar = ttk.Scrollbar(
            self, orient="vertical", command=self.scroll_canvas.yview)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.scroll_canvas.configure(yscrollcommand=self.scrollbar.set)
        self.inner_frame = tk.Frame(self.scroll_canvas)
        self.scroll_canvas.create_window(
            (0, 0), window=self.inner_frame, anchor='nw')
        self.inner_frame.bind("<Configure>", lambda e: self.scroll_canvas.configure(
            scrollregion=self.scroll_canvas.bbox("all")))
        self.scroll_canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.scroll_canvas.bind_all("<Button-4>", self._on_mousewheel)
        self.scroll_canvas.bind_all("<Button-5>", self._on_mousewheel)
        self._resize_after_id = None

        def on_resize(event):
            if self._resize_after_id:
                self.after_cancel(self._resize_after_id)
            self._resize_after_id = self.after(300, self._show_page)
        self.scroll_canvas.bind('<Configure>', on_resize)

    def _load_duplicadas(self):
        self.duplicadas = self._buscar_duplicadas()
        # Montar lista global de arquivos duplicados [(arquivo, grupo_idx)]
        self.all_arquivos = []
        for grupo_idx, grupo in enumerate(self.duplicadas):
            for arquivo in grupo:
                self.all_arquivos.append((arquivo, grupo_idx))
        self.total_pages = max(
            1, (len(self.all_arquivos) - 1) // int(self.var_per_page.get()) + 1)
        self.check_vars = [tk.BooleanVar() for _ in self.all_arquivos]
        self._show_page()

    def _buscar_duplicadas(self):
        exts = IMG_EXTS if self.contexto == 'imagens' else VIDEO_EXTS
        # Buscar todos os arquivos duplicados, incluindo deletados
        q = '''SELECT hash, tamanho, data_criacao, COUNT(*) as qtd FROM arquivos WHERE ext IN ({}) GROUP BY hash, tamanho, data_criacao HAVING qtd > 1'''.format(
            ','.join(['?']*len(exts)))
        rows = self.conn.execute(q, exts).fetchall()
        grupos = []
        for hash_, tamanho, data_criacao, qtd in rows:
            files = self.conn.execute(
                '''SELECT * FROM arquivos WHERE hash=? AND tamanho=? AND data_criacao=?''', (hash_, tamanho, data_criacao)).fetchall()
            grupos.append(files)
        return grupos

    def _show_page(self):
        import subprocess
        for widget in self.inner_frame.winfo_children():
            widget.destroy()
        self.img_refs.clear()
        self._update_cabecalho()
        per_page = int(self.var_per_page.get())
        # Atualiza label de paginação
        if not self.all_arquivos:
            self.page_label.config(text="")
            label = tk.Label(self.inner_frame, text="Tudo certo!! Não temos nada repetido por aqui!", font=(
                "Arial", 18, "bold"), fg="green")
            label.pack(pady=80)
            return
        start = self.page * per_page
        end = min(start + per_page, len(self.all_arquivos))
        total_pages = max(1, (len(self.all_arquivos) - 1) // per_page + 1)
        self.page_label.config(text=f"Página {self.page+1} / {total_pages}")
        arquivos_pagina = self.all_arquivos[start:end]
        grupos_pagina = {}
        for idx, (arquivo, grupo_idx) in enumerate(arquivos_pagina):
            grupos_pagina.setdefault(
                grupo_idx, []).append((arquivo, start+idx))
        largura_canvas = self.scroll_canvas.winfo_width()
        if largura_canvas < 400:
            largura_canvas = 1100
        x, y = 10, 10
        max_height_linha = 0
        grupo_widgets = []
        size = self.var_thumb_size.get()
        for grupo_idx in sorted(grupos_pagina.keys()):
            grupo = grupos_pagina[grupo_idx]
            frame_grupo = tk.LabelFrame(
                self.inner_frame, text=f'Grupo {grupo_idx+1} ({len(self.duplicadas[grupo_idx])} arquivos)', padx=10, pady=10)
            col = 0
            for arquivo, global_idx in grupo:
                path = arquivo[2]
                ext = Path(path).suffix.lower()
                corrompida = arquivo[6]
                deletado = arquivo[8]
                var = self.check_vars[global_idx]
                # Deletado
                if deletado:
                    canvas = tk.Canvas(
                        frame_grupo, width=size, height=size, bg='green', highlightthickness=0)
                    canvas.create_text(size//2, size//2, text='DELETADO',
                                       fill='white', font=("Arial", int(size/10), "bold"))
                    chk = tk.Checkbutton(
                        frame_grupo, variable=var, state='disabled')
                    txt_path = tk.Text(frame_grupo, height=3,
                                       width=40, wrap='word', font=("Arial", 8))
                    txt_path.insert('1.0', path)
                    txt_path.config(state='disabled', cursor='arrow')
                    canvas.grid(row=0, column=col, padx=5, pady=5)
                    chk.grid(row=1, column=col, padx=5, pady=2)
                    txt_path.grid(row=2, column=col, padx=5, pady=2)
                # Corrompido
                elif corrompida:
                    canvas = tk.Canvas(
                        frame_grupo, width=size, height=size, bg='red', highlightthickness=0)
                    canvas.create_text(size//2, size//2, text='CORROMPIDO',
                                       fill='white', font=("Arial", int(size/10), "bold"))
                    chk = tk.Checkbutton(
                        frame_grupo, variable=var)
                    txt_path = tk.Text(frame_grupo, height=3,
                                       width=40, wrap='word', font=("Arial", 8))
                    txt_path.insert('1.0', path)
                    txt_path.config(state='disabled', cursor='hand2')
                    txt_path.bind('<Control-Button-1>', lambda e,
                                  p=path: self._open_path(e, p, open_folder=True))
                    canvas.grid(row=0, column=col, padx=5, pady=5)
                    chk.grid(row=1, column=col, padx=5, pady=2)
                    txt_path.grid(row=2, column=col, padx=5, pady=2)
                # Vídeo
                elif self.contexto == "videos" and ext in VIDEO_EXTS and os.path.exists(path):
                    try:
                        with contextlib.suppress(Exception):
                            thumb_img = get_video_thumbnail(path)
                        if thumb_img is not None:
                            thumb_img = thumb_img.resize((size, size))
                            img_tk = ImageTk.PhotoImage(thumb_img)
                            self.img_refs.append(img_tk)
                            chk = tk.Checkbutton(
                                frame_grupo, variable=var)
                            lbl = tk.Label(frame_grupo, image=img_tk)
                        else:
                            chk = tk.Checkbutton(
                                frame_grupo, variable=var)
                            lbl = tk.Label(frame_grupo, text='Sem miniatura')
                        txt_path = tk.Text(
                            frame_grupo, height=3, width=40, wrap='word', font=("Arial", 8))
                        txt_path.insert('1.0', path)
                        txt_path.config(state='disabled', cursor='hand2')
                        txt_path.bind('<Control-Button-1>', lambda e,
                                      p=path: self._open_path(e, p, open_folder=True))
                        lbl.grid(row=0, column=col, padx=5, pady=5)
                        chk.grid(row=1, column=col, padx=5, pady=2)
                        txt_path.grid(row=2, column=col, padx=5, pady=2)
                    except Exception as e:
                        lbl = tk.Label(frame_grupo, text=f'Erro: {e}')
                        lbl.grid(row=0, column=col)
                # Imagem
                elif self.contexto == "imagens" and ext in IMG_EXTS and os.path.exists(path):
                    try:
                        img = Image.open(path)
                        img.thumbnail((size, size))
                        img_tk = ImageTk.PhotoImage(img)
                        self.img_refs.append(img_tk)
                        chk = tk.Checkbutton(
                            frame_grupo, variable=var)
                        lbl = tk.Label(frame_grupo, image=img_tk)
                        txt_path = tk.Text(
                            frame_grupo, height=3, width=40, wrap='word', font=("Arial", 8))
                        txt_path.insert('1.0', path)
                        txt_path.config(state='disabled', cursor='hand2')
                        txt_path.bind('<Control-Button-1>', lambda e,
                                      p=path: self._open_path(e, p, open_folder=True))
                        lbl.grid(row=0, column=col, padx=5, pady=5)
                        chk.grid(row=1, column=col, padx=5, pady=2)
                        txt_path.grid(row=2, column=col, padx=5, pady=2)
                    except Exception as e:
                        lbl = tk.Label(frame_grupo, text=f'Erro: {e}')
                        lbl.grid(row=0, column=col)
                else:
                    continue
                col += 1
            frame_grupo.update_idletasks()
            w = frame_grupo.winfo_reqwidth()
            h = frame_grupo.winfo_reqheight()
            if x + w > largura_canvas:
                x = 10
                y += max_height_linha + 20
                max_height_linha = 0
            frame_grupo.place(x=x, y=y)
            grupo_widgets.append(frame_grupo)
            x += w + 20
            if h > max_height_linha:
                max_height_linha = h
        total_height = y + max_height_linha + 20
        self.inner_frame.config(width=largura_canvas, height=total_height)

    def excluir_selecionados(self):
        selecionados = [(idx, arquivo, grupo_idx) for idx, (arquivo, grupo_idx) in enumerate(
            self.all_arquivos) if self.check_vars[idx].get()]
        if not selecionados:
            messagebox.showinfo('Nenhum selecionado',
                                'Selecione pelo menos uma imagem para excluir.')
            return
        if not messagebox.askyesno('Confirmação', f'Tem certeza que deseja excluir {len(selecionados)} arquivo(s)?'):
            return
        erros = []
        total = len(selecionados)
        toast = tk.Toplevel(self)
        toast.overrideredirect(True)
        toast.geometry(
            f"300x60+{self.winfo_x()+self.winfo_width()//2-150}+{self.winfo_y()+50}")
        tk.Label(toast, text="Excluindo arquivos...",
                 font=("Arial", 12)).pack(pady=5)
        progress = tk.Label(
            toast, text="0 / {}".format(total), font=("Arial", 10))
        progress.pack()
        self.update_idletasks()
        for i, (idx, arquivo, grupo_idx) in enumerate(selecionados, 1):
            path = arquivo[2]
            try:
                send2trash(path)
                # Marcar como deletado no banco
                self.conn.execute(
                    "UPDATE arquivos SET deletado=1 WHERE path=?", (path,))
            except Exception as e:
                erros.append(f'{path}: {e}')
            progress.config(text=f"{i} / {total}")
            toast.update_idletasks()
        self.conn.commit()
        self._refresh()
        toast.destroy()
        if erros:
            messagebox.showerror('Erros ao excluir', '\n'.join(erros))
        else:
            messagebox.showinfo(
                'Sucesso', f'{total} arquivo(s) excluídos.')

    def _refresh(self):
        self._load_duplicadas()
        self._show_page()
        self._update_cabecalho()

    def _on_mousewheel(self, event):
        if event.num == 5 or event.delta == -120:
            self.scroll_canvas.yview_scroll(1, "units")
        elif event.num == 4 or event.delta == 120:
            self.scroll_canvas.yview_scroll(-1, "units")

    def _on_contexto_change(self):
        self.contexto = self.var_contexto.get()
        self.page = 0
        self._load_duplicadas()
        self._show_page()
        self._update_cabecalho()

    def _on_per_page_change(self, event=None):
        try:
            self.per_page = int(self.var_per_page.get())
        except Exception:
            self.per_page = 20
        self.page = 0
        self._show_page()

    def _on_thumb_size_change(self, event=None):
        self.thumb_size = self.var_thumb_size.get()
        self._show_page()

    def _prev_page(self):
        if self.page > 0:
            self.page -= 1
            self._show_page()

    def _next_page(self):
        per_page = int(self.var_per_page.get())
        total = len(self.duplicadas)
        if (self.page + 1) * per_page < total:
            self.page += 1
            self._show_page()

    def _open_path(self, event, path, open_folder=False):
        try:
            if open_folder:
                folder = os.path.dirname(path)
                if os.name == 'nt':
                    os.startfile(folder)
                elif sys.platform == 'darwin':
                    os.system(f'open "{folder}"')
                else:
                    os.system(f'xdg-open "{folder}"')
            else:
                if os.name == 'nt':
                    os.startfile(path)
                elif sys.platform == 'darwin':
                    os.system(f'open "{path}"')
                else:
                    os.system(f'xdg-open "{path}"')
        except Exception as e:
            messagebox.showerror("Erro ao abrir", f"{path}\n{e}")

    def _save_deletados(self):
        # ... salvar status deletado no banco ...
        pass

    def _update_cabecalho(self):
        total_duplicados = sum(len(grupo) for grupo in self.duplicadas)
        self.lbl_total_duplicados.config(
            text=f"Total de arquivos duplicados: {total_duplicados}")
        # Total deletado (em MB)
        cur = self.conn.cursor()
        cur.execute("SELECT SUM(tamanho) FROM arquivos WHERE deletado=1")
        total_bytes = cur.fetchone()[0] or 0
        self.lbl_total_deletado.config(
            text=f"Total deletado: {total_bytes/1024/1024:.2f} MB")


if __name__ == '__main__':
    app = DuplicadasDBApp()
    app.mainloop()
