@echo off
pushd %~dp0

call py-dist\scripts\env.bat
cd py-dist\

python run.py
popd
