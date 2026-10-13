# Classroom Console — quản lý máy giáo viên & máy học sinh

Ứng dụng quản lý lớp học theo mô hình tương tự NetSupport School: giáo viên theo
dõi màn hình các máy học sinh theo thời gian thực, khóa/mở máy, và gửi tin nhắn.
Phần mềm **minh bạch**: máy học sinh luôn hiển thị một thanh báo cho biết đang
được quản lý — đúng chuẩn phần mềm lớp học, dùng cho môi trường được phép (lớp
học, phòng máy do nhà trường/đơn vị quản lý).

## Kiến trúc

```
┌────────────┐      WebSocket      ┌─────────┐      WebSocket      ┌──────────────┐
│  Trình duyệt│ ◄─────────────────► │   Hub   │ ◄─────────────────► │ Student agent │
│ (giáo viên) │   thumbnail/lệnh    │ (relay) │   thumbnail/lệnh    │  (máy học sinh)│
└────────────┘                     └─────────┘                     └──────────────┘
```

- **Hub** (`hub/server.py`): máy chủ WebSocket trung tâm, định tuyến theo "phòng"
  (room = lớp học). Không lưu trữ ảnh màn hình xuống đĩa, chỉ chuyển tiếp giữa
  các bên đang kết nối. Hub cũng phục vụ luôn trang web của giáo viên.
- **Teacher console** (`teacher/static/`): trang web lưới thumbnail + nút điều
  khiển (theo dõi, khóa tất cả, mở tất cả, gửi tin nhắn, thao tác từng máy).
- **Student agent** (`student/agent.py`): chụp thumbnail màn hình (độ phân giải
  thấp) gửi lên khi giáo viên yêu cầu, hiện overlay khi bị khóa, hiện popup tin
  nhắn. Có UI Tkinter khi có màn hình, tự chuyển chế độ headless khi không có.

## Cài đặt

```bash
pip install -r requirements.txt
# Trên Linux, máy học sinh cần Tkinter cho overlay khóa:  sudo apt install python3-tk
```

## Chạy

**1. Trên máy giáo viên** — khởi động hub (kiêm web console):

```bash
python -m hub.server --host 0.0.0.0 --port 8765
```

Mở trình duyệt tới `http://<IP-máy-giáo-viên>:8765/`, nhập tên phòng rồi
**Kết nối**.

**2. Trên mỗi máy học sinh** — chạy agent, trỏ về hub và cùng phòng:

```bash
python -m student.agent --hub ws://<IP-máy-giáo-viên>:8765/ws --name "PC-01" --room class-a
```

Máy học sinh sẽ xuất hiện trong lưới của giáo viên. Nhấn **▶ Theo dõi** để nhận
thumbnail, **🔒 Khóa tất cả** để khóa, hay dùng nút trên từng thẻ máy.

## Đóng gói & cài đặt

Có 2 cách triển khai.

### Cách A — Cài bằng pip (cần Python 3.9+ trên máy)

```bash
pip install .
# Sau khi cài có 2 lệnh:
classroom-hub --host 0.0.0.0 --port 8765          # máy giáo viên
classroom-student --hub ws://<IP-GV>:8765/ws --room class-a --name "PC-01"
```

### Cách B — File chạy độc lập (máy học sinh KHÔNG cần cài Python)

Dùng PyInstaller để tạo một file thực thi duy nhất cho mỗi vai trò. **Phải build
trên đúng hệ điều hành đích** (build .exe trên Windows, binary Linux trên Linux…
— PyInstaller không cross-compile).

```bash
# Windows:
packaging\build.bat
# Linux / macOS:
bash packaging/build.sh
```

Kết quả nằm trong `packaging/dist/`:

| File | Chạy ở đâu |
|------|-----------|
| `classroom-hub` / `classroom-hub.exe` | Máy giáo viên. Đã nhúng sẵn web console. |
| `classroom-student` / `classroom-student.exe` | Mỗi máy học sinh. Không cần Python. |

**Trên máy giáo viên:** chạy `classroom-hub.exe --port 8765`, rồi mở
`http://<IP-máy-giáo-viên>:8765/`.

**Trên mỗi máy học sinh:** chép `classroom-student.exe` và `run-student.bat`
(trong `packaging/`) vào cùng thư mục, sửa dòng `set HUB=` trong file .bat cho
đúng IP máy giáo viên, rồi chạy `run-student.bat`.

**Tự khởi động cùng Windows:** nhấn `Win+R`, gõ `shell:startup`, bỏ một shortcut
tới `run-student.bat` (hoặc `classroom-student.exe`) vào thư mục đó.

> Lưu ý: mở cổng 8765 trên tường lửa máy giáo viên để các máy học sinh kết nối
> được (hoặc tạo rule inbound cho `classroom-hub.exe`).

## Tính năng

| Tính năng | Trạng thái |
|-----------|-----------|
| Danh sách máy online theo phòng | ✅ |
| Thumbnail màn hình thời gian thực | ✅ |
| Khóa / mở khóa (một máy hoặc tất cả) | ✅ |
| Gửi tin nhắn (một máy hoặc cả lớp) | ✅ |
| Hiển thị cửa sổ đang mở của học sinh | ✅ (agent báo cáo qua STATUS) |
| Tự kết nối lại khi mất mạng | ✅ |

## Kiểm thử

```bash
python -m pytest tests/ --asyncio-mode=auto
```

Test chạy headless, kiểm tra toàn bộ luồng định tuyến của hub (roster, lock,
thumbnail, cập nhật trạng thái) mà không cần màn hình thật.

## Giao thức

Mọi thông điệp là JSON qua WebSocket, định nghĩa tập trung ở `shared/protocol.py`
(handshake `hello`, `roster`, `thumbnail`, `lock`/`unlock`, `message`,
`request_thumbnails`, `status`, `ack`).

## Lưu ý sử dụng

Công cụ này dành cho môi trường được phép quản lý (lớp học / phòng máy của tổ
chức). Máy học sinh luôn hiển thị thanh thông báo đang được quản lý; không có
chế độ ẩn/giám sát lén.
