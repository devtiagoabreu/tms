from tms.db.base import SessionLocal
from tms.models.masters import Machine
db = SessionLocal()
ms = db.query(Machine).order_by(Machine.mac_name).all()
for m in ms:
    ip = m.ip_addr or '-'
    mtype = m.mac_type or '-'
    print(f'{m.mac_name:12} | {ip:15} | {mtype:6} | {m.active}')
print('---', len(ms), 'machines')
db.close()
