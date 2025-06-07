# ESP32 Fingerprint System with MySQL Database

This project implements a fingerprint authentication system using an ESP32 microcontroller with a fingerprint sensor, communicating via serial to a Python application that handles MySQL database operations.

## System Architecture

1. **ESP32 with Fingerprint Sensor**
   - Manages the fingerprint sensor for enrollment, verification, and deletion
   - Communicates via serial port with the host computer
   - Uses custom command protocol for reliable communication

2. **Python Application**
   - Manages serial communication with ESP32
   - Handles MySQL database operations
   - Provides an interactive command-line interface

3. **MySQL Database**
   - Stores fingerprint enrollment data
   - Tracks access logs
   - Maintains user identity information

## Setup Instructions

### Hardware Requirements
- ESP32 development board
- Adafruit or compatible optical fingerprint sensor
- USB cable for ESP32 to computer connection

### Software Requirements
- Arduino IDE
- Python 3.6+
- MySQL server
- Required Python packages: `pyserial`, `mysql-connector-python`

### ESP32 Setup
1. Connect the fingerprint sensor to the ESP32:
   - Sensor RX → ESP32 TX2 (GPIO17)
   - Sensor TX → ESP32 RX2 (GPIO16)
   - Sensor VCC → ESP32 3.3V
   - Sensor GND → ESP32 GND

2. Install required Arduino libraries:
   - Adafruit Fingerprint Sensor Library
   
3. Upload the `ESP32_Fingerprint_Serial.ino` sketch to your ESP32

### Database Setup
1. Install MySQL if not already installed
2. Run the `fingerprint_db_setup.sql` script to create the database and tables:
   ```
   mysql -u root -p < fingerprint_db_setup.sql
   ```

### Python Application Setup
1. Install required Python packages:
   ```
   pip install pyserial mysql-connector-python
   ```

2. Update the database configuration in `fingerprint_db_handler.py`:
   ```python
   DB_CONFIG = {
       'host': 'localhost',
       'user': 'fingerprint_user',
       'password': 'your_secure_password',  
       'database': 'fingerprint_db'
   }
   ```

3. Update the serial port configuration:
   ```python
   SERIAL_PORT = '/dev/ttyUSB0'  # Change to match your system (Windows: 'COM3', etc.)
   ```

## Usage

1. Run the Python application:
   ```
   python fingerprint_db_handler.py
   ```

2. Use the interactive menu to:
   - Enroll new fingerprints
   - Verify fingerprints
   - Delete fingerprints
   - Get template count
   - View enrolled fingerprints
   - View access logs

## Communication Protocol

The ESP32 and Python application communicate using a simple command protocol:

- **Commands from Python to ESP32:**
  - `E[id]` - Enroll a new fingerprint with specified ID
  - `V` - Verify a fingerprint
  - `D[id]` - Delete a fingerprint with specified ID
  - `C` - Get count of stored templates

- **Responses from ESP32 to Python:**
  - `R,S,[id],[confidence],[message]` - Success response
  - `R,F,[id],[confidence],[message]` - Failure response
  - `R,Y,[id],[confidence],[message]` - Ready for next command

## Troubleshooting

### Serial Connection Issues
- Verify the correct serial port in the Python script
- Ensure the ESP32 is properly connected and powered
- Check the baud rate matches between ESP32 and Python (115200)

### Fingerprint Sensor Issues
- Make sure the sensor is properly connected to the ESP32
- Check that the sensor is powered (LED should be on)
- Try cleaning the sensor surface if readings are inconsistent

### Database Issues
- Verify MySQL server is running
- Check database credentials in the Python script
- Ensure the database and tables are properly created

## License

This project is open-source and available under the MIT License.