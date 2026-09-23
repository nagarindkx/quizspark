# QuizSpark Docker

เว็บเกมตอบคำถามแบบเรียลไทม์สำหรับห้องเรียนและกิจกรรมกลุ่ม รองรับภาษาไทย/อังกฤษ ผู้จัดเปิดเกมบนจอหลัก ผู้เล่นเข้าร่วมจากโทรศัพท์หรือคอมพิวเตอร์ด้วย PIN 6 หลัก

ระบบใช้ **Python + aiohttp + WebSocket + SQLite** รันด้วย Docker Compose บริการเดียว และเก็บชุดคำถามกับไฟล์อัปโหลดใน Docker volume

## เริ่มใช้งาน

เครื่องเซิร์ฟเวอร์ต้องมี Docker Engine, Docker Compose v2 และ `unzip` การ build ครั้งแรกต้องเข้าถึง registry ของ Docker image และแพ็กเกจ Python ได้

```bash
unzip quizspark-docker.zip
cd quizspark-docker
docker compose up -d --build
```

ดูรหัสผ่านผู้จัดเกมที่ระบบสร้างให้:

```bash
docker compose exec quizspark cat /app/data/admin-password
```

เปิด `http://SERVER_IP:8080` โดยแทน `SERVER_IP` ด้วย IP หรือชื่อเครื่องที่ผู้เล่นเข้าถึงได้ เลือก **จัดเกม** หรือ **จัดการชุดคำถาม** แล้วกรอกรหัสผ่าน

ผู้เล่นเปิด URL เดียวกัน เลือก **เข้าร่วมเกม** และกรอก PIN พร้อมชื่อเล่น โดยไม่ต้องสมัครสมาชิก ใช้ที่อยู่เซิร์ฟเวอร์แทน `localhost` เมื่อเข้าจากเครื่องอื่น

ตรวจสอบสถานะ:

```bash
docker compose ps
curl -fsS http://localhost:8080/health
```

ผลตอบกลับเมื่อแอปพร้อมใช้งาน:

```json
{"status": "ok", "version": "3.0-docker"}
```

## ความสามารถ

- จัดเกมหลายอุปกรณ์ผ่าน WebSocket พร้อม lobby รายชื่อผู้เล่น และจำนวนคำตอบแบบสด
- คำถามแบบเลือกตอบ 4 ตัวเลือก และแบบพิมพ์คำตอบ
- รูปประกอบคำถาม คำอธิบายเฉลย และรูปประกอบคำอธิบาย
- จับเวลา ตรวจคำตอบ และคิดคะแนนตามความเร็วที่ฝั่งเซิร์ฟเวอร์
- แสดงการกระจายคำตอบ คะแนนสะสม การตอบถูกต่อเนื่อง และ podium ผู้ชนะ
- สร้าง แก้ไข ลบ นำเข้า และส่งออกชุดคำถาม JSON
- เพิ่มบอตและนำผู้เล่นออกระหว่างรอเริ่มเกม
- ทดลองหน้าผู้จัดและหน้าผู้เล่นพร้อมกันด้วยโหมดสองหน้าจอ
- สลับภาษาไทย/อังกฤษ เปิด–ปิดเสียง และกลับเข้าเกมเดิมหลัง refresh หรือเครือข่ายหลุด
- รวม CSS, JavaScript และฟอนต์ภาษาไทยไว้ในโครงการ ไม่ต้องเรียก CDN ขณะเล่น

รูปที่ผู้จัดใส่เป็น URL ภายนอกยังต้องเข้าถึงต้นทางนั้น หากต้องการให้รูปอยู่บนเซิร์ฟเวอร์นี้ ให้อัปโหลดไฟล์ภาพ

## ตั้งค่าด้วย `.env`

คัดลอกไฟล์ตัวอย่างแล้วแก้ค่าที่ต้องการ:

```bash
cp .env.example .env
```

| ตัวแปร | ค่าเริ่มต้น | ความหมาย |
|---|---|---|
| `ADMIN_PASSWORD` | ว่าง | รหัสผ่านผู้จัดเกม ถ้าว่างจะใช้รหัสที่สร้างและเก็บใน volume |
| `HOST_PORT` | `8080` | พอร์ตที่เปิดบนเครื่อง host |
| `BIND_ADDRESS` | `0.0.0.0` | IP ของ host ที่รับการเชื่อมต่อ |
| `MAX_UPLOAD_MB` | `10` | ขนาดสูงสุดต่อรูปอัปโหลด |
| `MAX_IMPORT_MB` | `50` | ขนาดสูงสุดต่อไฟล์ JSON ที่นำเข้า |
| `MAX_PLAYERS` | `200` | จำนวนผู้เล่นสูงสุดต่อห้อง รวมบอต |
| `LOG_LEVEL` | `INFO` | ระดับ log ของแอป |

ตัวอย่างเปลี่ยนพอร์ตเป็น `8090`:

```dotenv
ADMIN_PASSWORD=
HOST_PORT=8090
BIND_ADDRESS=0.0.0.0
MAX_UPLOAD_MB=10
MAX_IMPORT_MB=50
MAX_PLAYERS=200
LOG_LEVEL=INFO
```

หลังแก้ `.env` ให้ใช้คำสั่งนี้เพื่อให้ container รับค่าใหม่:

```bash
docker compose up -d
```

จากตัวอย่าง เข้าเว็บที่ `http://SERVER_IP:8090` พอร์ตภายใน container ยังคงเป็น `8080`

เมื่อกำหนด `ADMIN_PASSWORD` ระบบจะใช้ค่านั้นแทนรหัสในไฟล์ `admin-password` ไฟล์ดังกล่าวอาจไม่มี หรือมีรหัสเดิมที่ไม่ได้ใช้งาน จึงไม่ควรใช้คำสั่ง `cat` เพื่อหารหัสเมื่อกำหนดค่า override ไว้แล้ว

ผู้จัดทุกคนใช้รหัสผ่านร่วมกัน รุ่นนี้ยังไม่มีบัญชีผู้จัดแยกรายบุคคล

## การใช้งาน

### ผู้จัดเกม

1. เปิดเว็บ เลือก **จัดเกม** และเข้าสู่ระบบด้วยรหัสผ่านผู้จัด
2. เลือกชุดคำถาม ระบบจะสร้างห้องและแสดง PIN 6 หลัก
3. ให้ผู้เล่นเปิด URL ของเซิร์ฟเวอร์และกรอก PIN หรือใช้ปุ่ม **คัดลอกลิงก์เกม**
4. เมื่อมีผู้เล่นอย่างน้อยหนึ่งคน กด **เริ่มเกม** ใช้ **เพิ่มบอต** เมื่อต้องการทดลอง
5. หลังเฉลยแต่ละข้อ กด **ดูตารางคะแนน** แล้วไปข้อถัดไป
6. เมื่อครบทุกข้อ กด **ประกาศผลผู้ชนะ**

### ผู้เล่น

กรอก PIN ชื่อเล่น และเลือกอีโมจิ จากนั้นรอผู้จัดเริ่มเกม แต่ละข้อส่งคำตอบได้ครั้งเดียว ระบบแสดงคะแนนและคำอธิบายหลังจบรอบ

การกลับเข้าเกมเดิมอาศัยข้อมูล session ในแท็บเบราว์เซอร์นั้น การ refresh รองรับ แต่การเปิดแท็บใหม่ไม่ได้รับประกันว่าจะกลับเป็นผู้เล่นคนเดิม

### สร้างชุดคำถาม

เลือก **จัดการชุดคำถาม → สร้างชุดคำถาม** กำหนดชื่อ หมวดหมู่ และรายละเอียดแต่ละข้อ แล้วกด **บันทึกชุดคำถาม**

| รายการ | เงื่อนไข |
|---|---|
| จำนวนคำถาม | 1–100 ข้อต่อชุด |
| แบบเลือกตอบ | มีตัวเลือกไม่ว่าง 4 ตัว และคำตอบถูก 1 ตัว |
| แบบพิมพ์คำตอบ | มีคำตอบที่ยอมรับ 1–50 ค่า คั่นด้วยจุลภาคในหน้าจอแก้ไข |
| เวลาตอบ | จำนวนเต็ม 5–300 วินาทีต่อข้อ |
| รูปภาพ | PNG, JPEG, WebP หรือ GIF ไม่เกินขนาดที่ตั้งไว้ |
| คำอธิบายและภาพเฉลย | ไม่บังคับ |

คำตอบแบบพิมพ์จะปรับ Unicode ด้วย NFKC ตัดช่องว่างหัวท้าย และเปรียบเทียบโดยไม่แยกตัวพิมพ์ใหญ่–เล็ก เช่น `Au`, `au` และ ` AU ` ถือว่าตรงกันเมื่อกำหนดคำตอบเป็น `Au`

## ไฟล์และข้อมูลถาวร

| ข้อมูล | ตำแหน่งภายใน container |
|---|---|
| ชุดคำถามและการตั้งค่าฐานข้อมูล | `/app/data/quizspark.sqlite3` |
| รูปคำถามและรูปคำอธิบาย | `/app/data/uploads/` |
| ต้นฉบับ JSON ที่นำเข้าสำเร็จ | `/app/data/imports/` |
| รหัสผ่านที่ระบบสร้างอัตโนมัติ | `/app/data/admin-password` |

ใน `compose.yaml` มี named volume ชื่อ **`quizspark_data`** ผูกกับ `/app/data` แอปจึงอ่านและเขียนไฟล์ภายใน container โดยมี volume เก็บข้อมูลไว้ข้ามการ restart, rebuild หรือ recreate

```yaml
services:
  quizspark:
    volumes:
      - quizspark_data:/app/data

volumes:
  quizspark_data:
    name: quizspark_data
```

ตัวอย่างด้านบนเป็นเฉพาะส่วนตั้งค่า volume ให้ใช้ไฟล์ `compose.yaml` เต็มที่มากับโครงการในการรัน

รูปอัปโหลดถูกตรวจสอบว่าเป็นภาพจริง และตั้งชื่อด้วย SHA-256 ของเนื้อหา รูปซ้ำจึงใช้ไฟล์เดียวกัน ส่วน JSON ที่นำเข้าจะเก็บต้นฉบับด้วยชื่อ UUID

การลบชุดคำถาม **ไม่ลบรูปภาพอัตโนมัติ** เพราะชุดคำถามอื่นอาจใช้ภาพเดียวกัน ไฟล์เหล่านี้ไม่ได้ฝังใน Docker image การย้าย image อย่างเดียวจึงไม่ย้ายข้อมูลอัปโหลดตามไปด้วย

`docker compose down` เก็บ volume ไว้ แต่ **`docker compose down -v` จะลบ volume ที่ Compose จัดการ รวมถึงข้อมูลในนั้น**

## นำเข้าและส่งออก JSON

ในหน้าจัดการชุดคำถาม ใช้ **นำเข้า JSON** เพื่อเพิ่มชุดคำถาม และ **ส่งออก JSON** เพื่อดาวน์โหลดชุดที่ต้องการ

- รับ JSON เป็น quiz object เดียว หรือ array ของ quiz objects สูงสุด 100 ชุดต่อไฟล์
- แต่ละการนำเข้าสร้าง quiz ID ใหม่ การนำเข้าไฟล์เดิมซ้ำจึงสร้างชุดคำถามเพิ่ม
- `correct` ของ MCQ ใช้ index **0–3** ตามลำดับตัวเลือก
- การส่งออกฝังรูปที่อัปโหลดไว้ใน JSON เป็น Base64 เพื่อย้ายไปเครื่องอื่นได้
- เมื่อนำเข้า Base64 ระบบจะแปลงกลับเป็นไฟล์ใน `uploads/`
- รูปที่อ้างด้วย URL ภายนอกจะยังเป็น URL ไม่ได้ดาวน์โหลดมาเก็บหรือฝังในไฟล์ export

ตัวอย่างไฟล์ที่นำเข้าได้:

```json
{
  "title": "Machine Learning เบื้องต้น",
  "category": "Machine Learning",
  "questions": [
    {
      "type": "mcq",
      "text": "งานใดเป็นตัวอย่างของ Classification?",
      "options": [
        "ทำนายราคาบ้านเป็นจำนวนเงิน",
        "จำแนกอีเมลว่าเป็นสแปมหรือไม่",
        "ทำนายอุณหภูมิเป็นองศาเซลเซียส",
        "ทำนายระยะเวลารอเป็นนาที"
      ],
      "correct": 1,
      "time": 20,
      "emoji": "💡",
      "image": "",
      "explanationText": "Classification ทำนายหมวดหมู่ เช่น สแปมหรือไม่ใช่สแปม",
      "explanationImage": ""
    },
    {
      "type": "open",
      "text": "AI ย่อมาจากอะไร?",
      "openAnswers": ["Artificial Intelligence", "ปัญญาประดิษฐ์"],
      "time": 30,
      "emoji": "🤖",
      "image": "",
      "explanationText": "Artificial Intelligence หมายถึงปัญญาประดิษฐ์",
      "explanationImage": ""
    }
  ]
}
```

หากมีข้อมูลจากรุ่นเดิมใน `localStorage` คีย์ `QuizSpark_quizzes_v3` หน้าเลือกชุดคำถามจะแสดงปุ่มนำเข้าจากเบราว์เซอร์ ปุ่มนี้อ่านได้เฉพาะข้อมูลของ origin ปัจจุบัน หากเปลี่ยน protocol, hostname หรือ port ให้ export/import JSON จากต้นทาง

## การคิดคะแนน

เซิร์ฟเวอร์วัดเวลาตั้งแต่เริ่มข้อจนได้รับคำตอบ แล้วคำนวณ:

```text
ตอบถูก: round(1000 × (1 − เวลาที่ใช้ / (เวลาที่กำหนด × 2)))
ตอบผิดหรือไม่ได้ตอบ: 0 คะแนน
```

ตัวอย่าง กำหนดเวลา 20 วินาที ตอบถูกเมื่อผ่านไป 10 วินาที ได้ 750 คะแนน การตอบถูกต่อเนื่องเพิ่ม streak และการตอบผิดหรือไม่ได้ตอบจะรีเซ็ต streak เป็น 0

คะแนนเท่ากันจัดอันดับตามผู้เข้าร่วมก่อน ผู้เล่นไม่ได้รับเฉลยหรือคำอธิบายก่อนจบรอบ

## คำสั่งดูแลระบบ

รันจากโฟลเดอร์ที่มี `compose.yaml`:

```bash
# ดูสถานะและ log
docker compose ps
docker compose logs --tail=100 -f quizspark

# หยุด / เปิดบริการเดิม
docker compose stop quizspark
docker compose start quizspark

# เริ่ม process ใหม่
docker compose restart quizspark

# Build และใช้ source code ที่แก้ไขแล้ว
docker compose up -d --build

# หยุดและถอด container โดยเก็บ volume ไว้
docker compose down
```

**เกมที่กำลังเล่นอยู่จะจบเมื่อ process หรือ container restart** เพราะห้องเกมและคะแนนขณะเล่นเก็บในหน่วยความจำ ชุดคำถามและไฟล์อัปโหลดยังคงอยู่ใน volume

## สำรองและกู้คืน

### สำรองข้อมูล

สำรองทั้ง `/app/data` เพื่อให้ได้ฐานข้อมูล รูปภาพ ต้นฉบับ JSON และรหัสผ่านอัตโนมัติ หยุดบริการก่อนเพื่อให้ข้อมูล SQLite และไฟล์อัปโหลดอยู่ในสภาพเดียวกัน

```bash
docker compose stop quizspark
docker run --rm --user 0:0 --entrypoint tar \
  -v quizspark_data:/data:ro \
  -v "$PWD":/backup \
  quizspark:3.0 -czf /backup/quizspark-data.tar.gz -C /data .
docker compose start quizspark
```

ไฟล์ `quizspark-data.tar.gz` อยู่ในโฟลเดอร์ปัจจุบัน คำสั่งนี้เขียนทับไฟล์สำรองชื่อเดียวกันถ้ามีอยู่แล้ว ให้เปลี่ยนชื่อหรือย้ายไฟล์สำรองก่อนทำรอบถัดไป

เก็บ source code และ `.env` แยกไว้ด้วย โดยเฉพาะเมื่อกำหนด `ADMIN_PASSWORD` เพราะไฟล์สำรอง volume ไม่รวม `.env`

### กู้คืนบนเครื่องใหม่

วาง source code, `.env` ที่ต้องการใช้ และไฟล์สำรองในโฟลเดอร์โครงการ ขั้นตอนนี้ใช้กับเครื่องที่ **ยังไม่มี volume `quizspark_data`**:

```bash
docker compose build
docker volume create quizspark_data
docker run --rm --user 0:0 --entrypoint tar \
  -v quizspark_data:/data \
  -v "$PWD":/backup:ro \
  quizspark:3.0 -xzf /backup/quizspark-data.tar.gz -C /data
docker compose up -d
```

หากเครื่องปลายทางมีข้อมูลเดิม ให้สำรองก่อนและเตรียม volume ว่างสำหรับการกู้คืน อย่าแตกไฟล์ทับฐานข้อมูลที่ใช้งานอยู่หรือมี SQLite WAL เก่าค้างอยู่

## ใช้งานหลัง NGINX

ตัวอย่างอยู่ที่ `docs/nginx.conf.example` สำหรับ proxy แอปที่ root path ของ hostname เช่น `quiz.example.org`

เมื่อ NGINX รันบนเครื่อง host เดียวกับ Docker ให้กำหนด `BIND_ADDRESS=127.0.0.1` ใน `.env` และ proxy ไป `http://127.0.0.1:8080` ถ้าเปลี่ยน `HOST_PORT` ต้องแก้พอร์ต upstream ให้ตรงกัน

ค่าหลักที่ต้องมีใน location ของ NGINX:

```nginx
proxy_http_version 1.1;
proxy_set_header Host $http_host;
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection $connection_upgrade;
proxy_read_timeout 3600s;
proxy_send_timeout 3600s;
proxy_buffering off;
```

ตัวแปร `$connection_upgrade` ต้องมี `map` ใน `http` context ตามไฟล์ตัวอย่าง กำหนด `client_max_body_size 51m;` สำหรับค่าเริ่มต้นนำเข้า JSON 50 MB และปรับให้สอดคล้องกันหากเพิ่มขนาดอัปโหลด

ไฟล์ตัวอย่างรับ HTTP ที่พอร์ต 80 ยังไม่ได้ตั้งใบรับรอง TLS ให้นำค่าที่เกี่ยวข้องไปใส่ใน HTTPS virtual host ของระบบ เมื่อหน้าเว็บใช้ HTTPS แอปจะเลือก `wss://` อัตโนมัติ

หาก NGINX อยู่ใน container แยก อย่าใช้ `127.0.0.1` เป็น upstream ของแอป ให้เชื่อมผ่าน Docker network และใช้ชื่อบริการ `quizspark:8080`

## โครงสร้างโครงการ

| ไฟล์หรือโฟลเดอร์ | หน้าที่ |
|---|---|
| `Dockerfile` | สร้าง image และรันแอปด้วย UID/GID `10001:10001` |
| `compose.yaml` | บริการ พอร์ต environment และ volume |
| `.env.example` | ตัวอย่างการตั้งค่า |
| `requirements.txt` | aiohttp `3.13.5` และ Pillow `12.3.0` |
| `app/server.py` | HTTP API, WebSocket, ห้องเกม และการจัดเก็บข้อมูล |
| `app/defaults.json` | ชุดคำถามตัวอย่างสำหรับฐานข้อมูลใหม่ |
| `app/static/index.html` | หน้าเว็บพร้อม CSS และ JavaScript |
| `app/static/fonts/` | ฟอนต์ภาษาไทยและใบอนุญาต |
| `tests/test_app.py` | Integration tests ของ HTTP/WebSocket |
| `tests/browser.cjs` | ทดสอบ workflow ผ่านเบราว์เซอร์ |
| `docs/VERIFICATION.md` | ขอบเขตและผลการตรวจสอบแพ็กเกจ |
| `docs/original-specification.md` | สเปกต้นฉบับ |

รุ่น Docker เปลี่ยนจาก `BroadcastChannel` เป็น WebSocket เพื่อเล่นข้ามเครื่อง เปลี่ยนการเก็บ quiz จาก `localStorage` เป็น SQLite และเก็บรูปอัปโหลดเป็นไฟล์จริง

## พัฒนาและทดสอบโดยไม่ใช้ Docker

ใช้ Python 3.12 ตามเวอร์ชันใน Docker image:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover -s tests -v
DATA_DIR=./data PORT=8080 python app/server.py
```

ข้อมูลจะอยู่ใน `./data` และรหัสผ่านที่สร้างอัตโนมัติอยู่ที่ `./data/admin-password`

การทดสอบหน้าจอเพิ่มเติมต้องมี Node.js, Playwright และ Chromium:

```bash
npm install --no-save playwright
npx playwright install chromium
node tests/browser.cjs
```

แอปและ Docker image ไม่ต้องใช้ Node.js ในการรันจริง

## แก้ปัญหาเบื้องต้น

| อาการ | จุดที่ควรตรวจ |
|---|---|
| เครื่องอื่นเปิดเว็บไม่ได้ | ใช้ IP/hostname ของเซิร์ฟเวอร์ ตรวจ `HOST_PORT`, `BIND_ADDRESS`, firewall และเส้นทางเครือข่าย |
| อ่าน `admin-password` ไม่พบไฟล์ | ตรวจว่า container พร้อมแล้ว และกำหนด `ADMIN_PASSWORD` ใน `.env` ไว้หรือไม่ |
| เปลี่ยน `.env` แต่ค่ายังเหมือนเดิม | ใช้ `docker compose up -d` เพื่อให้ Compose ปรับ container ตามค่าใหม่ |
| อัปโหลดขึ้น HTTP 413 | ตรวจทั้ง `MAX_UPLOAD_MB`/`MAX_IMPORT_MB` และ `client_max_body_size` ของ proxy |
| เปิดหน้าเว็บได้ แต่เข้าห้องไม่ได้หลัง proxy | ตรวจ WebSocket upgrade headers, upstream และการส่ง `Host` เดิม |
| นำเข้า JSON ไม่ผ่าน | ตรวจจำนวนข้อ ตัวเลือก 4 ค่า `correct` 0–3 เวลาจำนวนเต็ม 5–300 และ `openAnswers` ที่ไม่ว่าง |
| รูปหายเมื่อย้าย quiz ไปอีกเครื่อง | ใช้ปุ่มส่งออก JSON เพื่อฝังรูป แทนการคัดลอกเฉพาะ path `/uploads/...` |
| เจอ `Permission denied` หลังเปลี่ยนเป็น bind mount | โฟลเดอร์ข้อมูลต้องให้ UID/GID `10001:10001` เขียนได้ |
| PIN เดิมเข้าไม่ได้หลัง restart | ห้องเกมอยู่ในหน่วยความจำ ให้ผู้จัดเปิดเกมใหม่ |

## ขอบเขตของรุ่นนี้

- ใช้ process เดียว ไม่รองรับหลาย worker หรือหลาย replica ที่แชร์ห้องเกมเดียวกัน
- `MAX_PLAYERS=200` เป็นขีดจำกัดต่อห้อง ยังไม่ใช่ผล benchmark ผู้เล่นพร้อมกัน 200 คน
- ไม่เก็บห้องเกมและคะแนนขณะเล่นเพื่อกู้กลับหลัง server restart
- ยังไม่มี QR code จริง ใช้ PIN และปุ่มคัดลอกลิงก์เข้าร่วม
- ภาพอัปโหลดเปิดอ่านได้สำหรับผู้ที่มี URL เพื่อให้ผู้เล่นโหลดภาพได้
- session สำหรับจัดการ quiz หมดอายุหลัง 12 ชั่วโมง หรือเมื่อ server restart
- รายงานใน `docs/VERIFICATION.md` ระบุว่าทดสอบแอปและเบราว์เซอร์แล้ว แต่ยังไม่ได้ build/run Docker image ในสภาพแวดล้อมที่จัดทำแพ็กเกจ

## License

โค้ดโครงการใช้ MIT License ตามไฟล์ `LICENSE` ส่วน Noto Sans Thai ใช้ SIL Open Font License 1.1 ตาม `app/static/fonts/OFL.txt` ดูรายละเอียดส่วนประกอบภายนอกใน `docs/THIRD_PARTY.md`
