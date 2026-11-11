from machine import Pin, SPI
import time
import gc
import socket
import ujson
import network
import mhz19
from dht import DHT22
from umqtt.simple import MQTTClient
from st7735 import TFT, TFTColor
from xglcd_font import XglcdFont

# ---------- настройки ----------
WIFI_SSID = 'name'
WIFI_PASSWORD = 'pass'

MQTT_BROKER = "ip_ad"
MQTT_PORT = 1883
MQTT_USER = "esp_client"
MQTT_PASSWORD = "pass"
MQTT_TOPIC = "esp_data"

WIFI_RETRY_MS = 30000      # как часто пробовать Wi-Fi
MQTT_RETRY_MS = 30000      # как часто пробовать MQTT
FORCE_PUBLISH_MS = 60000   # отправлять минимум раз в минуту

# ---------- железо ----------
red_led = Pin(26, Pin.OUT)     # проветривание
green_led = Pin(25, Pin.OUT)   # температура
Pin(21, Pin.OUT).value(1)      # подсветка дисплея

sensor_dht = DHT22(Pin(22))
sensor_mhz = mhz19.mhz19(2)

spi = SPI(2, baudrate=20000000, sck=Pin(18), mosi=Pin(23), miso=Pin(19))
tft = TFT(spi, 2, 4, 5)        # (spi, DC, RESET, CS)
tft.initr()
tft.rotation(1)
SCREEN_W = tft.size()[0]
WHITE = TFTColor(255, 255, 255)
BLACK = TFTColor(0, 0, 0)
tft.fill(WHITE)

FONT_H = 15
font = XglcdFont('font_converted.c', 16, FONT_H, start_letter=32, letter_count=224)


def draw_text(y, text):
    #Пишет строку на экране; юникод -> cp1251 для шрифта.
    x = 2
    for ch in text:
        o = ord(ch)
        if 0x410 <= o <= 0x44F:
            o = o - 0x410 + 0xC0       # А-Я, а-я
        elif o == 0x401:
            o = 0xA8                   # Ё
        elif o == 0x451:
            o = 0xB8                   # ё
        buf, w, h = font.get_letter(chr(o), BLACK, WHITE)
        if w == 0 or x + w > SCREEN_W:
            continue
        tft.image(x, y, x + w - 1, y + h - 1, buf)
        x += w
    tft.fillrect((x, y), (SCREEN_W - x, FONT_H), WHITE)   # стираем хвост старой строки


# ---------- сеть ----------
sta_if = network.WLAN(network.STA_IF)
sta_if.active(True)
client = None                      # не None = MQTT подключён
prev_message = None

now = time.ticks_ms()
last_wifi_try = time.ticks_add(now, -WIFI_RETRY_MS - 1)
last_mqtt_try = time.ticks_add(now, -MQTT_RETRY_MS - 1)
last_publish = now


def mqtt_close():
    global client
    if client is not None:
        try:
            client.sock.close()
        except Exception:
            pass
        client = None


def mqtt_connect():
    global client, prev_message
    try:
        # быстрая проверка брокера с таймаутом, чтобы цикл не зависал
        s = socket.socket()
        s.settimeout(3)
        try:
            s.connect(socket.getaddrinfo(MQTT_BROKER, MQTT_PORT)[0][-1])
        finally:
            s.close()
        client = MQTTClient("esp_client", MQTT_BROKER, port=MQTT_PORT,
                            user=MQTT_USER, password=MQTT_PASSWORD)
        client.connect()
        prev_message = None        # сразу отправим свежие данные
        print("MQTT connected")
    except Exception as e:
        print("MQTT connect error:", e)
        mqtt_close()


# ---------- основной цикл ----------
draw_text(54, "Запуск...")

while True:
    # 1. датчики (None, если датчик не ответил)
    temp = humidity = ppm = None
    try:
        sensor_dht.measure()
        temp = round(sensor_dht.temperature(), 2)
        humidity = round(sensor_dht.humidity(), 2)
    except Exception as e:
        print("DHT22 error:", e)
    try:
        sensor_mhz.get_data()
        ppm = sensor_mhz.ppm
    except Exception as e:
        print("MH-Z19 error:", e)

    # 2. оценка воздуха
    if ppm is None or ppm <= 0:
        msg, fresh_air = 'Нет данных CO2', False
    elif ppm <= 600:
        msg, fresh_air = 'Свежий воздух', False
    elif ppm <= 1000:
        msg, fresh_air = 'Допустимый уровень', False
    elif ppm <= 1500:
        msg, fresh_air = 'Плохое качество', True
    else:
        msg, fresh_air = 'Плохой воздух', True

    green_led.value(temp is not None and temp > 30)
    red_led.value(fresh_air)

    draw_text(6,   "Температура: " + ("--" if temp is None else str(temp) + "°С"))
    draw_text(30,  "Влажность: " + ("--" if humidity is None else str(humidity) + "%"))
    draw_text(54,  "ppm: " + ("--" if ppm is None else str(ppm)))
    draw_text(104, msg)

    # 3. сеть (не блокирует цикл)
    now = time.ticks_ms()
    wifi_ok = sta_if.isconnected()

    if not wifi_ok:
        mqtt_close()
        if time.ticks_diff(now, last_wifi_try) > WIFI_RETRY_MS:
            last_wifi_try = now
            print("Connecting to WiFi...")
            sta_if.disconnect()
            sta_if.connect(WIFI_SSID, WIFI_PASSWORD)
    elif client is None and time.ticks_diff(now, last_mqtt_try) > MQTT_RETRY_MS:
        last_mqtt_try = now
        mqtt_connect()

    # 4. отправка при изменении или раз в минуту
    if client is not None:
        data = {}
        data["temp"] = temp
        data["humidity"] = humidity
        data["ppm"] = ppm
        message = ujson.dumps(data)
        due = time.ticks_diff(now, last_publish) > FORCE_PUBLISH_MS
        if data and (message != prev_message or due):
            try:
                client.publish(MQTT_TOPIC, message)
                prev_message = message
                last_publish = now
            except Exception as e:
                print("MQTT publish error:", e)
                mqtt_close()

    draw_text(80, "WiFi:{} MQTT:{}".format("ок" if wifi_ok else "нет",
                                           "ок" if client else "нет"))

    gc.collect()
    time.sleep(2)
