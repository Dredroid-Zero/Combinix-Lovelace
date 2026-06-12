# Dependências locais portáteis

Esta pasta acompanha a edição local do Combinix Lovelace para que o programa possa
abrir sem executar `pip install` e sem acessar a internet. As bibliotecas são
carregadas localmente por `app.py`.

Pacotes incluídos:

- Flask 2.3.2
- Werkzeug 2.3.7
- openpyxl 3.1.2
- Jinja2 3.1.6
- itsdangerous 2.2.0
- click 8.4.1
- blinker 1.9.0
- MarkupSafe 3.0.3 (fallback Python puro)
- et_xmlfile 2.0.0

Os arquivos de licença distribuídos pelos respectivos pacotes permanecem nas
pastas `*.dist-info`.
