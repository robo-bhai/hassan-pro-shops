# Installing at a customer (step by step)

## 0. What you must have in the package
`manage.py`, `P1/`, `app/`, `ceo_module/`, `templates/`, `static/`, `deploy/`, `requirements.txt`.
Build it with `python deploy/make_package.py` (on YOUR computer): it leaves out everything below automatically and refuses to build if the license key is not set.
**Never include**: `.env`, `db.sqlite3`, `license.key`, `license_private.key`, `make_license.py`, `logs/`, `dbbackup/`, `*.bak*` files, `__pycache__/`.
Before packaging, in `P1/settings.py` paste your public key into `LICENSE_PUBLIC_KEY` (from `python make_license.py keygen`).

## 1. Windows PC (most shops)
1. Install **Python 3.12** from python.org - tick **"Add python.exe to PATH"**.
2. Copy the package to `C:\AgriPOS` (any folder without spaces).
3. Double-click `deploy\install_windows.bat`. It installs the packages, creates `.env` with random secret keys,
   creates the database, and asks you to type the **admin username and password**. Wait for "Install finished".
4. Note the line **"This computer's ID for the license key"**. Send it to the vendor and get a license key (step 4 below).
5. Double-click `deploy\start_server.bat`. Open `http://localhost:8000` on this PC; other PCs/phones on the same
   Wi-Fi/LAN open `http://<this-PC-IP>:8000` (the window prints the exact address).
6. Start automatically after a reboot: open **Task Scheduler -> Create Task**: Trigger "At startup", Action
   "Start a program" = `C:\AgriPOS\deploy\start_server.bat`, tick "Run whether user is logged on or not".
7. Allow port 8000 in Windows Firewall (Windows asks the first time - choose Private networks).

No internet at the shop? On a computer WITH internet run `pip download -r requirements.txt -d wheelhouse`, put the
`wheelhouse` folder in the package; the installer then uses it and needs no internet.

## 2. Linux server
```
sudo apt install python3 python3-venv
cd /opt/agripos && sudo bash deploy/install_linux.sh --service
```
The service is called `agripos` (`systemctl status agripos`, logs in `logs/`).

## 3. Settings you may change (`.env`, never share this file)
`ALLOWED_HOSTS` (names/IPs typed in the browser; empty = localhost + this computer), `PORT`, `HTTPS=true` only when
the site really is on https. After editing `.env`, restart the server.

## 4. License
1. In the browser: log in as admin, open `/license/`, copy **This computer's ID**.
2. On the vendor's computer: `python make_license.py issue --customer "Shop name" --machine <ID> --days 365`
3. Paste the key (`LIC1....`) on the same `/license/` page and press Activate.
Until a key is entered the system runs as a 14-day trial. After expiry there are 7 days of grace, then it is read-only
(viewing and reports work; new sales/entries do not). Replacing the computer or reinstalling Windows changes the ID: issue a new key.

## 5. Backup (already in the system)
Use the **Backup** page in the app: make a backup now, schedule, and restore. Keep a copy OFF this computer
(USB drive or cloud via the rclone setting). **Do a test restore once at every new customer** before they start working.
Also copy the file `.env` somewhere safe: without its keys a restored database cannot be used.

## 6. Updating to a new version
1. Make a backup (Backup page).  2. Stop the server.  3. Copy the new code over the old (keep `.env`, `db.sqlite3`,
`media/`, `license.key`).  4. `venv\Scripts\activate` then `python manage.py migrate` and `python manage.py collectstatic --noinput`.
5. Start the server.  6. Make one test sale and delete/return it.

## 7. If something goes wrong
- **"DJANGO_SECRET_KEY is missing"** -> `.env` is missing; run `python deploy/setup_install.py`.
- **"DisallowedHost"** -> add the address you typed to `ALLOWED_HOSTS` in `.env`.
- **Page has no design (CSS missing)** -> `python manage.py collectstatic --noinput`, restart.
- **"LICENSE_PUBLIC_KEY ... not a 64-character hex key"** -> fix the key in `P1/settings.py`, or leave it empty for no licensing.
- **Everything is read-only** -> license expired or wrong computer: see `/license/` for the reason.
- **Login does nothing on https** -> `HTTPS=true` was set but the site is opened with http (or the reverse).
