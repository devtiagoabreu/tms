from tms.db.base import SessionLocal
from tms.models.masters import Machine
from sqlalchemy import select

ipfile = 'docs/legado/htdocs/wnet/iptable/ip_table.txt'
db = SessionLocal()
added = 0
with open(ipfile) as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith('#') or line.startswith('LW700') or line.startswith('FORMAT') or line.startswith('USER_VERSION') or line.startswith('TYPE') or line.startswith('end_of_data'):
            continue
        parts = line.split()
        if not parts:
            continue
        ip = parts[0]
        if ip.count('.') != 3:
            continue
        name = parts[1] if len(parts) > 1 else ip
        if not name.isdigit():
            continue
        mac_name = name.zfill(5)
        exists = db.execute(select(Machine).where(Machine.mac_name==mac_name)).scalar_one_or_none()
        if not exists:
            db.add(Machine(mac_name=mac_name, mac_type='JAT', ip_addr=ip, active=True))
            added += 1
db.commit()
ms = db.execute(select(Machine).order_by(Machine.mac_name)).scalars().all()
print('added', added, 'total', len(ms))
for m in ms:
    print(m.mac_name, m.ip_addr)
db.close()
