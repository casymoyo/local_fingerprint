-- Create the fingerprint database
CREATE DATABASE IF NOT EXISTS fingerprint_db;
USE fingerprint_db;

-- Create fingerprints table to store enrolled fingerprints
CREATE TABLE IF NOT EXISTS fingerprints (
    id INT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    registration_date DATETIME NOT NULL,
    last_access DATETIME
);

-- Create access_logs table to track all access attempts
CREATE TABLE IF NOT EXISTS access_logs (
    log_id INT AUTO_INCREMENT PRIMARY KEY,
    fingerprint_id INT,
    timestamp DATETIME NOT NULL,
    confidence INT,
    status VARCHAR(20) NOT NULL,
    FOREIGN KEY (fingerprint_id) REFERENCES fingerprints(id) ON DELETE SET NULL
);

-- Create a user for the Python application (
CREATE USER IF NOT EXISTS 'fingerprint_user'@'localhost' IDENTIFIED BY 'your_secure_password';
GRANT ALL PRIVILEGES ON fingerprint_db.* TO 'fingerprint_user'@'localhost';
FLUSH PRIVILEGES;

-- Insert some test data (optional)
-- INSERT INTO fingerprints (id, name, registration_date, last_access) 
-- VALUES (1, 'test', NOW(), NOW());