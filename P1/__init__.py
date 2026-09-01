import os

# Termux environment detection logic
IS_TERMUX = 'TERMUX_VERSION' in os.environ or os.path.exists('/data/data/com.termux')

# PyMySQL setup only for non-Termux (GitHub Actions / Production MySQL)
if not IS_TERMUX:
    try:
        import pymysql
        pymysql.install_as_MySQLdb()
    except ImportError:
        pass
