@echo off
pushd %~dp0

call py-dist\scripts\env.bat
cd requirements\
pip install -r setup_requirements.txt
popd
