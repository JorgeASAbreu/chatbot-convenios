from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.sync_dados_mg import DadosMGSyncService

with SessionLocal() as db:
    for x in DadosMGSyncService(db, get_settings().dados_mg_proxy).sync_all():
        print(x.resource_name, x.status, x.row_count)
