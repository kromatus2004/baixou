@echo off
rem Abre o Baixou na janela própria, sem deixar o terminal aberto.
cd /d "%~dp0"
start "" pythonw server.py
