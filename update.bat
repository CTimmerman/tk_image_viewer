CALL install_dev
CALL install
CALL pip lock -r requirements.txt -o pylock.toml
