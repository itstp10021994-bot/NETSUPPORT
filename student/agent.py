"""Student agent for the classroom management system.

The agent connects to the hub, announces itself, and then:

* periodically captures a *downscaled* JPEG thumbnail of the primary screen and
  sends it to the teacher console (only while a teacher has requested screens);
* reacts to teacher commands: show a lock overlay, hide it, or display a message;
* reports its lock status back to the hub.

Screen capture is intentionally low-resolution (thumbnails) so the console can
show a monitoring grid without streaming full-resolution video. The agent shows
a persistent on-screen banner so the student always knows it is running.

Run:
    python -m student.agent --hub ws://TEACHER_HOST:8765/ws --name "PC-01" --room class-a
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import io
import logging
import socket
import threading
from typing import Optional

import aiohttp

from shared import protocol as p
from student.ui import StudentUI, create_ui

log = logging.getLogger("student")


class ScreenGrabber:
    """Captures and JPEG-encodes a downscaled thumbnail of the primary monitor."""

    def __init__(self, max_width: int = 480, quality: int = 45) -> None:
        self.max_width = max_width
        self.quality = quality
        self._sct = None

    def _ensure(self) -> None:
        if self._sct is None:
            import mss  # local import: optional dependency

            self._sct = mss.mss()

    def capture_b64(self) -> Optional[str]:
        try:
            self._ensure()
            from PIL import Image

            monitor = self._sct.monitors[1]  # primary screen
            raw = self._sct.grab(monitor)
            img = Image.frombytes("RGB", raw.size, raw.rgb)
            if img.width > self.max_width:
                ratio = self.max_width / img.width
                img = img.resize((self.max_width, int(img.height * ratio)))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=self.quality)
            return base64.b64encode(buf.getvalue()).decode("ascii")
        except Exception as exc:
            log.debug("capture failed: %s", exc)
            return None


class StudentAgent:
    def __init__(self, hub_url: str, name: str, room: str, ui: StudentUI) -> None:
        self.hub_url = hub_url
        self.name = name
        self.room = room
        self.ui = ui
        self.grabber = ScreenGrabber()
        self.locked = False
        self.streaming = False
        self.stream_interval = 2.0  # seconds between thumbnails
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._stop = asyncio.Event()

    async def _send(self, message: str) -> None:
        if self._ws is not None and not self._ws.closed:
            await self._ws.send_str(message)

    async def _stream_loop(self) -> None:
        while not self._stop.is_set():
            if self.streaming and self._ws is not None:
                img = await asyncio.get_event_loop().run_in_executor(
                    None, self.grabber.capture_b64
                )
                if img:
                    await self._send(p.make(p.THUMBNAIL, image=img))
            await asyncio.sleep(self.stream_interval)

    async def _handle(self, msg: dict) -> None:
        mtype = msg.get("type")
        if mtype == p.LOCK:
            self.locked = True
            self.ui.show_lock(
                msg.get("title", "Screen locked"),
                msg.get("body", "Your teacher has locked this computer."),
            )
            await self._send(p.make(p.STATUS, locked=True))
            await self._send(p.make(p.ACK, action=p.LOCK))
        elif mtype == p.UNLOCK:
            self.locked = False
            self.ui.hide_lock()
            await self._send(p.make(p.STATUS, locked=False))
            await self._send(p.make(p.ACK, action=p.UNLOCK))
        elif mtype == p.MESSAGE:
            self.ui.show_message(msg.get("title", "Message"), msg.get("text", ""))
            await self._send(p.make(p.ACK, action=p.MESSAGE))
        elif mtype == p.REQUEST_THUMBNAILS:
            fps = float(msg.get("fps", 0.5) or 0.5)
            self.streaming = fps > 0
            self.stream_interval = max(0.5, 1.0 / fps) if fps > 0 else 2.0
            log.info("thumbnail streaming %s (every %.1fs)",
                     "on" if self.streaming else "off", self.stream_interval)
        elif mtype == p.PONG:
            pass

    async def _connect_once(self) -> None:
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(self.hub_url, heartbeat=30) as ws:
                self._ws = ws
                await ws.send_str(
                    p.make(p.HELLO, role=p.ROLE_STUDENT, name=self.name, room=self.room)
                )
                self.ui.set_connected(True, self.room)
                # Report initial status.
                await self._send(p.make(p.STATUS, locked=self.locked))
                async for frame in ws:
                    if frame.type == aiohttp.WSMsgType.TEXT:
                        await self._handle(p.parse(frame.data))
                    elif frame.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        break
        self._ws = None
        self.ui.set_connected(False, self.room)

    async def run(self) -> None:
        stream_task = asyncio.create_task(self._stream_loop())
        backoff = 1.0
        try:
            while not self._stop.is_set():
                try:
                    await self._connect_once()
                    backoff = 1.0
                except Exception as exc:
                    log.warning("connection lost: %s (retry in %.0fs)", exc, backoff)
                if self._stop.is_set():
                    break
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 15.0)
        finally:
            stream_task.cancel()

    def stop(self) -> None:
        self._stop.set()


def _default_name() -> str:
    try:
        return socket.gethostname()
    except Exception:
        return "student"


def main() -> None:
    parser = argparse.ArgumentParser(description="Classroom student agent")
    parser.add_argument("--hub", default="ws://127.0.0.1:8765/ws", help="Hub WebSocket URL")
    parser.add_argument("--name", default=_default_name(), help="Display name for this machine")
    parser.add_argument("--room", default="default", help="Classroom / room name")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

    ui = create_ui()
    agent = StudentAgent(args.hub, args.name, args.room, ui)

    # The asyncio networking runs on a background thread; the UI owns the main
    # thread (Tkinter requires this).
    loop = asyncio.new_event_loop()

    def _run_net() -> None:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(agent.run())

    net_thread = threading.Thread(target=_run_net, daemon=True)

    def _on_ready() -> None:
        net_thread.start()

    try:
        ui.run_forever(on_ready=_on_ready)
    except KeyboardInterrupt:
        pass
    finally:
        agent.stop()
        loop.call_soon_threadsafe(lambda: None)


if __name__ == "__main__":
    main()
