"""Central hub for the classroom management system.

The hub is a lightweight WebSocket relay. Both the teacher console and the
student agents connect to it and join a "room" (a classroom). The hub keeps
track of who is online, forwards teacher commands to the targeted students,
and fans student screen thumbnails / status updates back to the teacher.

Run:
    python -m hub.server --host 0.0.0.0 --port 8765

The hub holds no persistent state and stores no screen captures on disk; it
only forwards messages between connected, consenting participants in a room.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from aiohttp import WSMsgType, web

from shared import protocol as p

log = logging.getLogger("hub")

HUB_KEY: "web.AppKey[Hub]" = web.AppKey("hub", object)


@dataclass
class Connection:
    ws: web.WebSocketResponse
    conn_id: str
    role: str
    name: str
    room: str
    locked: bool = False
    active_window: str = ""


@dataclass
class Room:
    name: str
    teachers: Dict[str, Connection] = field(default_factory=dict)
    students: Dict[str, Connection] = field(default_factory=dict)


class Hub:
    def __init__(self) -> None:
        self.rooms: Dict[str, Room] = {}

    def room(self, name: str) -> Room:
        return self.rooms.setdefault(name, Room(name=name))

    # -- roster helpers ----------------------------------------------------
    def roster_payload(self, room: Room) -> dict:
        return {
            "students": [
                {
                    "id": c.conn_id,
                    "name": c.name,
                    "online": True,
                    "locked": c.locked,
                    "active_window": c.active_window,
                }
                for c in room.students.values()
            ]
        }

    async def broadcast_to_teachers(self, room: Room, message: str) -> None:
        dead: List[str] = []
        for cid, conn in room.teachers.items():
            try:
                await conn.ws.send_str(message)
            except ConnectionError:
                dead.append(cid)
        for cid in dead:
            room.teachers.pop(cid, None)

    async def send_roster(self, room: Room) -> None:
        await self.broadcast_to_teachers(room, p.make(p.ROSTER, **self.roster_payload(room)))

    # -- connection lifecycle ---------------------------------------------
    async def register(self, conn: Connection) -> None:
        room = self.room(conn.room)
        if conn.role == p.ROLE_TEACHER:
            room.teachers[conn.conn_id] = conn
            # Send the teacher the current roster immediately.
            await conn.ws.send_str(p.make(p.ROSTER, **self.roster_payload(room)))
            log.info("teacher %s joined room %s", conn.name, conn.room)
        else:
            room.students[conn.conn_id] = conn
            await self.broadcast_to_teachers(
                room, p.make(p.STUDENT_JOINED, id=conn.conn_id, name=conn.name)
            )
            await self.send_roster(room)
            log.info("student %s joined room %s", conn.name, conn.room)

    async def unregister(self, conn: Connection) -> None:
        room = self.rooms.get(conn.room)
        if not room:
            return
        if conn.role == p.ROLE_TEACHER:
            room.teachers.pop(conn.conn_id, None)
        else:
            room.students.pop(conn.conn_id, None)
            await self.broadcast_to_teachers(
                room, p.make(p.STUDENT_LEFT, id=conn.conn_id, name=conn.name)
            )
            await self.send_roster(room)
        if not room.teachers and not room.students:
            self.rooms.pop(conn.room, None)

    # -- message routing ---------------------------------------------------
    def _resolve_targets(self, room: Room, targets) -> List[Connection]:
        if targets == "all" or targets is None:
            return list(room.students.values())
        if isinstance(targets, str):
            targets = [targets]
        return [room.students[t] for t in targets if t in room.students]

    async def handle_teacher_message(self, conn: Connection, msg: dict) -> None:
        room = self.room(conn.room)
        mtype = msg.get("type")

        if mtype in (p.LOCK, p.UNLOCK, p.MESSAGE, p.REQUEST_THUMBNAILS):
            students = self._resolve_targets(room, msg.get("targets"))
            forward = p.make(
                mtype,
                **{k: v for k, v in msg.items() if k not in ("type", "ts", "targets")},
            )
            for s in students:
                try:
                    await s.ws.send_str(forward)
                except ConnectionError:
                    pass
        elif mtype == p.PING:
            await conn.ws.send_str(p.make(p.PONG))
        else:
            log.debug("ignoring teacher message type=%s", mtype)

    async def handle_student_message(self, conn: Connection, msg: dict) -> None:
        room = self.room(conn.room)
        mtype = msg.get("type")

        if mtype == p.THUMBNAIL:
            fan = p.make(
                p.THUMBNAIL,
                student_id=conn.conn_id,
                image=msg.get("image", ""),
            )
            await self.broadcast_to_teachers(room, fan)
        elif mtype == p.STATUS:
            conn.locked = bool(msg.get("locked", conn.locked))
            conn.active_window = str(msg.get("active_window", conn.active_window))
            await self.send_roster(room)
        elif mtype == p.ACK:
            await self.broadcast_to_teachers(
                room,
                p.make(p.ACK, student_id=conn.conn_id, action=msg.get("action", "")),
            )
        elif mtype == p.PING:
            await conn.ws.send_str(p.make(p.PONG))


async def websocket_handler(request: web.Request) -> web.WebSocketResponse:
    hub: Hub = request.app[HUB_KEY]
    ws = web.WebSocketResponse(heartbeat=30, max_msg_size=16 * 1024 * 1024)
    await ws.prepare(request)

    conn: Optional[Connection] = None
    try:
        async for frame in ws:
            if frame.type != WSMsgType.TEXT:
                if frame.type == WSMsgType.ERROR:
                    log.warning("ws error: %s", ws.exception())
                continue

            msg = p.parse(frame.data)

            if conn is None:
                # First message must be a hello handshake.
                if msg.get("type") != p.HELLO:
                    await ws.send_str(p.make(p.ERROR, reason="expected-hello"))
                    await ws.close()
                    break
                role = msg.get("role")
                if role not in (p.ROLE_TEACHER, p.ROLE_STUDENT):
                    await ws.send_str(p.make(p.ERROR, reason="bad-role"))
                    await ws.close()
                    break
                conn = Connection(
                    ws=ws,
                    conn_id=uuid.uuid4().hex[:12],
                    role=role,
                    name=str(msg.get("name", "unknown"))[:64],
                    room=str(msg.get("room", "default"))[:64],
                )
                await hub.register(conn)
                await ws.send_str(p.make("welcome", id=conn.conn_id, room=conn.room))
                continue

            if conn.role == p.ROLE_TEACHER:
                await hub.handle_teacher_message(conn, msg)
            else:
                await hub.handle_student_message(conn, msg)
    finally:
        if conn is not None:
            await hub.unregister(conn)
    return ws


def build_app() -> web.Application:
    import os

    app = web.Application()
    app[HUB_KEY] = Hub()
    app.router.add_get("/ws", websocket_handler)

    async def health(_req: web.Request) -> web.StreamResponse:
        return web.json_response({"ok": True})

    app.router.add_get("/health", health)

    static_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "teacher",
        "static",
    )

    async def index(_req: web.Request) -> web.StreamResponse:
        return web.FileResponse(os.path.join(static_dir, "index.html"))

    app.router.add_get("/", index)
    # Serve the teacher console's static assets at the site root.
    app.router.add_static("/", static_dir, show_index=False)
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Classroom management hub")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    log.info("hub listening on ws://%s:%d/ws", args.host, args.port)
    web.run_app(build_app(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
