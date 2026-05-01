@echo off
:: Auto Invoice Sender — runs via Windows Task Scheduler
:: Calls auto_invoice.py using the Python on PATH

cd /d "D:\time-tracker"
python auto_invoice.py >> "D:\time-tracker\invoices\scheduler.log" 2>&1
