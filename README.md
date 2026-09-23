# QuizSpark Docker 3.1

เว็บตอบคำถามภาษาไทย/อังกฤษตามสเปก QuizSpark พร้อม backend สำหรับเล่นหลายเครื่องจริง
ใช้ Python + aiohttp + SQLite และ HTML/CSS/JavaScript โดยไม่มี frontend build step

## เริ่มใช้งาน

ต้องมี Docker Engine และ Docker Compose v2 บนเครื่องเป้าหมาย

```bash
unzip quizspark-docker-v3.1.zip
cd quizspark-docker
docker compose up -d --build
docker compose exec quizspark cat /app/data/admin-password
```

เปิด `http://SERVER_IP:8080` เลือก **จัดเกม** หรือ **จัดการชุดคำถาม** แล้วใช้รหัสผ่านที่ได้จากคำสั่งสุดท้าย
ผู้เล่นเปิด URL เดียวกัน กรอก PIN 6 หลักและชื่อเล่น โดยไม่ต้องมีบัญชี
ใช้ IP หรือชื่อโดเมนที่โทรศัพท์ของผู้เล่นเข้าถึงได้ แทน `localhost` บนหน้าจอผู้จัด

หากต้องการกำหนดรหัสผ่าน/พอร์ตเอง ให้คัดลอก `.env.example` เป็น `.env` แล้วแก้ค่า **ก่อนเริ่ม**:

```bash
cp .env.example .env
# แก้ ADMIN_PASSWORD และ HOST_PORT ตามต้องการ
docker compose up -d --build
```

เมื่อกำหนด `ADMIN_PASSWORD` ระบบจะใช้ค่านั้นแทนรหัสที่สร้างอัตโนมัติ
ไฟล์ `admin-password` อาจไม่มี หรือเป็นรหัสเดิมที่ไม่ถูกใช้งานเมื่อมีค่า override
รหัสนี้ใช้สำหรับผู้จัดเกมร่วมกัน ยังไม่มีบัญชีผู้จัดแยกรายบุคคล

## ไฟล์อัปโหลดอยู่ที่ไหน

| ข้อมูล | ตำแหน่งภายใน container |
|---|---|
| รูปคำถามและรูปคำอธิบาย | `/app/data/uploads/` |
| ต้นฉบับ JSON ที่นำเข้า | `/app/data/imports/` |
| ชุดคำถามและการตั้งค่า | `/app/data/quizspark.sqlite3` |
| รหัสผ่านที่สร้างอัตโนมัติ | `/app/data/admin-password` |

Compose ผูก named volume **`quizspark_data`** เข้ากับ `/app/data`:

```yaml
volumes:
  - quizspark_data:/app/data
```

แอปอ่านและเขียนไฟล์ที่ path ภายใน container ขณะที่ Docker volume เก็บข้อมูลไว้ข้ามการ restart, rebuild และ recreate container
`docker compose down` เก็บ volume ไว้; **อย่าใช้ `docker compose down -v` หากต้องการเก็บข้อมูล**
ไฟล์ runtime ไม่ได้ฝังใน Docker image และการย้าย image เพียงอย่างเดียวไม่ย้ายข้อมูลอัปโหลด ต้องสำรอง/ย้าย volume ด้วย

รูปอัปโหลดรองรับ PNG/JPEG/WebP/GIF สูงสุด 10 MB ต่อไฟล์ ตรวจสอบว่าเป็นภาพจริงก่อนบันทึก
ใช้ชื่อไฟล์จาก SHA-256 เพื่อตัดปัญหาชื่อซ้ำและ path traversal โดยเก็บ bytes ภาพต้นฉบับ
ไฟล์นำเข้า JSON รองรับสูงสุด 50 MB และเก็บต้นฉบับไว้ใน `imports/` หลังผ่านการตรวจสอบ
รูปที่กรอกเป็น URL จะถูกโหลดจาก URL นั้นโดยเบราว์เซอร์ หากต้องการเก็บรูปบนเซิร์ฟเวอร์ด้วย ให้อัปโหลดไฟล์ภาพ
ภาพใน JSON แบบ Base64 จะถูกแปลงเป็นไฟล์จริงใน `uploads/`

การลบ quiz ไม่ลบรูปภาพอัตโนมัติ เพื่อรักษารูปที่อาจถูกอ้างอิงจาก quiz อื่น

## ฟังก์ชันที่มี

- ภาษาไทย/อังกฤษ, เปิด–ปิดเสียงสังเคราะห์, หน้าผู้จัดและหน้าผู้เล่นที่รองรับมือถือ
- เกม PIN 6 หลัก, คัดลอกลิงก์เข้าร่วม, lobby แบบสด, เพิ่มบอตและนำผู้เล่นออก
- คำถาม 4 ตัวเลือกและพิมพ์คำตอบ พร้อมรูปคำถามและรูปคำอธิบาย
- จับเวลาและตรวจคำตอบฝั่ง server, คะแนนตามความเร็ว, streak, กราฟคำตอบ, top 5 และ podium
- แก้ไข quiz, import/export JSON พร้อมฝังรูปอัปโหลดในไฟล์ export เพื่อย้ายเครื่องได้
- โหมดสองหน้าจอด้วย iframe สำหรับทดสอบในหน้าต่างเดียว
- เชื่อมต่อ WebSocket ใหม่และกลับเข้าเกมเดิมเมื่อ refresh/เครือข่ายหลุด
- ปุ่มนำเข้าข้อมูล `QuizSpark_quizzes_v3` เดิม เมื่อพบ localStorage ใน origin ปัจจุบัน
- ไม่มี CDN หรือบริการภายนอกที่ต้องเรียกใช้ขณะเล่น ยกเว้นรูป URL ที่ผู้จัดใส่เอง
- รวมฟอนต์ภาษาไทย Noto Sans Thai ไว้ใน image ไม่ต้องโหลดจาก Google Fonts

คะแนนถูกคำนวณจากเวลา server:

```text
correct: round(1000 * (1 - elapsed / (time_limit * 2)))
incorrect / unanswered: 0
```

ส่งได้หนึ่งคำตอบต่อรอบ และไม่ส่งเฉลยให้ผู้เล่นก่อนจบรอบ
คำตอบแบบข้อความเปรียบเทียบหลัง Unicode NFKC, ตัดช่องว่างหัวท้าย และ casefold
ลำดับเมื่อคะแนนเท่ากันใช้ผู้เข้าร่วมก่อน

## สิ่งที่ปรับจากสเปกต้นฉบับ

| สเปกต้นฉบับ | รุ่น Docker |
|---|---|
| BroadcastChannel ระหว่างแท็บ | WebSocket เล่นข้ามเครื่องได้ |
| localStorage เก็บ quiz | SQLite ใน volume ใช้ร่วมกันทุกเครื่อง |
| ภาพ Base64 ใน browser | ไฟล์ภาพจริงใน container + volume |
| single HTML ไม่มี backend | หน้าเว็บ `app/static/index.html` + Python backend |
| Tailwind/Font Awesome/Confetti CDN | CSS/สัญลักษณ์/Canvas ในตัว ใช้งานโดยไม่เรียก CDN |
| QR placeholder | PIN ขนาดใหญ่และปุ่มคัดลอกลิงก์ ยังไม่สร้าง QR จริง |

## ดูสถานะและอัปเดต

```bash
docker compose ps
docker compose logs --tail=100 quizspark
curl http://localhost:8080/health
docker compose up -d --build
```

Quiz และไฟล์อัปโหลดคงอยู่ใน volume แต่ **เกมที่กำลังเล่นอยู่เก็บในหน่วยความจำและจบลงเมื่อ server restart**
เปิดเกมใหม่หลังอัปเดต ระบบใช้ process เดียว; ยังไม่รองรับหลาย replica/หลาย worker
ตั้ง `MAX_PLAYERS` ได้ (ค่าเริ่มต้น 200 ต่อห้อง) เป็นขีดจำกัดรับผู้เล่น ไม่ใช่ผลรับรองสมรรถนะ
รุ่น 3.1 ปรับเส้นทางรับคำตอบสำหรับ 200 คน: ยืนยันกลับเฉพาะผู้ตอบ,
รวมการอัปเดตหน้าผู้จัดทุก 200 ms และส่งสถานะให้ทุกคนเมื่อเปลี่ยนช่วงเกม
ผลทดสอบและข้อจำกัดอยู่ใน `docs/PERFORMANCE.md`; ต้องทดสอบผ่าน URL จริงของระบบอีกครั้ง
ห้องปิดถูกล้างหลัง 5 นาที ห้องอื่นหมดอายุหลังไม่มีคำสั่งผู้จัด 6 ชั่วโมง
token ผู้จัดหมดอายุภายใน 12 ชั่วโมงหรือเมื่อ server restart

## สำรองและกู้คืน

หยุดเกมก่อนสำรองเพื่อให้ SQLite/WAL และไฟล์อัปโหลดเป็น snapshot ชุดเดียวกัน:

```bash
docker compose stop quizspark
docker run --rm --user 0:0 --entrypoint tar \
  -v quizspark_data:/data:ro -v "$PWD":/backup \
  quizspark:3.1 -czf /backup/quizspark-data.tar.gz -C /data .
docker compose start quizspark
```

กู้คืนลง volume **ใหม่หรือว่าง** บนเครื่องที่ build image แล้ว:

```bash
docker compose stop quizspark
docker volume create quizspark_data
docker run --rm --user 0:0 --entrypoint tar \
  -v quizspark_data:/data -v "$PWD":/backup:ro \
  quizspark:3.1 -xzf /backup/quizspark-data.tar.gz -C /data
docker compose up -d
```

หาก volume ปัจจุบันมีข้อมูล ให้สำรองและจัดการ volume เดิมก่อนกู้คืน ไม่ควรแตกไฟล์ทับฐานข้อมูลที่มี WAL เก่าค้างอยู่

## NGINX / HTTPS

มีตัวอย่าง `docs/nginx.conf.example` สำหรับ reverse proxy ที่ root path ของ hostname
ส่ง `Upgrade`, `Connection` และ `Host` เพื่อรองรับ WebSocket
เมื่อติดตั้งหลัง HTTPS เว็บจะเลือก `wss://` อัตโนมัติ
หาก nginx อยู่บนเครื่องเดียวกัน กำหนด `BIND_ADDRESS=127.0.0.1` ใน `.env`
ใช้ HTTPS เมื่อเปิดให้เข้าถึงผ่านอินเทอร์เน็ตเพื่อเข้ารหัสรหัสผ่านและข้อมูลเกม
ลิงก์ภาพอัปโหลดเปิดอ่านได้สำหรับผู้มี URL เพื่อให้ผู้เล่นโหลดภาพระหว่างเกม

## ทดสอบแบบไม่ใช้ Docker

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover -s tests -v
DATA_DIR=./data PORT=8080 python app/server.py
```

ชุดทดสอบครอบคลุมการเก็บภาพ/quiz หลังสร้าง server ใหม่, import/export,
การซ่อนเฉลย, MCQ, open-ended, deadline, คะแนน, reconnect และการแยกสิทธิ์ผู้จัด/ผู้เล่น

การ build ครั้งแรกต้องดาวน์โหลด Python image และ dependencies; หลัง build แล้วแอปรันได้โดยไม่เรียกบริการภายนอก

## อ้างอิง

- [aiohttp 3.13.5 server quickstart](https://docs.aiohttp.org/en/v3.13.5/web_quickstart.html)
- [Docker volumes](https://docs.docker.com/engine/storage/volumes/)

รายละเอียดการตรวจสอบแพ็กเกจนี้อยู่ใน `docs/VERIFICATION.md`

## อัปเดตจาก 3.0 เป็น 3.1

จบเกมที่กำลังเล่นก่อน แล้วแตก ZIP ทับโฟลเดอร์ `quizspark-docker` เดิม
เก็บ `.env` และการตั้งค่า proxy เดิมไว้ ZIP ไม่มีไฟล์ `.env` หรือข้อมูล runtime

```bash
cd quizspark-docker
docker compose up -d --build
curl http://localhost:8080/health
```

ผล health ควรแสดง `"version":"3.1-docker"` ระบบยังใช้ named volume
`quizspark_data` เดิมและ schema เดิม จึงเก็บชุดคำถาม รูปอัปโหลด และ JSON นำเข้าต่อได้
การ restart จบห้องเกมปัจจุบัน และผู้จัดต้องเข้าสู่ระบบใหม่

## ทดสอบ 200 คนบนระบบจริง

บนเครื่องสร้างโหลดอีกเครื่อง ใช้ Python 3.10 ขึ้นไปและ dependency สำหรับสคริปต์:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install aiohttp==3.13.5
python tools/stress_test.py --url https://your-server.example \
  --levels 50,100,200 --rounds 5 --output results/step-test.json
```

สคริปต์ถามรหัสผู้จัด สร้างห้องทดสอบ เล่นจนจบ และลบเฉพาะ quiz ที่สร้าง
ค่าเริ่มต้นตอบพร้อมกัน เพิ่ม `--answer-spread 10` เพื่อให้ทยอยตอบภายใน 10 วินาที
เกณฑ์เริ่มต้น: 200/200 คำตอบทุกข้อ, ack p95 ≤ 1,000 ms, ไม่มีผู้เล่นหลุด

สคริปต์พัก 65 วินาทีระหว่างระดับ เพราะ server ยังจำกัด connection/join
300 ครั้ง/IP/60 วินาที หลัง proxy อาจนับผู้เล่นทั้งหมดเป็น IP เดียว
ถ้ารันหลายคำสั่งต่อกัน ให้เว้นอย่างน้อย 65 วินาทีระหว่างการทดสอบ
HTTP 429/`rate_limit` ต้องแยกจากผลความเร็วการประมวลผล

สำหรับทำซ้ำ benchmark ในเครื่องทดสอบโดยใช้ server/client คนละ process:

```bash
python tests/run_load_tests.py
```

คำสั่งนี้เปิด server ชั่วคราวบน loopback และใช้ข้อมูลทดสอบใน temporary directory
อ่านวิธีวัดและผลจริงใน `docs/PERFORMANCE.md`
