@echo off
echo Starting Nifty Sniper Live Data Feed...
:loop
python data_updater.py
echo Waiting 60 seconds...
timeout /t 60 /nobreak > NUL
goto loop
