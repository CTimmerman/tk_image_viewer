@echo off
python -m cProfile -s cumtime main.py eye.ico > profile.txt
more profile.txt
rem python -m cProfile -o profile.prof -s cumtime main.py "eye.ico"
rem snakeviz profile.prof
