"""End-to-end smoke test of the hub routing, driven headlessly.

Starts the hub on an ephemeral port, connects a fake student and a fake teacher
as raw WebSocket clients, and asserts that:

* the teacher receives a roster containing the student;
* a LOCK command from the teacher reaches the student;
* a thumbnail from the student reaches the teacher;
* a STATUS update updates the roster the teacher sees.

No display, no real screen capture — purely the protocol/routing layer.
"""

import asyncio
import json
import socket

import aiohttp
import pytest
from aiohttp import web

from hub.server import build_app
from shared import protocol as p


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


async def _recv_until(ws, mtype, timeout=5.0, where=None):
    """Return the first message of type `mtype` (optionally matching `where`)."""
    async def _loop():
        async for frame in ws:
            if frame.type == aiohttp.WSMsgType.TEXT:
                msg = json.loads(frame.data)
                if msg.get("type") == mtype and (where is None or where(msg)):
                    return msg
    return await asyncio.wait_for(_loop(), timeout)


@pytest.mark.asyncio
async def test_lock_thumbnail_and_status_flow():
    port = _free_port()
    runner = web.AppRunner(build_app())
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()
    url = f"http://127.0.0.1:{port}/ws"

    try:
        async with aiohttp.ClientSession() as sess:
            teacher = await sess.ws_connect(url)
            await teacher.send_str(p.make(p.HELLO, role=p.ROLE_TEACHER, name="t", room="r1"))

            student = await sess.ws_connect(url)
            await student.send_str(p.make(p.HELLO, role=p.ROLE_STUDENT, name="PC-1", room="r1"))

            # Teacher should see the student in a roster (first roster is empty).
            roster = await _recv_until(
                teacher, p.ROSTER, where=lambda m: len(m["students"]) > 0
            )
            names = [s["name"] for s in roster["students"]]
            assert "PC-1" in names
            student_id = roster["students"][0]["id"]

            # Teacher locks the student; student must receive LOCK.
            await teacher.send_str(p.make(p.LOCK, targets=[student_id], title="x", body="y"))
            lock_msg = await _recv_until(student, p.LOCK)
            assert lock_msg["title"] == "x"

            # Student acknowledges by reporting locked status.
            await student.send_str(p.make(p.STATUS, locked=True, active_window="Notepad"))
            updated = await _recv_until(
                teacher, p.ROSTER,
                where=lambda m: any(s["id"] == student_id and s["locked"] for s in m["students"]),
            )
            target = next(s for s in updated["students"] if s["id"] == student_id)
            assert target["locked"] is True
            assert target["active_window"] == "Notepad"

            # Student sends a thumbnail; teacher must receive it tagged by id.
            await student.send_str(p.make(p.THUMBNAIL, image="QUJD"))
            thumb = await _recv_until(teacher, p.THUMBNAIL)
            assert thumb["student_id"] == student_id
            assert thumb["image"] == "QUJD"

            await teacher.close()
            await student.close()
    finally:
        await runner.cleanup()
