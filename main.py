import serial
import time
import psycopg2
import psycopg2.extras
from datetime import datetime
from loguru import logger

# Serial and Database Configuration
SERIAL_PORT = '/dev/ttyUSB0'  # Change this to your ESP32 serial port in windows
BAUD_RATE = 115200
DB_CONFIG = {
    'host': 'localhost',
    'user': 'postgres',
    'password': 'neverfail',
    'dbname': 'finger'
}

# Command definitions
CMD_ENROLL = 'E'
CMD_VERIFY = 'V'
CMD_DELETE = 'D'
CMD_COUNT = 'C'
CMD_RESPONSE = 'R'
CMD_SUCCESS = 'S'
CMD_FAILURE = 'F'
CMD_READY = 'Y'

class FingerprintSystem:
    def __init__(self, port=SERIAL_PORT, baud_rate=BAUD_RATE):
        self.ser = None
        self.db = None
        self.port = port
        self.baud_rate = baud_rate
        self.connected = False
        self.ready = False

    def connect(self):
        try:
            self.ser = serial.Serial(self.port, self.baud_rate, timeout=1)
            time.sleep(2)
            self.connected = True
            logger.info(f"Connected to {self.port} at {self.baud_rate} baud")
        except Exception as e:
            logger.error(f"Serial connection error: {e}")
            return False

        try:
            self.db = psycopg2.connect(**DB_CONFIG)
            logger.info(f"Connected to PostgreSQL database: {DB_CONFIG['dbname']}")
            self.setup_database()
            return True
        except psycopg2.Error as err:
            logger.error(f"Database connection error: {err}")
            return False

    def setup_database(self):
        cursor = self.db.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS fingerprints (
            id INTEGER PRIMARY KEY,
            name TEXT,
            registration_date TIMESTAMP,
            last_access TIMESTAMP
        )''')
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS access_logs (
            log_id SERIAL PRIMARY KEY,
            fingerprint_id INTEGER REFERENCES fingerprints(id),
            timestamp TIMESTAMP,
            confidence INTEGER,
            status TEXT
        )''')
        self.db.commit()
        cursor.close()

    def wait_for_ready(self):
        while not self.ready:
            response = self.read_response()
            if response and response['type'] == CMD_READY:
                self.ready = True
                return True
        return False

    def read_response(self, timeout=10):
        start_time = time.time()
        while (time.time() - start_time) < timeout:
            if self.ser.in_waiting > 0:
                try:
                    line = self.ser.readline().decode('utf-8').strip()
                    logger.debug(f"Raw response: {line}")
                    if line.startswith(CMD_RESPONSE):
                        parts = line.split(',')
                        if len(parts) >= 5:
                            return {
                                'response': parts[0],
                                'type': parts[1],
                                'id': int(parts[2]),
                                'confidence': int(parts[3]),
                                'message': ','.join(parts[4:])
                            }
                    else:
                        logger.info(f"ESP32: {line}")
                except Exception as e:
                    logger.exception("Error parsing response")
            time.sleep(0.1)
        return None

    def send_command(self, command, param=None):
        cmd_str = command + str(param) if param is not None else command
        self.ser.write(cmd_str.encode('utf-8'))
        logger.info(f"Sent command: {cmd_str}")
        self.ready = False
        response = self.read_response()
        self.wait_for_ready()
        return response

    def enroll_fingerprint(self, finger_id, name):
        if not self.connected:
            logger.warning("Not connected to ESP32")
            return False
        logger.info(f"Enrolling fingerprint ID: {finger_id}, Name: {name}")
        response = self.send_command(CMD_ENROLL, finger_id)
        if response and response['type'] == CMD_SUCCESS:
            try:
                cursor = self.db.cursor()
                now = datetime.now()
                cursor.execute("""
                INSERT INTO fingerprints (id, name, registration_date, last_access) 
                VALUES (%s, %s, %s, %s)
                """, (finger_id, name, now, now))
                self.db.commit()
                cursor.close()
                logger.success(f"Fingerprint {name} enrolled with ID {finger_id}")
                return True
            except Exception as err:
                logger.exception("Database error during enrollment")
        else:
            logger.error("Enrollment failed")
        return False

    def verify_fingerprint(self):
        if not self.connected:
            logger.warning("Not connected to ESP32")
            return False
        logger.info("Verifying fingerprint...")
        response = self.send_command(CMD_VERIFY)
        if response and response['type'] == CMD_SUCCESS:
            try:
                cursor = self.db.cursor()
                cursor.execute("SELECT name FROM fingerprints WHERE id = %s", (response['id'],))
                result = cursor.fetchone()
                name = result[0] if result else 'Unknown'
                logger.success(f"Access granted: {name} (ID: {response['id']}, Confidence: {response['confidence']})")
                now = datetime.now()
                cursor.execute("""
                    UPDATE fingerprints SET last_access = %s WHERE id = %s
                """, (now, response['id']))
                cursor.execute("""
                    INSERT INTO access_logs (fingerprint_id, timestamp, confidence, status) 
                    VALUES (%s, %s, %s, %s)
                """, (response['id'], now, response['confidence'], "ACCESS_GRANTED"))
                self.db.commit()
                cursor.close()
                return {'id': response['id'], 'name': name, 'confidence': response['confidence']}
            except Exception:
                logger.exception("Database error during verification")
        else:
            logger.warning("Verification failed")
            try:
                cursor = self.db.cursor()
                now = datetime.now()
                cursor.execute("""
                    INSERT INTO access_logs (fingerprint_id, timestamp, confidence, status) 
                    VALUES (%s, %s, %s, %s)
                """, (0, now, 0, "ACCESS_DENIED"))
                self.db.commit()
                cursor.close()
            except Exception:
                logger.exception("Database error logging failed access")
        return False

    def delete_fingerprint(self, finger_id):
        if not self.connected:
            logger.warning("Not connected to ESP32")
            return False
        logger.info(f"Deleting fingerprint ID: {finger_id}")
        response = self.send_command(CMD_DELETE, finger_id)
        if response and response['type'] == CMD_SUCCESS:
            try:
                cursor = self.db.cursor()
                now = datetime.now()
                cursor.execute("""
                    INSERT INTO access_logs (fingerprint_id, timestamp, confidence, status) 
                    VALUES (%s, %s, %s, %s)
                """, (finger_id, now, 0, "DELETED"))
                cursor.execute("DELETE FROM fingerprints WHERE id = %s", (finger_id,))
                self.db.commit()
                deleted = cursor.rowcount
                cursor.close()
                if deleted > 0:
                    logger.success(f"Fingerprint ID {finger_id} deleted")
                else:
                    logger.warning(f"Fingerprint ID {finger_id} not found in database")
                return True
            except Exception:
                logger.exception("Database error during deletion")
        else:
            logger.error("Failed to delete fingerprint from sensor")
        return False

    def get_template_count(self):
        if not self.connected:
            logger.warning("Not connected to ESP32")
            return -1
        response = self.send_command(CMD_COUNT)
        return response['id'] if response else -1

    def disconnect(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
            logger.info("Serial connection closed")
        if self.db and self.db.closed == 0:
            self.db.close()
            logger.info("Database connection closed")
        self.connected = False
        self.ready = False

def interactive_menu(fps):
    """Display an interactive menu for the fingerprint system."""
    while True:
        print("\n===== FINGERPRINT SYSTEM MENU =====")
        print("1. Enroll New Fingerprint")
        print("2. Verify Fingerprint")
        print("3. Delete Fingerprint")
        print("4. Get Template Count")
        print("5. List Enrolled Fingerprints")
        print("6. View Access Logs")
        print("0. Exit")
        print("===================================")
        
        choice = input("Enter your choice: ")
        
        if choice == '1':
            finger_id = int(input("Enter fingerprint ID (1-127): "))
            name = input("Enter person's name: ")
            fps.enroll_fingerprint(finger_id, name)
            
        elif choice == '2':
            result = fps.verify_fingerprint()
            if result:
                print(f"Verified fingerprint: ID {result['id']}, Name: {result['name']}, Confidence: {result['confidence']}")
                
        elif choice == '3':
            finger_id = int(input("Enter fingerprint ID to delete: "))
            fps.delete_fingerprint(finger_id)
            
        elif choice == '4':
            count = fps.get_template_count()
            print(f"Templates stored in sensor: {count}")
            
        elif choice == '5':
            if fps.db and fps.db.is_connected():
                cursor = fps.db.cursor(dictionary=True)
                cursor.execute("SELECT * FROM fingerprints ORDER BY id")
                records = cursor.fetchall()
                cursor.close()
                
                print("\n--- Enrolled Fingerprints ---")
                print("ID | Name | Registration Date | Last Access")
                print("---------------------------------------")
                for record in records:
                    print(f"{record['id']} | {record['name']} | {record['registration_date']} | {record['last_access']}")
            else:
                print("Database not connected")
                
        elif choice == '6':
            if fps.db and fps.db.is_connected():
                cursor = fps.db.cursor(dictionary=True)
                cursor.execute("""
                SELECT l.log_id, l.fingerprint_id, f.name, l.timestamp, l.confidence, l.status 
                FROM access_logs l 
                LEFT JOIN fingerprints f ON l.fingerprint_id = f.id 
                ORDER BY l.timestamp DESC 
                LIMIT 20
                """)
                logs = cursor.fetchall()
                cursor.close()
                
                print("\n--- Recent Access Logs (last 20) ---")
                print("ID | Fingerprint ID | Name | Timestamp | Confidence | Status")
                print("-------------------------------------------------------")
                for log in logs:
                    name = log['name'] if log['name'] else 'Unknown'
                    print(f"{log['log_id']} | {log['fingerprint_id']} | {name} | {log['timestamp']} | {log['confidence']} | {log['status']}")
            else:
                print("Database not connected")
                
        elif choice == '0':
            fps.disconnect()
            print("Exiting program")
            break
            
        else:
            print("Invalid choice, please try again")


if __name__ == "__main__":
    # Create and connect the fingerprint system
    fps = FingerprintSystem()
    if fps.connect():
        interactive_menu(fps)
    else:
        print("Failed to connect to ESP32 or database. Please check your connections and try again.")