import asyncio
import csv
import io
import os
import secrets
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel

from .config import ROOT, load_config
from .store import Store
from .worker import CameraWorker

security = HTTPBasic()


def authenticate(credentials: HTTPBasicCredentials = Depends(security)):
    username = os.getenv('MONITOR_USERNAME', 'admin')
    password = os.getenv('MONITOR_PASSWORD', '')
    valid_user = secrets.compare_digest(credentials.username.encode(), username.encode())
    valid_password = secrets.compare_digest(credentials.password.encode(), password.encode())
    if not password or not (valid_user and valid_password):
        raise HTTPException(401, 'Login diperlukan', headers={'WWW-Authenticate': 'Basic'})


@asynccontextmanager
async def lifespan(app):
    cfg = load_config()
    if len(os.getenv('MONITOR_PASSWORD', '')) < 16:
        raise RuntimeError('Set MONITOR_PASSWORD to at least 16 characters in .env')
    snapshots = ROOT / 'data/snapshots'
    snapshots.mkdir(parents=True, exist_ok=True)
    store = Store(ROOT / 'data/events.sqlite3')
    store.purge(cfg['retention_days'], snapshots)
    app.state.store = store
    app.state.workers = {c['id']: CameraWorker(c, cfg, store) for c in cfg['cameras']}
    for worker in app.state.workers.values():
        worker.start()

    async def cleanup():
        while True:
            await asyncio.sleep(3600)
            await asyncio.to_thread(store.purge, cfg['retention_days'], snapshots)

    task = asyncio.create_task(cleanup())
    try:
        yield
    finally:
        task.cancel()
        for worker in app.state.workers.values():
            worker.stop()
        for worker in app.state.workers.values():
            await asyncio.to_thread(worker.thread.join, 15)


app = FastAPI(title='CCTV Phone Monitor', lifespan=lifespan,
              dependencies=[Depends(authenticate)], docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware('http')
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'none'"
    return response


@app.get('/')
def index():
    return FileResponse(ROOT / 'static/index.html')


@app.get('/assets/{name}')
def assets(name: Literal['app.js', 'style.css']):
    return FileResponse(ROOT / 'static' / name)


@app.get('/api/cameras')
def cameras():
    return [w.status() for w in app.state.workers.values()]


@app.get('/api/events')
def events(limit: int = Query(100, ge=1, le=1000)):
    return app.state.store.list(limit)


class Review(BaseModel):
    value: Literal['pending', 'confirmed_visual', 'false_positive', 'uncertain']


@app.patch('/api/events/{event_id}/review')
def review(event_id: int, body: Review):
    if not app.state.store.review(event_id, body.value):
        raise HTTPException(404, 'Kejadian tidak ditemukan')
    return {'ok': True}


@app.get('/api/export.csv')
def export():
    output = io.StringIO()
    fields = ['id', 'camera', 'track', 'zone', 'recorded_at', 'start_seconds', 'end_seconds', 'duration', 'status', 'review']
    writer = csv.writer(output)
    writer.writerow(fields)
    for row in app.state.store.list(10000):
        # Prevent spreadsheet formula injection from operator-configured names.
        writer.writerow([("'" + str(row[k])) if str(row[k]).startswith(('=', '+', '-', '@', '\t', '\r')) else row[k] for k in fields])
    return Response('\ufeff' + output.getvalue(), media_type='text/csv',
                    headers={'Content-Disposition': 'attachment; filename="phone-events.csv"'})


@app.get('/api/snapshots/{name}')
def snapshot(name: str):
    if len(name) != 36 or not name.endswith('.jpg') or any(c not in '0123456789abcdef' for c in name[:-4]):
        raise HTTPException(404)
    path = ROOT / 'data/snapshots' / name
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path)


@app.get('/api/cameras/{camera_id}/stream')
async def stream(camera_id: str):
    worker = app.state.workers.get(camera_id)
    if worker is None:
        raise HTTPException(404)

    async def frames():
        previous = None
        while True:
            image = worker.frame()
            if image is not None and image is not previous:
                yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + image + b'\r\n'
                previous = image
            await asyncio.sleep(.15)
    return StreamingResponse(frames(), media_type='multipart/x-mixed-replace; boundary=frame')
