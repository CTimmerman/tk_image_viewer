CALL install_dev
CALL install
CALL python -m pip lock -r requirements.txt -o pylock.toml
