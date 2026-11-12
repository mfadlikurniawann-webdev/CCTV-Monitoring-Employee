import logging
import math
import threading
import time
import uuid

from .config import ROOT, resolve_source
from .events import EventGate, associate

log = logging.getLogger(__name__)


class LatestFrames:
    """Continuously drain live capture; replace old frames rather than queueing them."""

    def __init__(self, cap):
        self.cap = cap
        self.lock = threading.Condition()
        self.stopped = threading.Event()
        self.alive = True
        self.sequence = 0
        self.value = None
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        try:
            while not self.stopped.is_set():
                ok, frame = self.cap.read()
                if not ok:
                    break
                with self.lock:
                    self.sequence += 1
                    self.value = (frame, time.monotonic())
                    self.lock.notify_all()
        finally:
            with self.lock:
                self.alive = False
                self.lock.notify_all()

    def next(self, previous):
        with self.lock:
            self.lock.wait_for(lambda: self.sequence != previous or not self.alive, timeout=.2)
            if self.sequence == previous:
                return None
            return self.sequence, self.value

    def close(self):
        self.stopped.set()
        self.thread.join(6)


class CameraWorker:
    def __init__(self, camera, cfg, store):
        self.camera, self.cfg, self.store = camera, cfg, store
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.jpeg = None
        self.state = {'id': camera['id'], 'name': camera['name'], 'status': 'starting',
                      'people': 0, 'candidates': 0, 'confirmed': 0, 'media_seconds': 0}
        self.thread = threading.Thread(target=self.run, daemon=True, name=f"camera-{camera['id']}")

    def set_state(self, **values):
        with self.lock:
            self.state.update(values)

    def status(self):
        with self.lock:
            return dict(self.state)

    def frame(self):
        with self.lock:
            return self.jpeg

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()

    def reset_frame(self):
        with self.lock:
            self.jpeg = None
            self.state.update(people=0, candidates=0, confirmed=0)

    def apply(self, actions, jpeg=None, reason='ended'):
        for action, track, state in actions:
            if action == 'start':
                snapshot = None
                if self.cfg.get('store_snapshots') and jpeg:
                    snapshot = f'{uuid.uuid4().hex}.jpg'
                    (ROOT / 'data/snapshots' / snapshot).write_bytes(jpeg)
                state.event_id = self.store.start(self.camera['id'], track, state, snapshot)
            else:
                self.store.update(state.event_id, state, reason if action == 'end' else 'active')

    def run(self):
        # Delayed imports keep pure event/database tests independent of GPU libraries.
        gate = EventGate(self.cfg['minimum_seconds'], self.cfg['gap_seconds'])
        cap = None
        reader = None
        try:
            import cv2
            import numpy as np
            from ultralytics import YOLO

            source = resolve_source(self.camera['source'])
            local_video = isinstance(source, str) and not source.startswith(('rtsp://', 'rtsps://'))
            person_model = YOLO(self.cfg['person_model'])
            phone_model = YOLO(self.cfg['phone_model'])
            person_ids = [i for i, name in person_model.names.items() if name.lower() == 'person']
            phone_ids = self.cfg.get('phone_class_ids')
            if phone_ids is None:
                phone_ids = [i for i, name in phone_model.names.items()
                             if 'phone' in name.lower() or 'mobile' in name.lower()]
            if not person_ids or not phone_ids or any(i not in phone_model.names for i in phone_ids):
                raise ValueError('Model classes do not match configuration')
            common = dict(conf=self.cfg['confidence'], imgsz=self.cfg['image_size'],
                          device=self.cfg['device'], verbose=False)
            origin = time.monotonic()
            while not self.stop_event.is_set():
                self.set_state(status='connecting')
                if isinstance(source, str) and not local_video:
                    cap = cv2.VideoCapture(source, cv2.CAP_FFMPEG, [
                        cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000,
                        cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000])
                else:
                    cap = cv2.VideoCapture(source)
                if not cap.isOpened():
                    cap.release()
                    self.reset_frame()
                    self.set_state(status='offline')
                    if local_video or self.stop_event.wait(5):
                        break
                    continue
                # Never reuse temporal IDs across reconnections.
                for predictor in [getattr(person_model, 'predictor', None)]:
                    for tracker in getattr(predictor, 'trackers', []):
                        tracker.reset()
                fps = cap.get(cv2.CAP_PROP_FPS)
                if not math.isfinite(fps) or fps <= 0:
                    fps = 25
                frame_no, next_sample = 0, 0.0
                sequence = 0
                reader = None if local_video else LatestFrames(cap)
                while not self.stop_event.is_set():
                    if reader is not None:
                        item = reader.next(sequence)
                        if item is None:
                            if not reader.alive:
                                break
                            continue
                        sequence, (frame, captured_at) = item
                    else:
                        ok, frame = cap.read()
                        if not ok:
                            break
                    frame_no += 1
                    seconds = (frame_no - 1) / fps if local_video else captured_at - origin
                    if seconds < next_sample:
                        continue
                    next_sample = seconds + 1 / self.cfg['sample_fps']
                    people_result = person_model.track(frame, persist=True, tracker='bytetrack.yaml',
                                                       classes=person_ids, **common)[0]
                    phone_result = phone_model.predict(frame, classes=phone_ids, **common)[0]
                    people = {}
                    if people_result.boxes.id is not None:
                        people = {int(track): box.tolist() for track, box in zip(
                            people_result.boxes.id.cpu(), people_result.boxes.xyxy.cpu())}
                    phones = phone_result.boxes.xyxy.cpu().tolist()
                    h, w = frame.shape[:2]
                    zones = [(z['name'], np.array([[x*w, y*h] for x, y in z['points']], dtype=np.int32))
                             for z in self.camera.get('zones', [])]
                    observations = {}
                    for track in associate(people, phones):
                        box = people[track]
                        center = ((box[0] + box[2])/2, (box[1] + box[3])/2)
                        if not zones:
                            observations[track] = 'Seluruh gambar'
                        else:
                            for name, polygon in zones:
                                if cv2.pointPolygonTest(polygon, center, False) >= 0:
                                    observations[track] = name
                                    break
                    actions = gate.step(seconds, observations)
                    for name, polygon in zones:
                        cv2.polylines(frame, [polygon], True, (200, 180, 60), 2)
                    for track, box in people.items():
                        x1, y1, x2, y2 = map(int, box)
                        candidate = gate.states.get(track)
                        confirmed = candidate is not None and seconds - candidate.start >= self.cfg['minimum_seconds'] and track in observations
                        color = (0, 160, 255) if track in observations else (80, 200, 80)
                        label = 'PHONE PROXIMITY' if confirmed else ('CANDIDATE' if track in observations else 'PERSON')
                        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                        cv2.putText(frame, f'Track {track}: {label}', (x1, max(y1-8, 20)),
                                    cv2.FONT_HERSHEY_SIMPLEX, .5, color, 1)
                    for box in phones:
                        x1, y1, x2, y2 = map(int, box)
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 220, 255), 2)
                    # Dashboard preview only; inference above uses original resolution.
                    if w > 1280:
                        frame = cv2.resize(frame, (1280, round(h * 1280 / w)))
                    ok, encoded = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
                    jpeg = encoded.tobytes() if ok else None
                    self.apply(actions, jpeg)
                    confirmed_count = sum(s.event_id is not None for s in gate.states.values())
                    with self.lock:
                        self.jpeg = jpeg
                    self.set_state(status='running', people=len(people), candidates=len(observations),
                                   confirmed=confirmed_count, media_seconds=round(seconds, 1))
                    if not local_video:
                        self.stop_event.wait(max(0, next_sample - (time.monotonic() - origin)))
                self.apply(gate.close(), reason='ended' if local_video else 'interrupted')
                if reader is not None:
                    reader.close()
                    reader = None
                cap.release()
                self.reset_frame()
                self.set_state(status='finished' if local_video else 'offline')
                if local_video or self.stop_event.wait(5):
                    break
        except Exception as exc:
            # Never log raw exception text: OpenCV/URLs may contain camera credentials.
            log.error('Camera %s failed (%s); check config, source, model classes and dependencies',
                      self.camera['id'], type(exc).__name__)
            self.reset_frame()
            self.set_state(status='error', error='Periksa sumber, model, kelas dan dependensi pada konfigurasi.')
        finally:
            self.apply(gate.close(), reason='interrupted')
            if reader is not None:
                reader.close()
            if cap is not None:
                cap.release()
