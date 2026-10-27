# scripts/
Project ke runtime code (app/, templates/, P1/) se alag, one-off aur helper files yahan hain.
Inme se koi file Django import nahi karta, isliye move karne se site par koi asar nahi.

- patches/          purane patch/fix scripts (dobara chalane ki zaroorat nahi)
- utilities/        export, backup-finding, legacy helpers
- backup_tools/     db_backup_manager.py (app/backup_service.py alag, wahi use hota hai)
- checks_and_tests/ security check, module diagnostics, 2FA test

Chalane ke liye project root se: python scripts/checks_and_tests/check_security.py
