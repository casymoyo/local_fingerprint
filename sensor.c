#include <Adafruit_Fingerprint.h>

HardwareSerial MySerial(2);  // UART2 on ESP32
Adafruit_Fingerprint finger = Adafruit_Fingerprint(&MySerial);

// Command protocol constants
#define CMD_ENROLL 'E'        // Enroll a new fingerprint
#define CMD_VERIFY 'V'        // Verify a fingerprint
#define CMD_DELETE 'D'        // Delete a fingerprint
#define CMD_COUNT 'C'         // Get count of stored fingerprints
#define CMD_RESPONSE 'R'      // Response to PC
#define CMD_SUCCESS 'S'       // Success message
#define CMD_FAILURE 'F'       // Failure message
#define CMD_READY 'Y'         // Ready for next command

// Function declarations
void displayMenu();
void enrollFinger(int id);
int getFingerprintID();
void deleteFingerprint(int id);
void sendSerialResponse(char responseType, int id, int confidence, String message);

void setup() {
  Serial.begin(115200);
  while (!Serial) delay(10);  // Wait for serial port to connect
  
  MySerial.begin(57600, SERIAL_8N1, 16, 17);  // typical baud rate for fingerprint modules
  delay(100);
  
  finger.begin(57600);
  if (finger.verifyPassword()) {
    Serial.println("Fingerprint sensor detected!");
  } else {
    Serial.println("Fingerprint sensor not found :(");
    while (1) { delay(1); }
  }
  
  sendSerialResponse(CMD_READY, 0, 0, "Fingerprint system ready");
  displayMenu();
}

void loop() {
  if (Serial.available()) {
    char command = Serial.read();
    int id = -1;
    int result = -1;  // Declare result variable outside switch to avoid errors
    
    // Wait for ID parameter if needed
    if (command == CMD_ENROLL || command == CMD_DELETE) {
      // Wait for ID to be sent
      delay(100);
      if (Serial.available()) {
        id = Serial.parseInt();
      }
    }
    
    switch (command) {
      case CMD_ENROLL:
        if (id >= 1 && id <= 127) {
          enrollFinger(id);
        } else {
          sendSerialResponse(CMD_FAILURE, 0, 0, "Invalid ID. Must be between 1-127");
        }
        break;
        
      case CMD_VERIFY:
        Serial.println("Place finger to verify...");
        result = getFingerprintID();
        if (result >= 0) {
          sendSerialResponse(CMD_SUCCESS, result, finger.confidence, "Fingerprint matched");
        } else {
          sendSerialResponse(CMD_FAILURE, 0, 0, "No match found");
        }
        break;
        
      case CMD_DELETE:
        if (id >= 1 && id <= 127) {
          deleteFingerprint(id);
        } else {
          sendSerialResponse(CMD_FAILURE, 0, 0, "Invalid ID. Must be between 1-127");
        }
        break;
        
      case CMD_COUNT:
        finger.getTemplateCount();
        sendSerialResponse(CMD_RESPONSE, finger.templateCount, 0, "Template count");
        break;
        
      default:
        sendSerialResponse(CMD_FAILURE, 0, 0, "Unknown command");
        break;
    }
    
    // Clear any remaining characters in the buffer
    while(Serial.available()) Serial.read();
    
    sendSerialResponse(CMD_READY, 0, 0, "Ready for next command");
  }
}

void displayMenu() {
  Serial.println("\n========== FINGERPRINT SYSTEM MENU ==========");
  Serial.println("Commands:");
  Serial.println("E[id] - Enroll New Fingerprint (id: 1-127)");
  Serial.println("V - Verify Fingerprint");
  Serial.println("D[id] - Delete Fingerprint (id: 1-127)");
  Serial.println("C - Get Template Count");
  Serial.println("===========================================");
}

void enrollFinger(int id) {
  Serial.println("Enrolling ID #" + String(id));
  Serial.println("Place your finger on the sensor...");
  
  int p = -1;
  while (p != FINGERPRINT_OK) {
    p = finger.getImage();
    switch (p) {
      case FINGERPRINT_OK:
        Serial.println("Image taken");
        break;
      case FINGERPRINT_NOFINGER:
        Serial.print(".");
        delay(500);
        break;
      default:
        sendSerialResponse(CMD_FAILURE, id, 0, "Error taking image");
        return;
    }
  }
  
  p = finger.image2Tz(1);
  if (p != FINGERPRINT_OK) {
    sendSerialResponse(CMD_FAILURE, id, 0, "Error converting image");
    return;
  }
  
  Serial.println("Remove finger");
  delay(2000);
  
  p = 0;
  while (p != FINGERPRINT_NOFINGER) {
    p = finger.getImage();
    delay(500);
  }
  
  Serial.println("Place same finger again...");
  
  p = -1;
  while (p != FINGERPRINT_OK) {
    p = finger.getImage();
    switch (p) {
      case FINGERPRINT_OK:
        Serial.println("Image taken");
        break;
      case FINGERPRINT_NOFINGER:
        Serial.print(".");
        delay(500);
        break;
      default:
        sendSerialResponse(CMD_FAILURE, id, 0, "Error taking image");
        return;
    }
  }
  
  p = finger.image2Tz(2);
  if (p != FINGERPRINT_OK) {
    sendSerialResponse(CMD_FAILURE, id, 0, "Error converting image");
    return;
  }
  
  Serial.println("Creating model...");
  p = finger.createModel();
  if (p != FINGERPRINT_OK) {
    sendSerialResponse(CMD_FAILURE, id, 0, "Error creating model");
    return;
  }
  
  Serial.println("Storing model...");
  p = finger.storeModel(id);
  if (p != FINGERPRINT_OK) {
    sendSerialResponse(CMD_FAILURE, id, 0, "Error storing model");
    return;
  }
  
  sendSerialResponse(CMD_SUCCESS, id, 0, "Fingerprint enrolled successfully");
}

int getFingerprintID() {
  int p = finger.getImage();
  if (p != FINGERPRINT_OK) {
    if (p == FINGERPRINT_NOFINGER) {
      Serial.print(".");
    } else {
      Serial.println("Error getting image");
    }
    return -1;
  }
  
  p = finger.image2Tz();
  if (p != FINGERPRINT_OK) {
    Serial.println("Error converting image");
    return -1;
  }
  
  p = finger.fingerSearch();
  if (p != FINGERPRINT_OK) {
    Serial.println("No match found");
    return -1;
  }
  
  Serial.println("Found ID #" + String(finger.fingerID) + " with confidence " + String(finger.confidence));
  return finger.fingerID;
}

void deleteFingerprint(int id) {
  int p = finger.deleteModel(id);
  
  if (p == FINGERPRINT_OK) {
    sendSerialResponse(CMD_SUCCESS, id, 0, "Deleted fingerprint ID #" + String(id));
  } else {
    sendSerialResponse(CMD_FAILURE, id, 0, "Failed to delete fingerprint ID #" + String(id));
  }
}

void sendSerialResponse(char responseType, int id, int confidence, String message) {
  // Format: R,type,id,confidence,message
  Serial.print(CMD_RESPONSE);
  Serial.print(",");
  Serial.print(responseType);
  Serial.print(",");
  Serial.print(id);
  Serial.print(",");
  Serial.print(confidence);
  Serial.print(",");
  Serial.println(message);
}