import sys
import time
from datetime import datetime
from loguru import logger
import serial
import mysql.connector
from PyQt5.QtWidgets import (QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, 
                            QHBoxLayout, QPushButton, QLabel, QLineEdit, QMessageBox, 
                            QTableWidget, QTableWidgetItem, QHeaderView, QFormLayout,
                            QComboBox, QSpinBox, QGroupBox, QStatusBar, QSplitter)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, pyqtSlot, QTimer
from PyQt5.QtGui import QFont, QIcon, QPixmap

# Serial and Database Configuration
SERIAL_PORT = '/dev/ttyUSB0'  # Change this to your ESP32 serial port in Windows (COM1,COM2,COM3)
BAUD_RATE = 115200
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'neverfail',
    'database': 'finger'
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

class SerialWorker(QThread):
    """Worker thread that handles serial communication"""
    responseReceived = pyqtSignal(dict)
    messageReceived = pyqtSignal(str)
    readyChanged = pyqtSignal(bool)
    
    def __init__(self, port, baud_rate):
        super().__init__()
        self.port = port
        self.baud_rate = baud_rate
        self.ser = None
        self.running = False
        self.ready = False
        
    def connect_serial(self):
        try:
            self.ser = serial.Serial(self.port, self.baud_rate, timeout=1)
            time.sleep(2)  # Wait for connection to stabilize
            return True
        except Exception as e:
            self.messageReceived.emit(f"Serial connection error: {e}")
            return False
    
    def run(self):
        if not self.connect_serial():
            return
            
        self.running = True
        while self.running:
            if self.ser and self.ser.in_waiting > 0:
                try:
                    line = self.ser.readline().decode('utf-8').strip()
                    if line.startswith(CMD_RESPONSE):
                        parts = line.split(',')
                        if len(parts) >= 5:
                            response = {
                                'response': parts[0],
                                'type': parts[1],
                                'id': int(parts[2]),
                                'confidence': int(parts[3]),
                                'message': ','.join(parts[4:])
                            }
                            self.responseReceived.emit(response)
                            
                            if response['type'] == CMD_READY and not self.ready:
                                self.ready = True
                                self.readyChanged.emit(True)
                            elif response['type'] != CMD_READY and self.ready:
                                self.ready = False
                                self.readyChanged.emit(False)
                    else:
                        self.messageReceived.emit(f"ESP32: {line}")
                except Exception as e:
                    self.messageReceived.emit(f"Error parsing response: {e}")
            
            self.msleep(100)
    
    def send_command(self, command, param=None):
        if not self.ser or not self.ser.is_open:
            self.messageReceived.emit("Serial port not open")
            return False
            
        cmd_str = command + str(param) if param is not None else command
        self.ser.write(cmd_str.encode('utf-8'))
        self.messageReceived.emit(f"Sent command: {cmd_str}")
        return True
    
    def stop(self):
        self.running = False
        if self.ser and self.ser.is_open:
            self.ser.close()


class DatabaseManager:
    """Class to handle database operations"""
    def __init__(self, config):
        self.config = config
        self.db = None
        
    def connect(self):
        try:
            # First check if the database exists, if not create it
            temp_db = mysql.connector.connect(
                host=self.config['host'],
                user=self.config['user'],
                password=self.config['password']
            )
            temp_cursor = temp_db.cursor()
            temp_cursor.execute(f"CREATE DATABASE IF NOT EXISTS {self.config['database']}")
            temp_cursor.close()
            temp_db.close()
            
            # Now connect to the specific database
            self.db = mysql.connector.connect(**self.config)
            self.setup_database()
            return True
        except mysql.connector.Error as err:
            logger.error(f"Database connection error: {err}")
            return False
    
    def setup_database(self):
        cursor = self.db.cursor()
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS fingerprints (
            id INT PRIMARY KEY,
            name TEXT,
            registration_date DATETIME,
            last_access DATETIME
        )''')
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS access_logs (
            log_id INT AUTO_INCREMENT PRIMARY KEY,
            fingerprint_id INT,
            timestamp DATETIME,
            confidence INT,
            status VARCHAR(50),
            FOREIGN KEY (fingerprint_id) REFERENCES fingerprints(id) ON DELETE SET NULL
        )''')
        self.db.commit()
        cursor.close()
    
    def enroll_fingerprint(self, finger_id, name):
        try:
            cursor = self.db.cursor()
            now = datetime.now()
            cursor.execute("""
            INSERT INTO fingerprints (id, name, registration_date, last_access) 
            VALUES (%s, %s, %s, %s)
            """, (finger_id, name, now, now))
            self.db.commit()
            cursor.close()
            return True
        except Exception as err:
            logger.exception("Database error during enrollment")
            return False
    
    def verify_fingerprint(self, finger_id, confidence):
        try:
            cursor = self.db.cursor()
            cursor.execute("SELECT name FROM fingerprints WHERE id = %s", (finger_id,))
            result = cursor.fetchone()
            name = result[0] if result else 'Unknown'
            
            now = datetime.now()
            cursor.execute("""
                UPDATE fingerprints SET last_access = %s WHERE id = %s
            """, (now, finger_id))
            cursor.execute("""
                INSERT INTO access_logs (fingerprint_id, timestamp, confidence, status) 
                VALUES (%s, %s, %s, %s)
            """, (finger_id, now, confidence, "ACCESS_GRANTED"))
            self.db.commit()
            cursor.close()
            return {'id': finger_id, 'name': name, 'confidence': confidence}
        except Exception as e:
            logger.exception("Database error during verification")
            return None
    
    def log_access_denied(self):
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
    
    def delete_fingerprint(self, finger_id):
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
            return deleted > 0
        except Exception:
            logger.exception("Database error during deletion")
            return False
    
    def get_all_fingerprints(self):
        try:
            cursor = self.db.cursor(dictionary=True)
            cursor.execute("SELECT * FROM fingerprints ORDER BY id")
            records = cursor.fetchall()
            cursor.close()
            return records
        except Exception as e:
            logger.exception("Error fetching fingerprints")
            return []
    
    def get_recent_logs(self, limit=50):
        try:
            cursor = self.db.cursor(dictionary=True)
            cursor.execute("""
            SELECT l.log_id, l.fingerprint_id, f.name, l.timestamp, l.confidence, l.status 
            FROM access_logs l 
            LEFT JOIN fingerprints f ON l.fingerprint_id = f.id 
            ORDER BY l.timestamp DESC 
            LIMIT %s
            """, (limit,))
            logs = cursor.fetchall()
            cursor.close()
            return logs
        except Exception as e:
            logger.exception("Error fetching access logs")
            return []
    
    def close(self):
        if self.db and self.db.is_connected():
            self.db.close()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fingerprint Management System")
        self.setMinimumSize(800, 600)
        
        # Initialize components
        self.serial_worker = None
        self.db_manager = DatabaseManager(DB_CONFIG)
        
        self.init_ui()
        self.connect_serial()
        
        # Set up a timer to refresh the fingerprint and log tables
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.refresh_data)
        self.refresh_timer.start(5000)  # Refresh every 5 seconds
    
    def init_ui(self):
        # Create central widget and layout
        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)
        
        # Create tabs
        self.tabs = QTabWidget()
        
        # Create tab widgets
        self.dashboard_tab = QWidget()
        self.enrollment_tab = QWidget()
        self.verification_tab = QWidget()
        self.fingerprints_tab = QWidget()
        self.logs_tab = QWidget()
        self.settings_tab = QWidget()
        
        # Add tabs to tab widget
        self.tabs.addTab(self.dashboard_tab, "Dashboard")
        self.tabs.addTab(self.enrollment_tab, "Enroll")
        self.tabs.addTab(self.verification_tab, "Verify")
        self.tabs.addTab(self.fingerprints_tab, "Fingerprints")
        self.tabs.addTab(self.logs_tab, "Access Logs")
        self.tabs.addTab(self.settings_tab, "Settings")
        
        # Set up individual tabs
        self.setup_dashboard_tab()
        self.setup_enrollment_tab()
        self.setup_verification_tab()
        self.setup_fingerprints_tab()
        self.setup_logs_tab()
        self.setup_settings_tab()
        
        # Add status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        # Add tabs to main layout
        main_layout.addWidget(self.tabs)
        
        # Set central widget
        self.setCentralWidget(central_widget)
    
    def setup_dashboard_tab(self):
        layout = QVBoxLayout()
        
        # Status group
        status_group = QGroupBox("System Status")
        status_layout = QFormLayout()
        
        self.serial_status_label = QLabel("Disconnected")
        self.database_status_label = QLabel("Disconnected")
        self.sensor_status_label = QLabel("Unknown")
        self.template_count_label = QLabel("0")
        
        status_layout.addRow("Serial Connection:", self.serial_status_label)
        status_layout.addRow("Database Connection:", self.database_status_label)
        status_layout.addRow("Fingerprint Sensor:", self.sensor_status_label)
        status_layout.addRow("Stored Templates:", self.template_count_label)
        
        status_group.setLayout(status_layout)
        
        # Quick actions
        actions_group = QGroupBox("Quick Actions")
        actions_layout = QVBoxLayout()
        
        self.verify_btn = QPushButton("Verify Fingerprint")
        self.verify_btn.clicked.connect(self.quick_verify)
        
        self.count_btn = QPushButton("Count Templates")
        self.count_btn.clicked.connect(self.get_template_count)
        
        actions_layout.addWidget(self.verify_btn)
        actions_layout.addWidget(self.count_btn)
        actions_group.setLayout(actions_layout)
        
        # Recent activity group
        recent_group = QGroupBox("Recent Activity")
        recent_layout = QVBoxLayout()
        
        self.recent_logs_table = QTableWidget(5, 5)
        self.recent_logs_table.setHorizontalHeaderLabels(["ID", "Name", "Time", "Status", "Confidence"])
        self.recent_logs_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        
        recent_layout.addWidget(self.recent_logs_table)
        recent_group.setLayout(recent_layout)
        
        # Add to main layout
        layout.addWidget(status_group)
        layout.addWidget(actions_group)
        layout.addWidget(recent_group, 1)
        
        self.dashboard_tab.setLayout(layout)
    
    def setup_enrollment_tab(self):
        layout = QVBoxLayout()
        
        form_layout = QFormLayout()
        
        self.enrollment_id_spin = QSpinBox()
        self.enrollment_id_spin.setRange(1, 127)
        
        self.enrollment_name_edit = QLineEdit()
        
        form_layout.addRow("Fingerprint ID:", self.enrollment_id_spin)
        form_layout.addRow("Person Name:", self.enrollment_name_edit)
        
        # Status and instructions
        self.enrollment_status_label = QLabel("Ready to enroll")
        self.enrollment_status_label.setAlignment(Qt.AlignCenter)
        
        instructions_label = QLabel(
            "Instructions:\n"
            "1. Enter an ID number and name\n"
            "2. Click 'Start Enrollment'\n"
            "3. Place finger on the sensor when prompted\n"
            "4. Follow the instructions to complete enrollment"
        )
        instructions_label.setAlignment(Qt.AlignCenter)
        
        # Enroll button
        self.enroll_button = QPushButton("Start Enrollment")
        self.enroll_button.clicked.connect(self.start_enrollment)
        
        # Add to layout
        layout.addLayout(form_layout)
        layout.addWidget(instructions_label)
        layout.addWidget(self.enrollment_status_label)
        layout.addWidget(self.enroll_button)
        layout.addStretch(1)
        
        self.enrollment_tab.setLayout(layout)
    
    def setup_verification_tab(self):
        layout = QVBoxLayout()
        
        # Status and instructions
        self.verification_status_label = QLabel("Ready to verify")
        self.verification_status_label.setAlignment(Qt.AlignCenter)
        self.verification_status_label.setFont(QFont("Arial", 14))
        
        instructions_label = QLabel(
            "Instructions:\n"
            "1. Click 'Start Verification'\n"
            "2. Place finger on the sensor\n"
            "3. Wait for verification result"
        )
        instructions_label.setAlignment(Qt.AlignCenter)
        
        # Result display
        result_group = QGroupBox("Verification Result")
        result_layout = QFormLayout()
        
        self.verify_id_label = QLabel("--")
        self.verify_name_label = QLabel("--")
        self.verify_confidence_label = QLabel("--")
        self.verify_time_label = QLabel("--")
        
        result_layout.addRow("ID:", self.verify_id_label)
        result_layout.addRow("Name:", self.verify_name_label)
        result_layout.addRow("Confidence:", self.verify_confidence_label)
        result_layout.addRow("Time:", self.verify_time_label)
        
        result_group.setLayout(result_layout)
        
        # Verify button
        self.verify_button = QPushButton("Start Verification")
        self.verify_button.clicked.connect(self.start_verification)
        self.verify_button.setMinimumHeight(50)
        
        # Add to layout
        layout.addWidget(instructions_label)
        layout.addWidget(self.verification_status_label)
        layout.addWidget(result_group)
        layout.addWidget(self.verify_button)
        layout.addStretch(1)
        
        self.verification_tab.setLayout(layout)
    
    def setup_fingerprints_tab(self):
        layout = QVBoxLayout()
        
        # Fingerprints table
        self.fingerprints_table = QTableWidget(0, 4)
        self.fingerprints_table.setHorizontalHeaderLabels(["ID", "Name", "Registration Date", "Last Access"])
        self.fingerprints_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.fingerprints_table.setSelectionBehavior(QTableWidget.SelectRows)
        
        # Buttons
        buttons_layout = QHBoxLayout()
        
        self.refresh_fingerprints_btn = QPushButton("Refresh")
        self.refresh_fingerprints_btn.clicked.connect(self.refresh_fingerprints)
        
        self.delete_fingerprint_btn = QPushButton("Delete Selected")
        self.delete_fingerprint_btn.clicked.connect(self.delete_selected_fingerprint)
        
        buttons_layout.addWidget(self.refresh_fingerprints_btn)
        buttons_layout.addWidget(self.delete_fingerprint_btn)
        
        # Add to layout
        layout.addWidget(self.fingerprints_table)
        layout.addLayout(buttons_layout)
        
        self.fingerprints_tab.setLayout(layout)
    
    def setup_logs_tab(self):
        layout = QVBoxLayout()
        
        # Logs table
        self.logs_table = QTableWidget(0, 6)
        self.logs_table.setHorizontalHeaderLabels(["Log ID", "Fingerprint ID", "Name", "Timestamp", "Confidence", "Status"])
        self.logs_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        
        # Refresh button
        self.refresh_logs_btn = QPushButton("Refresh Logs")
        self.refresh_logs_btn.clicked.connect(self.refresh_logs)
        
        # Add to layout
        layout.addWidget(self.logs_table)
        layout.addWidget(self.refresh_logs_btn)
        
        self.logs_tab.setLayout(layout)
    
    def setup_settings_tab(self):
        layout = QVBoxLayout()
        
        # Serial settings
        serial_group = QGroupBox("Serial Connection")
        serial_layout = QFormLayout()
        
        self.serial_port_combo = QComboBox()
        # Add common port names
        for i in range(10):
            if sys.platform == "win32":
                self.serial_port_combo.addItem(f"COM{i+1}")
            else:
                self.serial_port_combo.addItem(f"/dev/ttyUSB{i}")
                self.serial_port_combo.addItem(f"/dev/ttyACM{i}")
        
        self.serial_port_combo.setEditable(True)
        self.serial_port_combo.setCurrentText(SERIAL_PORT)
        
        self.baud_rate_combo = QComboBox()
        for rate in [9600, 19200, 38400, 57600, 115200]:
            self.baud_rate_combo.addItem(str(rate))
        
        self.baud_rate_combo.setCurrentText(str(BAUD_RATE))
        
        self.serial_connect_btn = QPushButton("Connect")
        self.serial_connect_btn.clicked.connect(self.connect_serial)
        
        serial_layout.addRow("Port:", self.serial_port_combo)
        serial_layout.addRow("Baud Rate:", self.baud_rate_combo)
        serial_layout.addRow("", self.serial_connect_btn)
        
        serial_group.setLayout(serial_layout)
        
        # Database settings
        db_group = QGroupBox("Database Connection")
        db_layout = QFormLayout()
        
        self.db_host_edit = QLineEdit(DB_CONFIG['host'])
        self.db_name_edit = QLineEdit(DB_CONFIG['database'])
        self.db_user_edit = QLineEdit(DB_CONFIG['user'])
        self.db_password_edit = QLineEdit(DB_CONFIG['password'])
        self.db_password_edit.setEchoMode(QLineEdit.Password)
        
        self.db_connect_btn = QPushButton("Connect")
        self.db_connect_btn.clicked.connect(self.connect_database)
        
        db_layout.addRow("Host:", self.db_host_edit)
        db_layout.addRow("Database:", self.db_name_edit)
        db_layout.addRow("Username:", self.db_user_edit)
        db_layout.addRow("Password:", self.db_password_edit)
        db_layout.addRow("", self.db_connect_btn)
        
        db_group.setLayout(db_layout)
        
        # Add to layout
        layout.addWidget(serial_group)
        layout.addWidget(db_group)
        layout.addStretch(1)
        
        self.settings_tab.setLayout(layout)
    
    def connect_serial(self):
        # Stop any existing serial worker
        if self.serial_worker:
            self.serial_worker.stop()
            self.serial_worker.wait()
        
        # Get port and baud rate from settings if UI is set up
        if hasattr(self, 'serial_port_combo'):
            port = self.serial_port_combo.currentText()
            baud_rate = int(self.baud_rate_combo.currentText())
        else:
            port = SERIAL_PORT
            baud_rate = BAUD_RATE
        
        # Create and start the serial worker
        self.serial_worker = SerialWorker(port, baud_rate)
        self.serial_worker.messageReceived.connect(self.handle_message)
        self.serial_worker.responseReceived.connect(self.handle_response)
        self.serial_worker.readyChanged.connect(self.handle_ready_changed)
        self.serial_worker.start()
        
        self.status_bar.showMessage(f"Connecting to serial port {port}...")
        self.serial_status_label.setText(f"Connecting to {port}...")
    
    def connect_database(self):
        # Get settings from UI
        config = {
            'host': self.db_host_edit.text(),
            'user': self.db_user_edit.text(),
            'password': self.db_password_edit.text(),
            'database': self.db_name_edit.text()
        }
        
        # Close existing connection
        if self.db_manager:
            self.db_manager.close()
        
        # Create new database manager
        self.db_manager = DatabaseManager(config)
        
        # Try to connect
        if self.db_manager.connect():
            self.database_status_label.setText("Connected")
            self.status_bar.showMessage("Connected to database", 3000)
            self.refresh_data()
        else:
            self.database_status_label.setText("Disconnected")
            QMessageBox.critical(self, "Database Error", "Failed to connect to database")
    
    def refresh_data(self):
        """Refresh data tables"""
        self.refresh_fingerprints()
        self.refresh_logs()
        self.update_dashboard()
    
    def refresh_fingerprints(self):
        """Refresh the fingerprints table"""
        fingerprints = self.db_manager.get_all_fingerprints()
        self.fingerprints_table.setRowCount(len(fingerprints))
        
        for i, fp in enumerate(fingerprints):
            self.fingerprints_table.setItem(i, 0, QTableWidgetItem(str(fp['id'])))
            self.fingerprints_table.setItem(i, 1, QTableWidgetItem(fp['name']))
            self.fingerprints_table.setItem(i, 2, QTableWidgetItem(str(fp['registration_date'])))
            self.fingerprints_table.setItem(i, 3, QTableWidgetItem(str(fp['last_access'])))
    
    def refresh_logs(self):
        """Refresh the logs table"""
        logs = self.db_manager.get_recent_logs()
        self.logs_table.setRowCount(len(logs))
        
        # Update main logs tab
        for i, log in enumerate(logs):
            self.logs_table.setItem(i, 0, QTableWidgetItem(str(log['log_id'])))
            self.logs_table.setItem(i, 1, QTableWidgetItem(str(log['fingerprint_id'])))
            self.logs_table.setItem(i, 2, QTableWidgetItem(log['name'] if log['name'] else 'Unknown'))
            self.logs_table.setItem(i, 3, QTableWidgetItem(str(log['timestamp'])))
            self.logs_table.setItem(i, 4, QTableWidgetItem(str(log['confidence'])))
            self.logs_table.setItem(i, 5, QTableWidgetItem(log['status']))
        
        # Update recent logs on dashboard (show only 5 most recent)
        recent_logs = logs[:5]
        self.recent_logs_table.setRowCount(len(recent_logs))
        
        for i, log in enumerate(recent_logs):
            self.recent_logs_table.setItem(i, 0, QTableWidgetItem(str(log['fingerprint_id'])))
            self.recent_logs_table.setItem(i, 1, QTableWidgetItem(log['name'] if log['name'] else 'Unknown'))
            self.recent_logs_table.setItem(i, 2, QTableWidgetItem(str(log['timestamp'])))
            self.recent_logs_table.setItem(i, 3, QTableWidgetItem(log['status']))
            self.recent_logs_table.setItem(i, 4, QTableWidgetItem(str(log['confidence'])))
    
    def update_dashboard(self):
        """Update dashboard information"""
        if self.serial_worker and self.serial_worker.isRunning():
            self.serial_status_label.setText("Connected")
        else:
            self.serial_status_label.setText("Disconnected")
            
        if not self.db_manager or not hasattr(self.db_manager, 'db') or not self.db_manager.db or not self.db_manager.db.is_connected():
            self.database_status_label.setText("Disconnected")
        else:
            self.database_status_label.setText("Connected")
            
        # Template count will be updated when the user presses the Count button
    
    def handle_message(self, message):
        """Handle messages from the serial worker"""
        self.status_bar.showMessage(message, 3000)
        logger.info(message)
    
    def handle_response(self, response):
        """Handle responses from the fingerprint sensor"""
        if response['type'] == CMD_SUCCESS:
            if 'enrollment' in response['message'].lower():
                self.handle_enrollment_response(response)
            elif 'template' in response['message'].lower():
                self.template_count_label.setText(str(response['id']))
            elif 'verified' in response['message'].lower():
                self.handle_verification_response(response)
            elif 'deleted' in response['message'].lower():
                self.handle_deletion_response(response)
        elif response['type'] == CMD_FAILURE:
            self.status_bar.showMessage(f"Error: {response['message']}", 5000)
            
            if 'verify' in response['message'].lower():
                self.verification_status_label.setText("Verification Failed")
                self.verification_status_label.setStyleSheet("color: red")
                self.db_manager.log_access_denied()
                self.refresh_logs()
    
    def handle_ready_changed(self, ready):
        """Handle sensor ready state changes"""
        if ready:
            self.sensor_status_label.setText("Ready")
        else:
            self.sensor_status_label.setText("Busy")
    
    def start_enrollment(self):
        """Start the enrollment process"""
        if not self.serial_worker or not self.serial_worker.isRunning():
            QMessageBox.warning(self, "Not Connected", "Serial connection not established")
            return
            
        finger_id = self.enrollment_id_spin.value()
        name = self.enrollment_name_edit.text()
        
        if not name:
            QMessageBox.warning(self, "Invalid Input", "Please enter a name")
            return
            
        self.enrollment_status_label.setText("Place finger on sensor...")
        self.serial_worker.send_command(CMD_ENROLL, finger_id)
    
    def handle_enrollment_response(self, response):
        """Handle enrollment response"""
        if response['type'] == CMD_SUCCESS:
            finger_id = response['id']
            name = self.enrollment_name_edit.text()
            
            if self.db_manager.enroll_fingerprint(finger_id, name):
                self.enrollment_status_label.setText(f"Enrollment successful! ID: {finger_id}")
                self.refresh_fingerprints()
                QMessageBox.information(self, "Success", f"Enrollment successful! ID: {finger_id}")
            else:
                self.enrollment_status_label.setText("Database error during enrollment")
        else:
            self.enrollment_status_label.setText("Enrollment failed")
    
    def start_verification(self):
        """Start the verification process"""
        if not self.serial_worker or not self.serial_worker.isRunning():
            QMessageBox.warning(self, "Not Connected", "Serial connection not established")
            return
            
        self.verification_status_label.setText("Place finger on sensor...")
        self.verification_status_label.setStyleSheet("")
        self.serial_worker.send_command(CMD_VERIFY)
    
    def quick_verify(self):
        """Quick verification from dashboard"""
        self.tabs.setCurrentIndex(2)  # Switch to verification tab
        self.start_verification()
    
    def handle_verification_response(self, response):
        """Handle verification response"""
        if response['type'] == CMD_SUCCESS:
            finger_id = response['id']
            confidence = response['confidence']
            
            result = self.db_manager.verify_fingerprint(finger_id, confidence)
            if result:
                self.verification_status_label.setText(f"Access Granted: {result['name']}")
                self.verification_status_label.setStyleSheet("color: green; font-weight: bold;")
                
                # Update the result display
                self.verify_id_label.setText(str(result['id']))
                self.verify_name_label.setText(result['name'])
                self.verify_confidence_label.setText(str(result['confidence']))
                self.verify_time_label.setText(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                
                # Refresh logs to show the new access
                self.refresh_logs()
            else:
                self.verification_status_label.setText("Database error during verification")
                self.verification_status_label.setStyleSheet("color: red")
        else:
            self.verification_status_label.setText("Verification failed")
            self.verification_status_label.setStyleSheet("color: red")
    
    def delete_selected_fingerprint(self):
        """Delete the selected fingerprint"""
        selected_rows = self.fingerprints_table.selectedIndexes()
        if not selected_rows:
            QMessageBox.warning(self, "No Selection", "Please select a fingerprint to delete")
            return
            
        # Get the fingerprint ID from the first column of the selected row
        row = selected_rows[0].row()
        finger_id = int(self.fingerprints_table.item(row, 0).text())
        name = self.fingerprints_table.item(row, 1).text()
        
        # Confirm deletion
        reply = QMessageBox.question(self, "Confirm Deletion", 
                                     f"Are you sure you want to delete fingerprint ID {finger_id} ({name})?",
                                     QMessageBox.Yes | QMessageBox.No)
                                     
        if reply == QMessageBox.No:
            return
            
        # First delete from sensor
        if self.serial_worker and self.serial_worker.isRunning():
            self.serial_worker.send_command(CMD_DELETE, finger_id)
        else:
            QMessageBox.warning(self, "Not Connected", "Serial connection not established")
            return
    
    def handle_deletion_response(self, response):
        """Handle deletion response from the sensor"""
        if response['type'] == CMD_SUCCESS:
            finger_id = response['id']
            
            # Delete from database
            if self.db_manager.delete_fingerprint(finger_id):
                self.status_bar.showMessage(f"Fingerprint ID {finger_id} deleted successfully", 3000)
                self.refresh_fingerprints()
                self.refresh_logs()
            else:
                self.status_bar.showMessage("Database error during deletion", 3000)
        else:
            self.status_bar.showMessage("Failed to delete fingerprint from sensor", 3000)
    
    def get_template_count(self):
        """Get the number of templates stored in the sensor"""
        if not self.serial_worker or not self.serial_worker.isRunning():
            QMessageBox.warning(self, "Not Connected", "Serial connection not established")
            return
            
        self.serial_worker.send_command(CMD_COUNT)
        self.status_bar.showMessage("Querying template count...", 2000)
    
    def closeEvent(self, event):
        """Clean up resources when closing the application"""
        if self.serial_worker and self.serial_worker.isRunning():
            self.serial_worker.stop()
            self.serial_worker.wait()
        
        if self.db_manager:
            self.db_manager.close()
            
        event.accept()


def main():
    logger.add("fingerprint_system.log", rotation="10 MB", level="INFO")
    
    # Create and show the application
    app = QApplication(sys.argv)
    app.setStyle('Fusion')  
    
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
