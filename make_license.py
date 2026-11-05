#!/usr/bin/env python3
"""
VENDOR TOOL - keep this file and license_private.key on YOUR computer. Never ship them to a customer.

  python make_license.py keygen                      one time: creates license_private.key, prints the PUBLIC key
                                                     for settings.py (LICENSE_PUBLIC_KEY = '...')
  python make_license.py issue --customer "Haji Traders" --machine A1B2-C3D4-E5F6-0789 --days 365
  python make_license.py issue --customer "Demo" --machine '*' --until 2027-03-31       (works on any computer)
  python make_license.py verify --pub <hex> --machine <ID> --token LIC1....              check a key
  python make_license.py machine                     print THIS computer's id

Back up license_private.key safely: if you lose it you cannot issue renewals for existing customers
(you would have to change LICENSE_PUBLIC_KEY on every install); if it leaks, anyone can make keys.
Put this file next to the project's app/ folder (it loads app/licensing directly).
"""
import argparse
import importlib.util
import os
import stat
import sys
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))


def load_licensing():
    path = os.path.join(HERE, 'app', 'licensing')
    spec = importlib.util.spec_from_file_location('licensing', os.path.join(path, '__init__.py'), submodule_search_locations=[path])
    pkg = importlib.util.module_from_spec(spec)
    sys.modules['licensing'] = pkg
    spec.loader.exec_module(pkg)
    from importlib import import_module
    return import_module('licensing.core'), import_module('licensing.ed25519')


def main():
    core, ed = load_licensing()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    k = sub.add_parser('keygen'); k.add_argument('--out', default='license_private.key')
    i = sub.add_parser('issue')
    i.add_argument('--key', default='license_private.key'); i.add_argument('--customer', required=True)
    i.add_argument('--machine', required=True, help="customer's machine id, or '*' for any computer")
    g = i.add_mutually_exclusive_group(required=True)
    g.add_argument('--days', type=int); g.add_argument('--until', help='YYYY-MM-DD')
    v = sub.add_parser('verify'); v.add_argument('--pub', required=True); v.add_argument('--token', required=True); v.add_argument('--machine')
    sub.add_parser('machine')
    a = ap.parse_args()

    if a.cmd == 'keygen':
        if os.path.exists(a.out):
            sys.exit(f'{a.out} already exists - refusing to overwrite your private key.')
        seed = os.urandom(32)
        with open(a.out, 'w') as f:
            f.write(seed.hex())
        try:
            os.chmod(a.out, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
        print(f'Private key saved to {a.out}  (KEEP SECRET, BACK IT UP)')
        print("Put this in the app's settings.py:\n\n    LICENSE_PUBLIC_KEY = '%s'\n" % ed.public_key(seed).hex())
    elif a.cmd == 'issue':
        seed = bytes.fromhex(open(a.key).read().strip())
        expires = date.fromisoformat(a.until) if a.until else date.today() + timedelta(days=a.days)
        print(core.make_token(seed, a.customer, a.machine, expires))
        print(f'\n# {a.customer} | machine {a.machine} | expires {expires:%d %b %Y}', file=sys.stderr)
    elif a.cmd == 'verify':
        data = core.parse_token(a.token, bytes.fromhex(a.pub))
        if not data:
            sys.exit('INVALID signature / format')
        ok_machine = (not a.machine) or data['m'] in ('*', a.machine)
        print(data, '| machine OK' if ok_machine else '| WRONG MACHINE')
    else:
        print(core.machine_id())


if __name__ == '__main__':
    main()
