@echo off
REM Rastreador de Precos de Mercado - lancador portatil.
REM Usa o Python embutido nesta pasta; instala os componentes na primeira execucao.
setlocal
cd /d "%~dp0"
"%~dp0python\python.exe" "%~dp0app\bootstrap.py"
if errorlevel 1 (
  echo.
  echo O programa foi encerrado. Pressione uma tecla para fechar.
  pause >nul
)
endlocal
