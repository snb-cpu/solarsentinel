
import json
import os
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

from decide import decide


BROKER = os.getenv("MQTT_BROKER", "localhost")
PORT = int(os.getenv("MQTT_PORT", "1883"))
USERNAME = os.getenv("MQTT_USERNAME")
PASSWORD = os.getenv("MQTT_PASSWORD")

COOLDOWN_SECONDS = 2 * 60 * 60
last_clean_command = {}


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Connected to MQTT broker:", BROKER)
        client.subscribe("solar/+/reading")
        print("Listening for solar panel readings...")
    else:
        print("MQTT connection failed. Code:", rc)


def on_message(client, userdata, message):
    try:
        reading = json.loads(message.payload.decode("utf-8"))

        panel_id = reading["panel_id"]
        print(f"\nReading received from {panel_id}")

        result = decide(reading)

        decision_topic = f"solar/{panel_id}/decision"

        client.publish(
            decision_topic,
            json.dumps(result),
            qos=1
        )

        print("Decision published:")
        print(json.dumps(result, indent=4))

        if result["state"] == "dust" and result["clean_now"]:
            now = time.time()
            previous_clean = last_clean_command.get(panel_id, 0)

            if now - previous_clean < COOLDOWN_SECONDS:
                print("Cleaning skipped: cooldown is active.")
                return

            command = {
                "panel_id": panel_id,
                "action": "clean",
                "water_ms": 4000,
                "air_ms": 8000
            }

            command_topic = f"solar/{panel_id}/command"

            client.publish(
                command_topic,
                json.dumps(command),
                qos=1
            )

            last_clean_command[panel_id] = now

            print("Cleaning command published:")
            print(json.dumps(command, indent=4))

    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        print("Invalid sensor reading:", error)

    except Exception as error:
        print("Processing error:", error)


def main():
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION1
    )

    if USERNAME:
        client.username_pw_set(USERNAME, PASSWORD)

    client.on_connect = on_connect
    client.on_message = on_message

    print("Connecting to MQTT broker...")

    client.connect(BROKER, PORT, 60)
    client.loop_forever()


if __name__ == "__main__":
    main()
