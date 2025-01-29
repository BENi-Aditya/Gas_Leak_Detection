from flask import Flask, render_template, request, jsonify
import RPi.GPIO as GPIO
import time
import threading
from RPLCD import i2c
import requests
import os

app = Flask(__name__)

# Load Telegram Bot configuration from environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")  # Set this in your system environment
CHAT_ID = os.getenv("CHAT_ID")  # Set this in your system environment

# GPIO setup
MQ2_1_PIN = 14
MQ2_2_PIN = 15
MQ7_PIN = 18
BUZZER_PIN = 4

GPIO.setmode(GPIO.BCM)
GPIO.setup(MQ2_1_PIN, GPIO.IN)
GPIO.setup(MQ2_2_PIN, GPIO.IN)
GPIO.setup(MQ7_PIN, GPIO.IN)
GPIO.setup(BUZZER_PIN, GPIO.OUT)

# LCD Configuration
lcdmode = 'i2c'
cols = 16
rows = 2
charmap = 'A00'
i2c_expander = 'PCF8574'
address = 0x27  # LCD I2C address

# Initialize the LCD
lcd = i2c.CharLCD(i2c_expander, address, port=1, charmap=charmap,
                  cols=cols, rows=rows)

# Global variables
sensor_readings = {
    'mq2_1': 100,  # Initialize to safe values
    'mq2_2': 100,
    'mq7': 100
}

thresholds = {
    'mq2': 50,
    'mq7': 50
}

global_safety_status = True
alert_sent = False

def send_telegram_alert(message):
    """Send a Telegram alert using the bot."""
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram credentials are not set.")
        return
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {'chat_id': CHAT_ID, 'text': message}
        response = requests.post(url, data=payload)
        print(f"Telegram alert sent: {response.status_code}")
    except Exception as e:
        print(f"Failed to send Telegram alert: {e}")

def update_lcd(line1, line2):
    """Update the LCD display with two lines of text."""
    try:
        lcd.clear()
        lcd.cursor_pos = (0, 0)
        lcd.write_string(line1[:16].ljust(16))
        lcd.cursor_pos = (1, 0)
        lcd.write_string(line2[:16].ljust(16))
    except Exception as e:
        print(f"LCD Error: {e}")

def read_sensor(pin):
    """Read sensor value and convert to 0 or 100."""
    try:
        value = GPIO.input(pin)
        return 100 if value else 0  # Return 100 for HIGH (safe), 0 for LOW (unsafe)
    except Exception as e:
        print(f"Sensor read error: {e}")
        return 100  # Default to safe value on error

def check_safety_status():
    """Check if any sensor reading is 0 (unsafe)."""
    return not any(reading == 0 for reading in sensor_readings.values())

def update_readings():
    """Update sensor readings and handle alerts."""
    global global_safety_status, alert_sent
    
    while True:
        try:
            sensor_readings['mq2_1'] = read_sensor(MQ2_1_PIN)
            sensor_readings['mq2_2'] = read_sensor(MQ2_2_PIN)
            sensor_readings['mq7'] = read_sensor(MQ7_PIN)
            
            global_safety_status = check_safety_status()
            
            status_msg = "SAFE" if global_safety_status else "NOT SAFE"
            readings_msg = f"M1:{sensor_readings['mq2_1']} M2:{sensor_readings['mq2_2']}"
            
            update_lcd(f"Gas Status: {status_msg}", readings_msg)
            
            if not global_safety_status:
                GPIO.output(BUZZER_PIN, GPIO.HIGH)
                if not alert_sent:
                    alert_message = "ALERT: Gas leak detected!\n"
                    alert_message += f"MQ2-1: {sensor_readings['mq2_1']}\n"
                    alert_message += f"MQ2-2: {sensor_readings['mq2_2']}\n"
                    alert_message += f"MQ7: {sensor_readings['mq7']}"
                    send_telegram_alert(alert_message)
                    alert_sent = True
            else:
                GPIO.output(BUZZER_PIN, GPIO.LOW)
                alert_sent = False
            
            time.sleep(1)
            
        except Exception as e:
            print(f"Update error: {e}")
            time.sleep(1)

sensor_thread = threading.Thread(target=update_readings, daemon=True)
sensor_thread.start()

@app.route('/')
def index():
    return render_template('index.html', 
                           readings=sensor_readings, 
                           thresholds=thresholds, 
                           global_status=global_safety_status)

@app.route('/calibrate', methods=['POST'])
def calibrate():
    new_thresholds = request.json
    thresholds.update(new_thresholds)
    return jsonify({"status": "success"})

@app.route('/get_readings')
def get_readings():
    return jsonify({
        **sensor_readings,
        "global_status": global_safety_status
    })

if __name__ == '__main__':
    try:
        update_lcd("Gas Detection", "System Starting")
        time.sleep(2)
        app.run(debug=False, host='0.0.0.0')
    finally:
        GPIO.output(BUZZER_PIN, GPIO.LOW)
        GPIO.cleanup()
        lcd.close(clear=True)
