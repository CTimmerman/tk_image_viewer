REM pymanager install --configure
REM py upgrade 3.13
REM set PATH="C:\Users\C\AppData\Local\Python\pythoncore-3.13-64;%PATH%"
python -m pip install --upgrade pip
CALL install_dev
CALL install
python -m pip lock -r requirements.txt -o pylock.toml
