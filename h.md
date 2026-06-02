a1. GET /api/status

Mục đích: Lấy trạng thái MGMT server và số file .bin hiện có.

Request:

GET http://<device_ip>:8765/api/status

Response JSON:

{
  "ok": true,
  "status": "mgmt",
  "sd": true,
  "mounted": true,
  "file_count": 5
}

Ghi chú:

file_count: số lượng file .bin trong thư mục REC.
sd / mounted: trạng thái bộ nhớ có sẵn.
2. GET /api/filelist

Mục đích: Lấy danh sách chi tiết tất cả file .bin.

Request:

GET http://<device_ip>:8765/api/filelist

Response JSON:

{
  "ok": true,
  "files": [
    {"name": "rec2_20260601_154526.bin", "size": 12345, "size_human": "12.1 KB"},
    {"name": "rec2_20260601_154626.bin", "size": 23456, "size_human": "22.9 KB"}
  ]
}

Ghi chú:

name: tên file
size: kích thước file tính bằng byte
size_human: kích thước file dễ đọc
3. GET /api/download?name=<filename>

Mục đích: Tải file .bin cụ thể về client.

Request:

GET http://<device_ip>:8765/api/download?name=rec2_20260601_154526.bin

Response:

Trả về file .bin với header:
Content-Type: application/octet-stream
Content-Disposition: attachment; filename="rec2_20260601_154526.bin"
Content-Length: <file_size>
Nếu file không tồn tại: 404 Not Found
Nếu path traversal: 403 Forbidden
4. POST /api/upload

Mục đích: Upload một file .bin từ client.

Request:

Method: POST
Content-Type: multipart/form-data
Field: file (file .bin cần upload)

Ví dụ cURL:

curl -F "file=@rec2_20260601_154526.bin" http://<device_ip>:8765/api/upload

Response JSON:

{"ok": true, "name": "rec2_20260601_154526.bin"}

Ghi chú:

Nếu không phải multipart: trả 400
Nếu lỗi server: trả 500
5. POST /api/upload-all

Mục đích: Upload nhiều file cùng lúc.

Request:

Method: POST
Content-Type: multipart/form-data
Field: files[] (các file .bin)

Ví dụ cURL:

curl -F "files[]=@file1.bin" -F "files[]=@file2.bin" http://<device_ip>:8765/api/upload-all

Response JSON:

{"ok": true, "saved": ["file1.bin", "file2.bin"]}
6. DELETE /api/delete?name=<filename>

Mục đích: Xóa một file .bin cụ thể.

Request:

DELETE http://<device_ip>:8765/api/delete?name=rec2_20260601_154526.bin

Response JSON (thành công):

{"ok": true}

Ghi chú:

Nếu file không tồn tại: trả 404
Nếu path traversal: trả 403
7. DELETE /api/delete-all

Mục đích: Xóa tất cả file .bin trong thư mục REC.

Request:

DELETE http://<device_ip>:8765/api/delete-all

Response JSON:

{"ok": true, "deleted": 5}

Ghi chú:

deleted: số file đã xóa