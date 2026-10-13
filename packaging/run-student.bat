@echo off
REM Launcher for the student machine. Place this next to classroom-student.exe.
REM Edit HUB and ROOM once, then double-click on each student PC.
REM
REM To auto-start at login: press Win+R, type  shell:startup , and put a
REM shortcut to this .bat (or to classroom-student.exe) in that folder.

set HUB=ws://192.168.1.10:8765/ws
set ROOM=class-a

REM %COMPUTERNAME% is used as the display name shown in the teacher console.
classroom-student.exe --hub %HUB% --room %ROOM% --name "%COMPUTERNAME%"
