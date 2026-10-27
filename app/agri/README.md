# Agri Edition (mukammal)

Switch: `python manage.py agri_edition on|off|status` (sirf menu chhupata/dikhata hai, kuch delete nahi hota).
Migration: `python manage.py migrate` (0028 + 0029). Test: `python -I tests/test_agri_pure.py`.

## Kya kya hai
- **Expiry Manager** `/agri/expiry/` : batch no + expiry, buckets, write-off ("Stock se nikalein"), record `/agri/writeoffs/`.
- **Kisan Udhaar** `/agri/credit/` : baqaya, wapsi ki tareekh, WhatsApp/call, credit limit.
- **Expiry har raaste se saath chalti hai**: Purchase form, PO receive -> GRN -> Purchase convert, sale return,
  purchase return, store transfer receive, POS void.
- **Sale par**: POS aur Sales form dono mein "wapsi ki tareekh"; credit limit se upar ka udhaar ruk jata hai
  (manager ko sirf warning). POS tile par expiry aur expired qty dikhti hai; expired maal sale nahi hota (FEFO).
- **Product**: active ingredient, registration no, pack size, target crops. **Customer**: gaon, fasal, credit limit.
- **Alerts**: `python manage.py agri_alerts [--csv file.csv] [--dry-run]` roz ek dafa chalayen (cron / Task Scheduler).

## Settings
- `agri_credit_limit_mode` (System Settings): `block` (default) / `warn` / `off`.
- Write-off ka nuqsan tab post hota hai jab Store accounting ON ho aur "Stock loss" + Inventory account map hon
  (wahi mapping jo physical count istemal karta hai). Mapping na ho to write-off roll back ho kar saaf message deta hai.

## Jo abhi bhi khud karna hai
- Stock count se barhne wala maal aur production ka maal bina expiry ke aata hai (Expiry Manager ke "Expiry nahi daali" filter se bharen).
- Supplier ko wapsi ka paisa: Purchase Return alag se banayen; write-off sirf stock + nuqsan hai.
- Purani batch rows jo 0030 se pehle ki store issue / transfer ki hain, unka usage snapshot khali hota hai
  (naye issue / transfer mein expiry khud copy hoti hai).
- Store issue / transfer / count loss ab nearest-expiry-pehle (FEFO) uthate hain.
