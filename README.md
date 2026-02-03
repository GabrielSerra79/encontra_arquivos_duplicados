# encontra_arquivos_duplicados
<b>**** PROJETO EM DESENVOLVIMENTO ****</b>

Programa para encontrar e gerenciar arquivos duplicados no HD ou SSD.
Autor: Gabriel Serra
Data: 12/2025
Versão: 0.4

## Usando SQLite
rodar o escaneamento e a busca por arquivos duplicados
`python encontra_repetidos_sqlite.py`

rodar apenas a busca por arquivos duplicados
`python encontra_repetidos_sqlite.py --so-busca`

## rodar GUI para selecionar arquivos para a exclusão
rodar
```bash
python main_visualiza_duplicadas.py
```

# Filtro no GUI
Use * para qualquer sequência de caracteres (ex: d:\pasta1**small.png)
Use ? para um único caractere (ex: d:\pasta1\pasta?\file?.jpg)
O filtro funciona tanto para exibição quanto para o botão "Selecionar Todos do Filtro". Se quiser exemplos ou ajustes, só pedir!

# Config do projeto
## Criar e entrar na venv Windows CMD
```bash
setup_and_activate_venv_WINDOWS.bat
```

## Instalar dependencias
```bash
pip install -r requiriments.txt
```
