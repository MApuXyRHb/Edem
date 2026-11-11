import json
import sqlite3
from paho.mqtt import client as mqtt  # Импортируем один раз как mqtt
import requests
from datetime import datetime

# --- НАСТРОЙКИ ---
WOKWI_BROKER = "IP"  # Или test.mosquitto.org
WOKWI_PORT = 1883
WOKWI_TOPIC = "esp_data"  # Уточнить этот топик у сокомандника

YOUR_MQTT_HOST = "IP"
YOUR_MQTT_PORT = 1883
YOUR_MQTT_TOPIC = "esp_data1"
YOUR_MQTT_USER = "backend_service"
YOUR_MQTT_PASS = "pass"

DB_NAME = "climate_data.db"


def save_to_sqlite(temp, hum, ppm,  device_id="wokwi_device"):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO readings (temperature, humidity, ppm,  device_id) VALUES (?, ?, ?, ?)", (temp, hum, ppm, device_id))
    conn.commit()
    conn.close()


def forward_to_your_mqtt(temp, hum, ppm):
    # Исправлено: для создания клиента внутри функции тоже используем CallbackAPIVersion
    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(YOUR_MQTT_USER, YOUR_MQTT_PASS)

    try:
        client.connect(YOUR_MQTT_HOST, YOUR_MQTT_PORT, 60)
        payload = json.dumps({
            "timestamp": datetime.now().isoformat(),
            "temperature": temp,
            "humidity": hum,
            "ppm": ppm
        })
        client.publish(YOUR_MQTT_TOPIC, payload)
        client.disconnect()
        print(f"Данные пересланы на ваш MQTT: {payload}")
    except Exception as e:
        print(f"Ошибка отправки на ваш MQTT: {e}")

def on_connect(client, userdata, flags, reason_data, properties):
	print("Подключено, код:", reason_data)
	client.subscribe(WOKWI_TOPIC)

def on_message(client, userdata, msg):
    print('123')
    try:
        payload_str = msg.payload.decode('utf-8')
        data = json.loads(payload_str)

        temp = data.get("temp")
        hum = data.get("humidity")
        ppm = data.get("ppm")
        if temp is not None and hum is not None and ppm is not None:
            print(f"Получено: T={temp}, H={hum}, P={ppm}")

            # 1. Сохраняем в SQLite
            save_to_sqlite(temp, hum, ppm)

            # 2. Пересылаем на ваш защищенный сервер MQTT Explore
            forward_to_your_mqtt(temp, hum, ppm)
        else:
            print("Получен JSON, но в нем нет temperature или humidity")
    except json.JSONDecodeError:
        print("Получены невалидные данные (не JSON)")


# --- НАСТРОЙКА КЛИЕНТА (ИСПРАВЛЕНО) ---
# Создаем клиент один раз с корректным указанием API версии 2
client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
client.username_pw_set("backend_service", "pass")
client.on_connect = on_connect
client.on_message = on_message
client.connect(WOKWI_BROKER, WOKWI_PORT, 60)
client.subscribe(WOKWI_TOPIC)
print(f"Ожидаю данные от Wokwi на топике: {WOKWI_TOPIC}")
client.loop_forever()
