# Módulo para a interface gráfica principal
import fnmatch
import os
import sys
import tkinter as tk
from tkinter import messagebox, ttk

from db_utils import (
    buscar_duplicadas,
    get_connection,
    marcar_deletado,
    total_deletado_mb,
)
from document_utils import existe_documento, gerar_miniatura_documento
from image_utils import existe_arquivo, gerar_miniatura, verificar_corrompida
from PIL import ImageTk
from send2trash import send2trash
from video_utils import existe_video, gerar_thumb_video

DB_PATH = os.path.join(os.path.dirname(
    os.path.abspath(__file__)), 'arquivos.db')


class DuplicadasDBApp(tk.Tk):
    def _selecionar_todos_filtro(self):
        # Só permite seleção se o filtro estiver preenchido
        filtro = self.var_path_filter.get().strip()
        # Se não houver coringa, adiciona '*' ao final
        if filtro and '*' not in filtro and '?' not in filtro:
            filtro += '*'
        filtro_lower = filtro.lower()
        if not filtro:
            messagebox.showinfo(
                "Filtro obrigatório", "Digite um path no filtro para usar esta função.")
            return
        for i, (arquivo, grupo_idx) in enumerate(self.all_arquivos):
            path = str(arquivo['path']).lower()
            deletado = arquivo['deletado'] if 'deletado' in arquivo.keys(
            ) else False
            if fnmatch.fnmatch(path, filtro_lower) and not deletado:
                self.check_vars[i].set(True)
            else:
                self.check_vars[i].set(False)
        self._show_page()

    def __init__(self):
        tk.Tk.__init__(self)
        self.title('Visualizador de Duplicadas (DB)')
        self.conn = get_connection(DB_PATH)
        from db_utils import ensure_ignorado_column
        ensure_ignorado_column(self.conn)
        self.contexto = 'imagens'
        self.per_page = 50
        self.page = 0
        self.thumb_size = 200
        self.img_refs = []
        self.check_vars = []
        self.var_path_filter = tk.StringVar()
        self.var_considerar_ignorados = tk.BooleanVar(value=True)
        self._build_ui_pre_canvas()
        self._build_ui()
        # Adiciona checkbox ignorados ao header2
        header2 = self.main_frame.winfo_children()[1]
        self.chk_ignorados = tk.Checkbutton(
            header2, text='Incluir arquivos ignorados', variable=self.var_considerar_ignorados, command=self._on_considerar_ignorados_change)
        self.chk_ignorados.pack(side=tk.LEFT, padx=5)
        self._load_duplicadas()

    def _on_considerar_ignorados_change(self):
        self._load_duplicadas()

    def ignorar_selecionados(self):
        from db_utils import marcar_ignorado
        selecionados = [i for i, var in enumerate(
            self.check_vars) if var.get()]
        if not selecionados:
            messagebox.showinfo(
                "Nenhum selecionado", "Selecione arquivos para ignorar/desfazer ignorar.")
            return
        if not messagebox.askyesno("Confirmar ignorar", f"Ignorar/desfazer ignorar {len(selecionados)} arquivos?"):
            return
        # Janela de progresso
        progresso = tk.Toplevel(self)
        progresso.title("Ignorando arquivos...")
        progresso.geometry("400x100")
        label = tk.Label(
            progresso, text="Ignorando arquivos...", font=("Arial", 12))
        label.pack(pady=10)
        barra = ttk.Progressbar(progresso, length=350,
                                mode='determinate', maximum=len(selecionados))
        barra.pack(pady=10)
        progresso.update()
        for n, idx in enumerate(selecionados, 1):
            arquivo, _ = self.all_arquivos[idx]
            path = arquivo['path']
            try:
                marcar_ignorado(self.conn, path)
            except Exception as e:
                messagebox.showerror("Erro ao ignorar", f"{path}\n{e}")
            barra['value'] = n
            label.config(
                text=f"Ignorando arquivo {n} de {len(selecionados)}...")
            progresso.update()
        progresso.destroy()
        self._load_duplicadas()

    def _on_considerar_deletados_change(self):
        self._load_duplicadas()

    def _build_ui_pre_canvas(self):
        # Frame principal para layout vertical
        self.main_frame = tk.Frame(self)
        self.main_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

    def _build_ui(self):
        self.geometry('1200x800')
        # Cabeçalho 1
        header1 = tk.Frame(self.main_frame)
        header1.pack(side=tk.TOP, fill=tk.X)
        btn_refresh = tk.Button(header1, text='⟳', font=(
            "Arial", 12, "bold"), command=self._refresh)
        btn_refresh.pack(side=tk.LEFT, padx=8)
        tk.Label(header1, text='Contexto:').pack(side=tk.LEFT)
        self.var_contexto = tk.StringVar(value=self.contexto)
        tk.Radiobutton(header1, text='Imagens', variable=self.var_contexto,
                       value='imagens', command=self._on_contexto_change).pack(side=tk.LEFT)
        tk.Radiobutton(header1, text='Vídeos', variable=self.var_contexto,
                       value='videos', command=self._on_contexto_change).pack(side=tk.LEFT)
        tk.Radiobutton(header1, text='Documentos', variable=self.var_contexto,
                       value='documentos', command=self._on_contexto_change).pack(side=tk.LEFT)
        tk.Radiobutton(header1, text='Corrompidos', variable=self.var_contexto,
                       value='corrompidos', command=self._on_contexto_change).pack(side=tk.LEFT)
        self.lbl_total_duplicados = tk.Label(
            header1, text='', font=("Arial", 12, "bold"), fg='blue')
        self.lbl_total_duplicados.pack(side=tk.LEFT, padx=10)
        self.lbl_total_deletados_count = tk.Label(
            header1, text='', font=("Arial", 12, "bold"), fg='red')
        self.lbl_total_deletados_count.pack(side=tk.LEFT, padx=10)
        self.lbl_total_deletado = tk.Label(
            header1, text='', font=("Arial", 12, "bold"), fg='green')
        self.lbl_total_deletado.pack(side=tk.LEFT, padx=10)

        # Cabeçalho 2
        header2 = tk.Frame(self.main_frame)
        header2.pack(side=tk.TOP, fill=tk.X)
        self.var_considerar_data = tk.BooleanVar(value=True)
        self.chk_data = tk.Checkbutton(
            header2, text='Considerar data de criação', variable=self.var_considerar_data, command=self._refresh)
        self.chk_data.pack(side=tk.LEFT, padx=5)
        self.var_considerar_deletados = tk.BooleanVar(value=True)
        self.chk_deletados = tk.Checkbutton(
            header2, text='Incluir arquivos deletados', variable=self.var_considerar_deletados, command=self._on_considerar_deletados_change)
        self.chk_deletados.pack(side=tk.LEFT, padx=5)
        tk.Label(header2, text='Arquivos por página:').pack(
            side=tk.LEFT, padx=5)
        self.var_per_page = tk.StringVar(value=str(self.per_page))
        self.per_page_menu = ttk.Combobox(header2, textvariable=self.var_per_page, values=[
            "50", "100", "200"], width=5, state='readonly')
        self.per_page_menu.pack(side=tk.LEFT)
        self.per_page_menu.bind('<<ComboboxSelected>>',
                                self._on_per_page_change)
        # Página [Entry] / [total] Anterior Próxima
        tk.Label(header2, text='Página').pack(side=tk.LEFT, padx=(10, 2))
        self.var_page_entry = tk.StringVar()
        self.page_entry = tk.Entry(
            header2, textvariable=self.var_page_entry, width=4, justify='center')
        self.page_entry.pack(side=tk.LEFT, padx=2)
        self.page_entry.bind('<Return>', self._on_page_entry)
        self.lbl_total_pages = tk.Label(header2, text='/ 1')
        self.lbl_total_pages.pack(side=tk.LEFT, padx=2)
        self.btn_prev = tk.Button(
            header2, text='Anterior', command=self._prev_page)
        self.btn_prev.pack(side=tk.LEFT, padx=5)
        self.btn_next = tk.Button(
            header2, text='Próxima', command=self._next_page)
        self.btn_next.pack(side=tk.LEFT, padx=5)
        tk.Label(header2, text='Tamanho miniatura:').pack(
            side=tk.LEFT, padx=10)
        self.var_thumb_size = tk.StringVar(value=str(self.thumb_size))
        self.thumb_size_menu = ttk.Combobox(header2, textvariable=self.var_thumb_size, values=[
            "200", "300", "400", "500"], width=5, state='readonly')
        self.thumb_size_menu.pack(side=tk.LEFT)
        self.thumb_size_menu.bind(
            '<<ComboboxSelected>>', self._on_thumb_size_change)

        # Cabeçalho 3: filtro de path
        header3 = tk.Frame(self.main_frame)
        header3.pack(side=tk.TOP, fill=tk.X, pady=(2, 6))
        tk.Label(header3, text='Filtrar por path:').pack(
            side=tk.LEFT, padx=(8, 2))
        entry_path = tk.Entry(
            header3, textvariable=self.var_path_filter, width=50)
        entry_path.pack(side=tk.LEFT, padx=2)
        entry_path.bind('<Return>', self._on_path_filter)

        btn_search = tk.Button(header3, text='🔍', command=self._on_path_filter)
        btn_search.pack(side=tk.LEFT, padx=2)

        btn_select_all = tk.Button(
            header3, text='Selecionar Todos do Filtro', command=self._selecionar_todos_filtro, bg='#ff0')
        btn_select_all.pack(side=tk.LEFT, padx=8)

        # Canvas central
        self._build_canvas_area()

        # Botões no rodapé
        rodape = tk.Frame(self.main_frame)
        rodape.pack(side=tk.BOTTOM, fill=tk.X)
        self.btn_ignorar = tk.Button(rodape, text="Ignorar Selecionados",
                                     command=self.ignorar_selecionados, bg='#888', fg='white')
        self.btn_ignorar.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.btn_excluir = tk.Button(rodape, text="Excluir Selecionados",
                                     command=self.excluir_selecionados, bg='#c00', fg='white')
        self.btn_excluir.pack(side=tk.LEFT, fill=tk.X, expand=True)

    def _build_canvas_area(self):
        # Frame dedicado para canvas e scrollbar lado a lado
        self.canvas_frame = tk.Frame(self.main_frame)
        self.canvas_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.scroll_canvas = tk.Canvas(self.canvas_frame)
        self.scroll_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar = ttk.Scrollbar(
            self.canvas_frame, orient="vertical", command=self.scroll_canvas.yview)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.scroll_canvas.configure(yscrollcommand=self.scrollbar.set)
        self.inner_frame = tk.Frame(self.scroll_canvas)
        self.window_id = self.scroll_canvas.create_window(
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

    # ... (Canvas já criado em _build_ui_pre_canvas)

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

    def _destacar_quadro(self, var, quadro_widget, ignorado=False):
        # Selecionado: amarelo. Ignorado: cinza escuro. Ambos: amarelo.
        if var.get():
            quadro_widget.config(bg='yellow')
        elif ignorado:
            quadro_widget.config(bg='#888')
        else:
            quadro_widget.config(bg='SystemButtonFace')

    def _show_page(self):
        # Sempre rola para o topo ao trocar de página ou aplicar filtro
        self.scroll_canvas.yview_moveto(0)
        for widget in self.inner_frame.winfo_children():
            widget.destroy()
        self.img_refs.clear()
        self._update_cabecalho()
        per_page = int(self.var_per_page.get())
        if not self.all_arquivos:
            self.var_page_entry.set('1')
            self.lbl_total_pages.config(text='/ 1')
            label = tk.Label(self.inner_frame, text="Tudo certo!! Não temos nada repetido por aqui!", font=(
                "Arial", 18, "bold"), fg="green")
            label.pack(pady=80)
            return
        start = self.page * per_page
        end = min(start + per_page, len(self.all_arquivos))
        total_pages = max(1, (len(self.all_arquivos) - 1) // per_page + 1)
        self.var_page_entry.set(str(self.page+1))
        self.lbl_total_pages.config(text=f'/ {total_pages}')
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
        size = self.thumb_size
        for grupo_idx in sorted(grupos_pagina.keys()):
            grupo = grupos_pagina[grupo_idx]
            frame_grupo = tk.LabelFrame(
                self.inner_frame, text=f'Grupo {grupo_idx+1} ({len(self.duplicadas[grupo_idx])} arquivos)', padx=10, pady=10)
            col = 0
            for arquivo, global_idx in grupo:
                path = arquivo['path']
                corrompida = arquivo['corrompida']
                deletado = arquivo['deletado']
                ignorado = arquivo['ignorado'] if 'ignorado' in arquivo.keys(
                ) else 0
                var = self.check_vars[global_idx]
                ts = arquivo['data_criacao'] if 'data_criacao' in arquivo.keys(
                ) else ''
                dt_str = str(ts) if ts else ''
                quadro_ind = tk.Frame(frame_grupo, bd=2, relief='groove')
                quadro_ind.grid(row=0, column=col, padx=8, pady=8, sticky='n')
                lbl_data = tk.Label(quadro_ind, text=dt_str,
                                    font=("Arial", 9), fg="#333")
                lbl_data.grid(row=0, column=0, padx=5, pady=(0, 2))
                # O destaque agora é feito via _destacar_quadro
                self._destacar_quadro(var, quadro_ind, ignorado=bool(ignorado))
                # Deletado
                if deletado:
                    canvas = tk.Canvas(
                        quadro_ind, width=size, height=size, bg='green', highlightthickness=0)
                    canvas.create_text(size//2, size//2, text='DELETADO',
                                       fill='white', font=("Arial", int(size/10), "bold"))
                    chk = tk.Checkbutton(
                        quadro_ind, variable=var, state='disabled')
                    txt_path = tk.Text(quadro_ind, height=3,
                                       width=40, wrap='word', font=("Arial", 8))
                    txt_path.insert('1.0', path)
                    txt_path.config(state='disabled', cursor='arrow')
                    canvas.grid(row=1, column=0, padx=5, pady=5)
                    chk.grid(row=2, column=0, padx=5, pady=2)
                    txt_path.grid(row=3, column=0, padx=5, pady=2)
                elif corrompida:
                    canvas = tk.Canvas(
                        quadro_ind, width=size, height=size, bg='red', highlightthickness=0)
                    canvas.create_text(size//2, size//2, text='CORROMPIDO',
                                       fill='white', font=("Arial", int(size/10), "bold"))
                    chk = tk.Checkbutton(
                        quadro_ind, variable=var, command=lambda v=var, q=quadro_ind: self._destacar_quadro(v, q))
                    txt_path = tk.Text(quadro_ind, height=3,
                                       width=40, wrap='word', font=("Arial", 8))
                    txt_path.insert('1.0', path)
                    txt_path.config(state='disabled', cursor='hand2')
                    txt_path.bind('<Control-Button-1>', lambda e,
                                  p=path: self._open_path(e, p, open_folder=True))
                    canvas.grid(row=1, column=0, padx=5, pady=5)
                    chk.grid(row=2, column=0, padx=5, pady=2)
                    txt_path.grid(row=3, column=0, padx=5, pady=2)
                elif self.contexto == "videos" and existe_video(path):
                    thumb_img = gerar_thumb_video(path, size)
                    if thumb_img is not None:
                        img_tk = ImageTk.PhotoImage(thumb_img)
                        self.img_refs.append(img_tk)
                        chk = tk.Checkbutton(
                            quadro_ind, variable=var, command=lambda v=var, q=quadro_ind: self._destacar_quadro(v, q))
                        lbl = tk.Label(quadro_ind, image=img_tk)
                    else:
                        chk = tk.Checkbutton(
                            quadro_ind, variable=var, command=lambda v=var, q=quadro_ind: self._destacar_quadro(v, q))
                        lbl = tk.Label(quadro_ind, text='Sem miniatura')
                    txt_path = tk.Text(quadro_ind, height=3,
                                       width=40, wrap='word', font=("Arial", 8))
                    txt_path.insert('1.0', path)
                    txt_path.config(state='disabled', cursor='hand2')
                    txt_path.bind('<Control-Button-1>', lambda e,
                                  p=path: self._open_path(e, p, open_folder=True))
                    lbl.grid(row=1, column=0, padx=5, pady=5)
                    chk.grid(row=2, column=0, padx=5, pady=2)
                    txt_path.grid(row=3, column=0, padx=5, pady=2)
                elif self.contexto == "imagens" and existe_arquivo(path):
                    img = gerar_miniatura(path, size)
                    if img is not None:
                        img_tk = ImageTk.PhotoImage(img)
                        self.img_refs.append(img_tk)
                        chk = tk.Checkbutton(
                            quadro_ind, variable=var, command=lambda v=var, q=quadro_ind: self._destacar_quadro(v, q))
                        lbl = tk.Label(quadro_ind, image=img_tk)
                    else:
                        chk = tk.Checkbutton(
                            quadro_ind, variable=var, command=lambda v=var, q=quadro_ind: self._destacar_quadro(v, q))
                        lbl = tk.Label(quadro_ind, text='Erro ao carregar')
                    txt_path = tk.Text(quadro_ind, height=3,
                                       width=40, wrap='word', font=("Arial", 8))
                    txt_path.insert('1.0', path)
                    txt_path.config(state='disabled', cursor='hand2')
                    txt_path.bind('<Control-Button-1>', lambda e,
                                  p=path: self._open_path(e, p, open_folder=True))
                    lbl.grid(row=1, column=0, padx=5, pady=5)
                    chk.grid(row=2, column=0, padx=5, pady=2)
                    txt_path.grid(row=3, column=0, padx=5, pady=2)
                elif self.contexto == "documentos" and existe_documento(path):
                    img = gerar_miniatura_documento(path, size)
                    if img is not None:
                        img_tk = ImageTk.PhotoImage(img)
                        self.img_refs.append(img_tk)
                        chk = tk.Checkbutton(
                            quadro_ind, variable=var, command=lambda v=var, q=quadro_ind: self._destacar_quadro(v, q))
                        lbl = tk.Label(quadro_ind, image=img_tk)
                    else:
                        chk = tk.Checkbutton(
                            quadro_ind, variable=var, command=lambda v=var, q=quadro_ind: self._destacar_quadro(v, q))
                        lbl = tk.Label(quadro_ind, text='Sem miniatura')
                    txt_path = tk.Text(quadro_ind, height=3,
                                       width=40, wrap='word', font=("Arial", 8))
                    txt_path.insert('1.0', path)
                    txt_path.config(state='disabled', cursor='hand2')
                    txt_path.bind('<Control-Button-1>', lambda e,
                                  p=path: self._open_path(e, p, open_folder=True))
                    lbl.grid(row=1, column=0, padx=5, pady=5)
                    chk.grid(row=2, column=0, padx=5, pady=2)
                    txt_path.grid(row=3, column=0, padx=5, pady=2)
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
            x += w + 20
            if h > max_height_linha:
                max_height_linha = h
        # Após adicionar todos os grupos, ajusta o tamanho do inner_frame
        total_height = y + max_height_linha + 20
        self.inner_frame.config(width=largura_canvas, height=total_height)
        # Após adicionar todos os grupos, atualiza a área de rolagem
        self.inner_frame.update_idletasks()
        self.scroll_canvas.configure(
            scrollregion=self.scroll_canvas.bbox("all"))
        # Garante que a largura do inner_frame acompanha a largura do canvas
        self.scroll_canvas.itemconfig(
            self.window_id, width=self.scroll_canvas.winfo_width())

    def _update_cabecalho(self):
        from db_utils import total_deletados_count
        total_duplicados = len(self.all_arquivos)
        total_del = total_deletados_count(self.conn)
        total_mb = total_deletado_mb(self.conn)
        self.lbl_total_duplicados.config(
            text=f"Total de arquivos duplicados: {total_duplicados}")
        self.lbl_total_deletados_count.config(
            text=f"Total de arquivos deletados: {total_del}")
        self.lbl_total_deletado.config(
            text=f"Total deletado: {total_mb:.2f} MB")

    def _on_contexto_change(self):
        self.contexto = self.var_contexto.get()
        self.page = 0
        self._load_duplicadas()

    def _on_per_page_change(self, event=None):
        self.page = 0
        self._show_page()

    def _on_thumb_size_change(self, event=None):
        self.thumb_size = int(self.var_thumb_size.get())
        self._show_page()

    def _on_mousewheel(self, event):
        if event.num == 5 or event.delta < 0:
            self.scroll_canvas.yview_scroll(1, "units")
        elif event.num == 4 or event.delta > 0:
            self.scroll_canvas.yview_scroll(-1, "units")

    def _on_page_entry(self, event=None):
        try:
            page = int(self.var_page_entry.get()) - 1
            if 0 <= page < self.total_pages:
                self.page = page
                self._show_page()
            else:
                messagebox.showinfo(
                    "Página inválida", f"Digite um número entre 1 e {self.total_pages}.")
        except Exception:
            messagebox.showinfo("Entrada inválida",
                                "Digite um número de página válido.")

    def _on_path_filter(self, event=None):
        self.page = 0
        self._load_duplicadas()

    def _refresh(self):
        self._load_duplicadas()

    def _prev_page(self):
        if self.page > 0:
            self.page -= 1
            self._show_page()

    def _next_page(self):
        if (self.page + 1) * int(self.var_per_page.get()) < len(self.all_arquivos):
            self.page += 1
            self._show_page()

    def excluir_selecionados(self):
        selecionados = [i for i, var in enumerate(
            self.check_vars) if var.get()]
        if not selecionados:
            messagebox.showinfo("Nenhum selecionado",
                                "Selecione arquivos para excluir.")
            return
        if not messagebox.askyesno("Confirmar exclusão", f"Excluir {len(selecionados)} arquivos? (Eles serão enviados para a lixeira)"):
            return

        # Janela de progresso
        progresso = tk.Toplevel(self)
        progresso.title("Excluindo arquivos...")
        progresso.geometry("400x100")
        label = tk.Label(
            progresso, text="Excluindo arquivos...", font=("Arial", 12))
        label.pack(pady=10)
        barra = ttk.Progressbar(progresso, length=350,
                                mode='determinate', maximum=len(selecionados))
        barra.pack(pady=10)
        progresso.update()

        for n, idx in enumerate(selecionados, 1):
            arquivo, grupo_idx = self.all_arquivos[idx]
            path = arquivo[2]
            try:
                send2trash(path)
                marcar_deletado(self.conn, path)
            except Exception as e:
                messagebox.showerror("Erro ao excluir", f"{path}\n{e}")
            barra['value'] = n
            label.config(
                text=f"Excluindo arquivo {n} de {len(selecionados)}...")
            progresso.update()

        progresso.destroy()
        self._refresh()

    def _load_duplicadas(self):
        if self.contexto == 'corrompidos':
            from db_utils import buscar_corrompidos
            corrompidos = buscar_corrompidos(self.conn)
            self.duplicadas = [[arq] for arq in corrompidos]
        else:
            considerar_data = getattr(self, 'var_considerar_data', None)
            if considerar_data is not None:
                considerar_data = self.var_considerar_data.get()
            else:
                considerar_data = True
            considerar_deletados = getattr(
                self, 'var_considerar_deletados', None)
            if considerar_deletados is not None:
                considerar_deletados = self.var_considerar_deletados.get()
            else:
                considerar_deletados = True
            considerar_ignorados = getattr(
                self, 'var_considerar_ignorados', None)
            if considerar_ignorados is not None:
                considerar_ignorados = self.var_considerar_ignorados.get()
            else:
                considerar_ignorados = True
            from db_utils import buscar_duplicadas as buscar_duplicadas_fn
            self.duplicadas = buscar_duplicadas_fn(
                self.conn, self.contexto, considerar_data_criacao=considerar_data, considerar_deletados=considerar_deletados, considerar_ignorados=considerar_ignorados)
        filtro = self.var_path_filter.get().strip()
        if filtro and '*' not in filtro and '?' not in filtro:
            filtro += '*'
        filtro_lower = filtro.lower()
        self.all_arquivos = []
        if filtro:
            grupos_filtrados = []
            for grupo in self.duplicadas:
                if any(fnmatch.fnmatch(str(arq[2]).lower(), filtro_lower) for arq in grupo):
                    grupos_filtrados.append(grupo)
            self.duplicadas_filtradas = grupos_filtrados
        else:
            self.duplicadas_filtradas = self.duplicadas
        for grupo_idx, grupo in enumerate(self.duplicadas_filtradas):
            for arquivo in grupo:
                self.all_arquivos.append((arquivo, grupo_idx))
        self.total_pages = max(
            1, (len(self.all_arquivos) - 1) // int(self.var_per_page.get()) + 1)
        self.check_vars = [tk.BooleanVar() for _ in self.all_arquivos]
        self._show_page()
