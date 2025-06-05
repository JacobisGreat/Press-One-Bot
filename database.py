import sqlite3
import json
from typing import List, Dict, Optional
import os

class Database:
    def __init__(self, db_path: str = "call_bot.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize the database with required tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Contacts table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id TEXT NOT NULL,
                name TEXT NOT NULL,
                email TEXT,
                phone_number TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                digit_pressed TEXT,
                call_sid TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Scripts table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS scripts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                opening_audio_path TEXT,
                after_digit_audio_path TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, name)
            )
        ''')
        
        # Settings table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                concurrent_calls INTEGER DEFAULT 5,
                calls_per_second REAL DEFAULT 1.0,
                caller_id TEXT,
                active_script_id INTEGER,
                FOREIGN KEY (active_script_id) REFERENCES scripts (id)
            )
        ''')
        
        # Call logs table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS call_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contact_id INTEGER,
                campaign_id TEXT,
                call_sid TEXT,
                status TEXT,
                digit_pressed TEXT,
                duration INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (contact_id) REFERENCES contacts (id)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def add_contacts_from_csv(self, campaign_id: str, contacts: List[Dict]) -> int:
        """Add contacts from CSV data"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        inserted = 0
        for contact in contacts:
            try:
                cursor.execute('''
                    INSERT INTO contacts (campaign_id, name, email, phone_number)
                    VALUES (?, ?, ?, ?)
                ''', (campaign_id, contact['name'], contact.get('email', ''), contact['phonenumber']))
                inserted += 1
            except sqlite3.Error as e:
                print(f"Error inserting contact {contact}: {e}")
        
        conn.commit()
        conn.close()
        return inserted
    
    def get_pending_contacts(self, campaign_id: str) -> List[Dict]:
        """Get all pending contacts for a campaign"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, name, email, phone_number, status
            FROM contacts
            WHERE campaign_id = ? AND status = 'pending'
        ''', (campaign_id,))
        
        contacts = []
        for row in cursor.fetchall():
            contacts.append({
                'id': row[0],
                'name': row[1],
                'email': row[2],
                'phone_number': row[3],
                'status': row[4]
            })
        
        conn.close()
        return contacts
    
    def get_contacts_without_digit_press(self, campaign_id: str) -> List[Dict]:
        """Get contacts who didn't press any digit"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, name, email, phone_number, status
            FROM contacts
            WHERE campaign_id = ? AND (digit_pressed IS NULL OR digit_pressed = '') 
            AND status != 'pending'
        ''', (campaign_id,))
        
        contacts = []
        for row in cursor.fetchall():
            contacts.append({
                'id': row[0],
                'name': row[1],
                'email': row[2],
                'phone_number': row[3],
                'status': row[4]
            })
        
        conn.close()
        return contacts
    
    def update_contact_status(self, contact_id: int, status: str, call_sid: str = None, digit_pressed: str = None):
        """Update contact status after call"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE contacts 
            SET status = ?, call_sid = ?, digit_pressed = ?
            WHERE id = ?
        ''', (status, call_sid, digit_pressed, contact_id))
        
        conn.commit()
        conn.close()
    
    def reset_contacts_for_recall(self, contact_ids: List[int]):
        """Reset contacts status to pending for recall"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        placeholders = ','.join('?' * len(contact_ids))
        cursor.execute(f'''
            UPDATE contacts 
            SET status = 'pending', call_sid = NULL, digit_pressed = NULL
            WHERE id IN ({placeholders})
        ''', contact_ids)
        
        conn.commit()
        conn.close()
    
    def save_script(self, user_id: int, name: str, opening_audio_path: str = None, after_digit_audio_path: str = None) -> int:
        """Save or update a script for a specific user"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO scripts (user_id, name, opening_audio_path, after_digit_audio_path)
            VALUES (?, ?, ?, ?)
        ''', (user_id, name, opening_audio_path, after_digit_audio_path))
        
        script_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return script_id
    
    def get_scripts(self, user_id: int) -> List[Dict]:
        """Get all scripts for a specific user"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT id, name, opening_audio_path, after_digit_audio_path FROM scripts WHERE user_id = ?', (user_id,))
        
        scripts = []
        for row in cursor.fetchall():
            scripts.append({
                'id': row[0],
                'name': row[1],
                'opening_audio_path': row[2],
                'after_digit_audio_path': row[3]
            })
        
        conn.close()
        return scripts
    
    def get_script(self, user_id: int, script_id: int) -> Optional[Dict]:
        """Get a specific script for a user (validates ownership)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT id, name, opening_audio_path, after_digit_audio_path FROM scripts WHERE id = ? AND user_id = ?', (script_id, user_id))
        row = cursor.fetchone()
        
        if row:
            script = {
                'id': row[0],
                'name': row[1],
                'opening_audio_path': row[2],
                'after_digit_audio_path': row[3]
            }
        else:
            script = None
        
        conn.close()
        return script
    
    def get_user_settings(self, user_id: int) -> Dict:
        """Get user settings"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT concurrent_calls, calls_per_second, caller_id, active_script_id FROM settings WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        
        if row:
            settings = {
                'concurrent_calls': row[0],
                'calls_per_second': row[1],
                'caller_id': row[2],
                'active_script_id': row[3]
            }
        else:
            # Default settings
            settings = {
                'concurrent_calls': 5,
                'calls_per_second': 1.0,
                'caller_id': None,
                'active_script_id': None
            }
            self.save_user_settings(user_id, **settings)
        
        conn.close()
        return settings
    
    def save_user_settings(self, user_id: int, concurrent_calls: int = None, 
                          calls_per_second: float = None, caller_id: str = None, 
                          active_script_id: int = None):
        """Save user settings"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Check if user settings exist
        cursor.execute('SELECT concurrent_calls, calls_per_second, caller_id, active_script_id FROM settings WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        
        if row:
            # User exists, get current settings
            current = {
                'concurrent_calls': row[0],
                'calls_per_second': row[1],
                'caller_id': row[2],
                'active_script_id': row[3]
            }
        else:
            # User doesn't exist, use defaults
            current = {
                'concurrent_calls': 5,
                'calls_per_second': 1.0,
                'caller_id': None,
                'active_script_id': None
            }
        
        # Update only provided values
        if concurrent_calls is not None:
            current['concurrent_calls'] = concurrent_calls
        if calls_per_second is not None:
            current['calls_per_second'] = calls_per_second
        if caller_id is not None:
            current['caller_id'] = caller_id
        if active_script_id is not None:
            current['active_script_id'] = active_script_id
        
        cursor.execute('''
            INSERT OR REPLACE INTO settings 
            (user_id, concurrent_calls, calls_per_second, caller_id, active_script_id)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, current['concurrent_calls'], current['calls_per_second'], 
              current['caller_id'], current['active_script_id']))
        
        conn.commit()
        conn.close()
    
    def log_call(self, contact_id: int, campaign_id: str, call_sid: str, status: str, 
                digit_pressed: str = None, duration: int = None):
        """Log call details"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO call_logs (contact_id, campaign_id, call_sid, status, digit_pressed, duration)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (contact_id, campaign_id, call_sid, status, digit_pressed, duration))
        
        conn.commit()
        conn.close() 