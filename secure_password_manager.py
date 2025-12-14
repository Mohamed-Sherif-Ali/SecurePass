#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════════
SecurePass - Multi-User Password Manager
═══════════════════════════════════════════════════════════════════════════

A secure, locally-stored password manager with military-grade encryption.
Features:
- AES-256-GCM encryption with PBKDF2 key derivation
- Multi-user support with master password verification
- Password strength analyzer
- Secure password generator
- Auto-clearing clipboard (30 seconds)
- Dark-themed Qt5 interface

Security:
- 600,000 PBKDF2 iterations (OWASP recommended)
- Unique salt per encrypted field
- GCM mode for authenticated encryption
- Database file permissions: 0600 (owner read/write only)
"""

import os
import stat
import sys
import base64
import secrets
import string
import sqlite3
import ctypes
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget, QAction,
    QFormLayout, QLineEdit, QPushButton, QLabel, QSpinBox,
    QCheckBox, QProgressBar, QToolBar, QMessageBox, QStatusBar,
    QInputDialog, QVBoxLayout
)
from Crypto.Cipher import AES
from Crypto.Protocol.KDF import PBKDF2
import pyperclip

# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════

DB_PATH = "passwords.db"           # SQLite database file path
KDF_ITERS = 600_000                # PBKDF2 iterations (OWASP 2023 recommendation)
CLIPBOARD_CLEAR_MS = 30000         # Auto-clear clipboard after 30 seconds
MAX_USERNAME_LENGTH = 50           # Maximum username length
MIN_PASSWORD_LENGTH = 8            # Minimum generated password length
MAX_PASSWORD_LENGTH = 128          # Maximum generated password length

# ═══════════════════════════════════════════════════════════════════════════
# DATABASE INITIALIZATION
# ═══════════════════════════════════════════════════════════════════════════

def init_db(path=DB_PATH):
    """
    Initialize SQLite database with secure permissions
    
    Creates database file with owner-only permissions (0600) BEFORE opening
    to prevent race condition where other processes could read during creation.
    
    Schema:
        users: Stores username and encrypted verification blob
        passwords: Stores encrypted passwords with service/username/owner
    
    Returns:
        sqlite3.Connection: Database connection object
    """
    new = not os.path.exists(path)
    
    if new:
        # Create empty file with secure permissions BEFORE opening database
        # This prevents race condition vulnerability
        open(path, "a").close()
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # 0600: owner read/write only
    
    # Connect to database
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    
    # Create users table (stores master password verification)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            verify_blob TEXT NOT NULL
        )
    """)
    
    # Create passwords table (stores encrypted passwords)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS passwords (
            service TEXT NOT NULL,
            username TEXT NOT NULL,
            encrypted_password TEXT NOT NULL,
            owner TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (service, username, owner),
            FOREIGN KEY (owner) REFERENCES users(username) ON DELETE CASCADE
        )
    """)
    
    conn.commit()
    return conn

# ═══════════════════════════════════════════════════════════════════════════
# ENCRYPTION MANAGER
# ═══════════════════════════════════════════════════════════════════════════

class EncryptionManager:
    """
    Handles all encryption/decryption using AES-256-GCM with PBKDF2 key derivation
    
    Security features:
    - Unique random salt per encryption operation (prevents rainbow tables)
    - Unique random IV per encryption operation (prevents pattern analysis)
    - GCM mode provides authenticated encryption (detects tampering)
    - PBKDF2 with 600k iterations (makes brute-force attacks expensive)
    """
    
    def __init__(self, key: bytes):
        """
        Initialize encryption manager with master password
        
        Args:
            key: Master password as bytes (will be used for key derivation)
        """
        self.key = key

    def _derive_key(self, salt: bytes) -> bytes:
        """
        Derive 256-bit AES key from master password using PBKDF2
        
        PBKDF2 parameters:
        - Password: User's master password
        - Salt: 16 random bytes (unique per operation)
        - Iterations: 600,000 (OWASP 2023 recommendation)
        - Key length: 32 bytes (256 bits for AES-256)
        
        Args:
            salt: 16-byte random salt
            
        Returns:
            32-byte AES key
        """
        return PBKDF2(
            self.key,           # Master password
            salt,               # Random salt
            dkLen=32,          # 256-bit key for AES-256
            count=KDF_ITERS    # 600,000 iterations
        )

    def encrypt(self, plaintext: str) -> str:
        """
        Encrypt plaintext string using AES-256-GCM
        
        Process:
        1. Generate random 16-byte salt
        2. Generate random 16-byte IV (initialization vector)
        3. Derive AES key from master password + salt
        4. Encrypt plaintext using AES-GCM
        5. Return: base64(salt + IV + ciphertext + auth_tag)
        
        Args:
            plaintext: String to encrypt
            
        Returns:
            Base64-encoded blob containing salt + IV + ciphertext + tag
        """
        # Generate cryptographically secure random values
        salt = secrets.token_bytes(16)  # Random salt for key derivation
        iv = secrets.token_bytes(16)    # Random IV for AES-GCM
        
        # Derive encryption key from master password
        aes_key = self._derive_key(salt)
        
        # Create AES cipher in GCM mode (authenticated encryption)
        cipher = AES.new(aes_key, AES.MODE_GCM, nonce=iv)
        
        # Encrypt and generate authentication tag
        ciphertext, auth_tag = cipher.encrypt_and_digest(plaintext.encode('utf-8'))
        
        # Combine all components: salt + IV + ciphertext + tag
        blob = salt + iv + ciphertext + auth_tag
        
        # Return as base64 string for text storage
        return base64.b64encode(blob).decode('ascii')

    def decrypt(self, blob_b64: str) -> str:
        """
        Decrypt AES-256-GCM encrypted blob
        
        Process:
        1. Decode base64 to get binary blob
        2. Extract salt (first 16 bytes)
        3. Extract IV (next 16 bytes)
        4. Extract ciphertext (middle portion)
        5. Extract auth tag (last 16 bytes)
        6. Derive key and decrypt
        7. Verify authentication tag (detect tampering)
        
        Args:
            blob_b64: Base64-encoded encrypted blob
            
        Returns:
            Decrypted plaintext string
            
        Raises:
            ValueError: If authentication tag verification fails (tampered data)
        """
        # Decode base64 to binary
        blob = base64.b64decode(blob_b64)
        
        # Extract components from blob
        salt = blob[:16]           # Bytes 0-15: Salt
        iv = blob[16:32]          # Bytes 16-31: IV
        ciphertext = blob[32:-16] # Middle: Ciphertext
        auth_tag = blob[-16:]     # Last 16 bytes: Authentication tag
        
        # Derive the same key using extracted salt
        aes_key = self._derive_key(salt)
        
        # Create cipher with same parameters
        cipher = AES.new(aes_key, AES.MODE_GCM, nonce=iv)
        
        # Decrypt and verify authentication tag
        # Will raise ValueError if tag doesn't match (data was tampered)
        plaintext = cipher.decrypt_and_verify(ciphertext, auth_tag)
        
        return plaintext.decode('utf-8')

# ═══════════════════════════════════════════════════════════════════════════
# USER SESSION
# ═══════════════════════════════════════════════════════════════════════════

class UserSession:
    """
    Represents an authenticated user session
    Contains username and their encryption manager (derived from master password)
    """
    
    def __init__(self, username: str, crypto: EncryptionManager):
        """
        Create new user session
        
        Args:
            username: Logged-in username
            crypto: EncryptionManager initialized with user's master password
        """
        self.username = username
        self.crypto = crypto

# ═══════════════════════════════════════════════════════════════════════════
# PASSWORD DATABASE
# ═══════════════════════════════════════════════════════════════════════════

class PasswordDatabase:
    """
    Handles all database operations for user verification and password storage
    """
    
    def __init__(self, conn: sqlite3.Connection):
        """
        Initialize database handler
        
        Args:
            conn: SQLite database connection
        """
        self.conn = conn
        self.cur = conn.cursor()

    def verify_or_create_user(self, username: str, crypto: EncryptionManager) -> bool:
        """
        Verify master password for existing user or create new user
        
        How it works:
        - Existing user: Decrypt their verification blob with provided master password
          - Success: Password is correct
          - Failure: Wrong password
        - New user: Encrypt a known string ("verifyme") and store it
        
        This allows password verification without storing the password itself.
        
        Args:
            username: Username to verify or create
            crypto: EncryptionManager with master password
            
        Returns:
            True if password correct (existing) or user created (new)
            False if password incorrect for existing user
        """
        # Check if user already exists
        self.cur.execute("SELECT verify_blob FROM users WHERE username=?", (username,))
        row = self.cur.fetchone()
        
        if row:
            # Existing user - verify master password
            try:
                # Try to decrypt verification blob
                decrypted = crypto.decrypt(row[0])
                return decrypted == "verifyme"  # Correct password if decryption succeeds
            except Exception:
                # Decryption failed = wrong password
                return False
        else:
            # New user - create verification blob
            verify_blob = crypto.encrypt("verifyme")
            self.cur.execute("INSERT INTO users VALUES (?, ?)", (username, verify_blob))
            self.conn.commit()
            return True

    def add_password(self, owner: str, service: str, username: str, 
                     password: str, crypto: EncryptionManager):
        """
        Add or update encrypted password entry
        
        Args:
            owner: Username of password owner
            service: Service name (e.g., "Gmail", "GitHub")
            username: Username/email for the service
            password: Plaintext password to encrypt and store
            crypto: EncryptionManager for encryption
        """
        # Encrypt password
        encrypted = crypto.encrypt(password)
        
        # Store in database (INSERT OR REPLACE updates if exists)
        self.cur.execute(
            "INSERT OR REPLACE INTO passwords (service, username, encrypted_password, owner) VALUES (?, ?, ?, ?)",
            (service, username, encrypted, owner)
        )
        self.conn.commit()

    def get_password(self, owner: str, service: str, username: str, 
                     crypto: EncryptionManager) -> str:
        """
        Retrieve and decrypt password
        
        Args:
            owner: Username of password owner
            service: Service name
            username: Service username
            crypto: EncryptionManager for decryption
            
        Returns:
            Decrypted password string, or None if not found/decryption failed
        """
        # Query database
        self.cur.execute(
            "SELECT encrypted_password FROM passwords WHERE service=? AND username=? AND owner=?",
            (service, username, owner)
        )
        row = self.cur.fetchone()
        
        if not row:
            return None  # Entry not found
        
        # Try to decrypt
        try:
            return crypto.decrypt(row[0])
        except Exception:
            return None  # Decryption failed (corrupted or wrong key)

    def list_services(self, owner: str) -> list:
        """
        Get list of all services for a user
        
        Args:
            owner: Username
            
        Returns:
            List of (service, username) tuples
        """
        self.cur.execute(
            "SELECT service, username FROM passwords WHERE owner=? ORDER BY service",
            (owner,)
        )
        return self.cur.fetchall()

# ═══════════════════════════════════════════════════════════════════════════
# PASSWORD UTILITIES
# ═══════════════════════════════════════════════════════════════════════════

def calculate_password_strength(password: str) -> tuple:
    """
    Calculate password strength based on character diversity and length
    
    Criteria:
    - Lowercase letters (a-z)
    - Uppercase letters (A-Z)
    - Digits (0-9)
    - Special characters (!@#$%^&*, etc.)
    
    Args:
        password: Password to analyze
        
    Returns:
        Tuple of (diversity_score, length) where:
        - diversity_score: 0-4 (number of character categories present)
        - length: Password length
    """
    categories = [
        any(c.islower() for c in password),            # Has lowercase?
        any(c.isupper() for c in password),            # Has uppercase?
        any(c.isdigit() for c in password),            # Has digits?
        any(c in string.punctuation for c in password) # Has symbols?
    ]
    
    diversity_score = sum(categories)
    return diversity_score, len(password)

def generate_secure_password(length: int = 16, include_symbols: bool = True) -> str:
    """
    Generate cryptographically secure random password
    
    Uses secrets module (cryptographically secure random number generator)
    instead of random module (which is predictable).
    
    Args:
        length: Password length (8-128)
        include_symbols: Include special characters
        
    Returns:
        Random password string
    """
    # Build character set
    characters = string.ascii_letters + string.digits  # a-z, A-Z, 0-9
    if include_symbols:
        characters += string.punctuation  # Add !@#$%^&*()...
    
    # Generate password using cryptographically secure random
    return ''.join(secrets.choice(characters) for _ in range(length))

def validate_username(username: str) -> tuple:
    """
    Validate username for security and database compatibility
    
    Rules:
    - Not empty
    - Max 50 characters
    - Only alphanumeric and underscore (prevents SQL injection)
    
    Args:
        username: Username to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not username:
        return False, "Username cannot be empty"
    
    if len(username) > MAX_USERNAME_LENGTH:
        return False, f"Username too long (max {MAX_USERNAME_LENGTH} characters)"
    
    if not username.replace('_', '').isalnum():
        return False, "Username can only contain letters, numbers, and underscores"
    
    return True, ""

def secure_clear_string(s: str):
    """
    Attempt to clear string from memory (best effort)
    
    Note: Python strings are immutable, so true secure deletion is impossible.
    This overwrites the memory location, but Python may have made copies.
    For true security, use a language with manual memory management.
    """
    try:
        # Get memory address of string's buffer
        str_address = id(s)
        # Overwrite with zeros (ctypes hack, not guaranteed to work)
        ctypes.memset(str_address, 0, len(s))
    except:
        pass  # Best effort - may not work on all Python implementations

# ═══════════════════════════════════════════════════════════════════════════
# MAIN WINDOW (GUI)
# ═══════════════════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    """
    Main application window with tabbed interface
    
    Tabs:
    1. Add Entry - Save new password
    2. Retrieve Entry - Get existing password
    3. Generate Password - Create strong random password
    4. View All - List all saved services
    """
    
    def __init__(self, db: PasswordDatabase, session: UserSession):
        """
        Initialize main window
        
        Args:
            db: Password database handler
            session: Authenticated user session
        """
        super().__init__()
        self.db = db
        self.session = session
        
        # Set window properties
        self.setWindowTitle(f"🔐 SecurePass — {session.username}")
        self.resize(600, 400)
        
        # Build UI and apply styling
        self._build_interface()
        self._apply_dark_theme()

    def _build_interface(self):
        """
        Build the main user interface
        Creates menu bar, toolbar, tabs, and status bar
        """
        # ─────────────────────────────────────────────────────────────────
        # Menu Bar
        # ─────────────────────────────────────────────────────────────────
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("File")
        exit_action = QAction("Exit", self, shortcut="Ctrl+Q", triggered=self.close)
        file_menu.addAction(exit_action)
        
        # Help menu
        help_menu = menubar.addMenu("Help")
        about_action = QAction("About", self, triggered=self._show_about)
        help_menu.addAction(about_action)

        # ─────────────────────────────────────────────────────────────────
        # Toolbar
        # ─────────────────────────────────────────────────────────────────
        toolbar = QToolBar()
        toolbar.addAction("➕ Add", lambda: self.tabs.setCurrentIndex(0))
        toolbar.addAction("🔍 Retrieve", lambda: self.tabs.setCurrentIndex(1))
        toolbar.addAction("🔑 Generate", lambda: self.tabs.setCurrentIndex(2))
        toolbar.addAction("📋 View All", lambda: self.tabs.setCurrentIndex(3))
        self.addToolBar(toolbar)

        # ─────────────────────────────────────────────────────────────────
        # Tab Widget
        # ─────────────────────────────────────────────────────────────────
        self.tabs = QTabWidget()
        self.tabs.addTab(self._create_add_tab(), "Add Entry")
        self.tabs.addTab(self._create_retrieve_tab(), "Retrieve Entry")
        self.tabs.addTab(self._create_generate_tab(), "Generate Password")
        self.tabs.addTab(self._create_list_tab(), "View All")
        
        self.setCentralWidget(self.tabs)
        
        # ─────────────────────────────────────────────────────────────────
        # Status Bar
        # ─────────────────────────────────────────────────────────────────
        self.setStatusBar(QStatusBar())

    def _create_add_tab(self):
        """
        Create the "Add Entry" tab for saving passwords
        
        Returns:
            QWidget containing the add entry form
        """
        widget = QWidget()
        layout = QFormLayout(widget)
        
        # Input fields
        self.service_input = QLineEdit()
        self.username_input = QLineEdit()
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)  # Hide password by default
        
        # Password strength indicator
        self.strength_bar = QProgressBar()
        self.strength_bar.setRange(0, 100)
        self.strength_bar.setTextVisible(True)
        self.strength_bar.setFormat("Strength: %p%")
        
        # Update strength bar as user types
        self.password_input.textChanged.connect(self._update_strength_indicator)
        
        # Show/hide password checkbox
        show_password_checkbox = QCheckBox("Show Password")
        show_password_checkbox.toggled.connect(
            lambda checked: self.password_input.setEchoMode(
                QLineEdit.Normal if checked else QLineEdit.Password
            )
        )
        
        # Save button
        save_button = QPushButton("💾 Save Entry")
        save_button.clicked.connect(self._handle_save_entry)
        
        # Add widgets to layout
        layout.addRow("Service:", self.service_input)
        layout.addRow("Username:", self.username_input)
        layout.addRow("Password:", self.password_input)
        layout.addRow("", self.strength_bar)
        layout.addRow("", show_password_checkbox)
        layout.addRow("", save_button)
        
        return widget

    def _create_retrieve_tab(self):
        """
        Create the "Retrieve Entry" tab for getting saved passwords
        
        Returns:
            QWidget containing the retrieve form
        """
        widget = QWidget()
        layout = QFormLayout(widget)
        
        # Input fields
        self.service_get = QLineEdit()
        self.username_get = QLineEdit()
        
        # Retrieve button
        retrieve_button = QPushButton("🔍 Retrieve Password")
        retrieve_button.clicked.connect(self._handle_retrieve_entry)
        
        # Output field (read-only)
        self.password_output = QLineEdit()
        self.password_output.setReadOnly(True)
        self.password_output.setEchoMode(QLineEdit.Password)  # Hidden by default
        
        # Show/hide retrieved password
        show_output_checkbox = QCheckBox("Show Password")
        show_output_checkbox.toggled.connect(
            lambda checked: self.password_output.setEchoMode(
                QLineEdit.Normal if checked else QLineEdit.Password
            )
        )
        
        # Copy to clipboard button
        copy_button = QPushButton("📋 Copy to Clipboard")
        copy_button.clicked.connect(self._handle_copy_password)
        
        # Add widgets to layout
        layout.addRow("Service:", self.service_get)
        layout.addRow("Username:", self.username_get)
        layout.addRow("", retrieve_button)
        layout.addRow("Password:", self.password_output)
        layout.addRow("", show_output_checkbox)
        layout.addRow("", copy_button)
        
        return widget

    def _create_generate_tab(self):
        """
        Create the "Generate Password" tab
        
        Returns:
            QWidget containing the password generator
        """
        widget = QWidget()
        layout = QFormLayout(widget)
        
        # Length selector
        self.length_spinner = QSpinBox()
        self.length_spinner.setRange(MIN_PASSWORD_LENGTH, MAX_PASSWORD_LENGTH)
        self.length_spinner.setValue(16)  # Default 16 characters
        
        # Symbol inclusion checkbox
        self.symbols_checkbox = QCheckBox("Include Symbols (!@#$%^&*)")
        self.symbols_checkbox.setChecked(True)  # Enabled by default
        
        # Generate button
        generate_button = QPushButton("🎲 Generate Password")
        generate_button.clicked.connect(self._handle_generate_password)
        
        # Generated password output
        self.generated_password = QLineEdit()
        self.generated_password.setReadOnly(True)
        
        # Copy button
        copy_gen_button = QPushButton("📋 Copy to Clipboard")
        copy_gen_button.clicked.connect(
            lambda: self._copy_to_clipboard(self.generated_password.text())
        )
        
        # Add widgets to layout
        layout.addRow("Length:", self.length_spinner)
        layout.addRow("", self.symbols_checkbox)
        layout.addRow("", generate_button)
        layout.addRow("Generated:", self.generated_password)
        layout.addRow("", copy_gen_button)
        
        return widget

    def _create_list_tab(self):
        """
        Create the "View All" tab showing all saved services
        
        Returns:
            QWidget containing the service list
        """
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Refresh button
        refresh_button = QPushButton("🔄 Refresh List")
        refresh_button.clicked.connect(self._refresh_service_list)
        
        # Services list (plain text for simplicity)
        self.services_list = QLineEdit()
        self.services_list.setReadOnly(True)
        self.services_list.setPlaceholderText("Click 'Refresh List' to view saved services")
        
        layout.addWidget(refresh_button)
        layout.addWidget(QLabel("Saved Services:"))
        layout.addWidget(self.services_list)
        
        return widget

    def _update_strength_indicator(self, password: str):
        """
        Update password strength indicator bar
        
        Args:
            password: Password text to analyze
        """
        score, length = calculate_password_strength(password)
        
        # Calculate percentage (0-100)
        # Base percentage on diversity (0-4 categories)
        percentage = int((score / 4) * 100)
        
        # Penalize short passwords
        if length < MIN_PASSWORD_LENGTH:
            percentage = min(percentage, 25)  # Cap at 25% if too short
        
        # Update progress bar
        self.strength_bar.setValue(percentage)
        
        # Color code based on strength
        if percentage < 40:
            color = "#d32f2f"  # Red - weak
        elif percentage < 70:
            color = "#ff9800"  # Orange - medium
        else:
            color = "#4caf50"  # Green - strong
        
        self.strength_bar.setStyleSheet(f"QProgressBar::chunk {{ background-color: {color}; }}")

    def _handle_save_entry(self):
        """
        Handle saving a password entry to database
        """
        # Get input values (strip whitespace from service/username, NOT from password)
        service = self.service_input.text().strip()
        username = self.username_input.text().strip()
        password = self.password_input.text()  # Don't strip password (may be intentional)
        
        # Validate inputs
        if not service or not username or not password:
            self.statusBar().showMessage("❌ All fields are required", 5000)
            return
        
        # Save to database
        self.db.add_password(
            self.session.username,
            service,
            username,
            password,
            self.session.crypto
        )
        
        # Show success message
        self.statusBar().showMessage(f"✅ Saved password for '{service}:{username}'", 5000)
        
        # Clear form
        self.service_input.clear()
        self.username_input.clear()
        self.password_input.clear()
        self.strength_bar.reset()

    def _handle_retrieve_entry(self):
        """
        Handle retrieving a password from database
        """
        # Get inputs
        service = self.service_get.text().strip()
        username = self.username_get.text().strip()
        
        # Validate inputs
        if not service or not username:
            self.statusBar().showMessage("❌ Service and username required", 5000)
            return
        
        # Retrieve from database
        password = self.db.get_password(
            self.session.username,
            service,
            username,
            self.session.crypto
        )
        
        if password is None:
            self.statusBar().showMessage("❌ Entry not found or decryption failed", 5000)
            self.password_output.clear()
            return
        
        # Display retrieved password
        self._current_retrieved_password = password
        self.password_output.setText(password)
        self.statusBar().showMessage("✅ Password retrieved", 3000)

    def _handle_copy_password(self):
        """
        Copy retrieved password to clipboard with auto-clear timer
        """
        if not hasattr(self, "_current_retrieved_password"):
            self.statusBar().showMessage("❌ No password to copy", 3000)
            return
        
        # Copy to clipboard
        self._copy_to_clipboard(self._current_retrieved_password)
        
        # Auto-clear password field after 30 seconds
        QTimer.singleShot(CLIPBOARD_CLEAR_MS, lambda: self.password_output.clear())

    def _handle_generate_password(self):
        """
        Generate a secure random password
        """
        length = self.length_spinner.value()
        include_symbols = self.symbols_checkbox.isChecked()
        
        # Generate password
        password = generate_secure_password(length, include_symbols)
        
        # Display generated password
        self.generated_password.setText(password)
        self.statusBar().showMessage("✅ Password generated", 2000)

    def _refresh_service_list(self):
        """
        Refresh the list of saved services
        """
        services = self.db.list_services(self.session.username)
        
        if not services:
            self.services_list.setText("No saved services")
            return
        
        # Format as "Service: username" list
        formatted = ", ".join([f"{svc}:{usr}" for svc, usr in services])
        self.services_list.setText(formatted)
        self.statusBar().showMessage(f"Found {len(services)} entries", 3000)

    def _copy_to_clipboard(self, text: str):
        """
        Copy text to clipboard with auto-clear timer
        
        Args:
            text: Text to copy
        """
        pyperclip.copy(text)
        self.statusBar().showMessage("📋 Copied to clipboard (auto-clears in 30s)", 3000)
        
        # Auto-clear clipboard after 30 seconds
        QTimer.singleShot(CLIPBOARD_CLEAR_MS, lambda: pyperclip.copy(""))

    def _show_about(self):
        """
        Show about dialog
        """
        QMessageBox.information(
            self,
            "About SecurePass",
            "SecurePass - Multi-User Password Manager\n\n"
            "Security Features:\n"
            "• AES-256-GCM encryption\n"
            "• PBKDF2 key derivation (600k iterations)\n"
            "• Secure local storage\n"
            "• Auto-clearing clipboard\n\n"
            "© 2025 Mohamed Sherif Ali"
        )

    def _apply_dark_theme(self):
        """
        Apply dark color scheme to application
        """
        self.setStyleSheet("""
            /* Main window and widgets */
            QMainWindow, QWidget {
                background-color: #2b2b2b;
                color: #cccccc;
            }
            
            /* Input fields */
            QLineEdit, QSpinBox, QProgressBar {
                background-color: #3c3f41;
                color: #ffffff;
                border: 1px solid #555555;
                padding: 4px;
                border-radius: 3px;
            }
            
            /* Buttons */
            QPushButton {
                background-color: #555555;
                color: #ffffff;
                border: none;
                padding: 6px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #707070;
            }
            QPushButton:pressed {
                background-color: #404040;
            }
            
            /* Menu and toolbar */
            QMenuBar, QMenu, QToolBar {
                background-color: #313335;
                color: #cccccc;
            }
            
            /* Status bar */
            QStatusBar {
                background-color: #313335;
                color: #cccccc;
            }
            
            /* Progress bar */
            QProgressBar {
                text-align: center;
            }
        """)

# ═══════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════

def main():
    """
    Main application entry point
    
    Flow:
    1. Prompt for username
    2. Prompt for master password
    3. Initialize database
    4. Verify or create user
    5. Launch main window
    """
    # Create Qt application
    app = QApplication(sys.argv)
    app.setApplicationName("SecurePass")
    
    # ─────────────────────────────────────────────────────────────────
    # Get username
    # ─────────────────────────────────────────────────────────────────
    username, ok = QInputDialog.getText(
        None,
        "SecurePass - Login",
        "Enter username:",
        QLineEdit.Normal
    )
    
    if not ok or not username:
        return  # User cancelled
    
    # Validate username
    valid, error = validate_username(username)
    if not valid:
        QMessageBox.critical(None, "Invalid Username", error)
        return
    
    # ─────────────────────────────────────────────────────────────────
    # Get master password
    # ─────────────────────────────────────────────────────────────────
    master_password, ok = QInputDialog.getText(
        None,
        "SecurePass - Login",
        f"Enter master password for '{username}':",
        QLineEdit.Password
    )
    
    if not ok or not master_password:
        return  # User cancelled
    
    # Convert to bytes for encryption
    master_password_bytes = master_password.encode('utf-8')
    
    # Clear plaintext password from memory (best effort)
    secure_clear_string(master_password)
    del master_password
    
    # ─────────────────────────────────────────────────────────────────
    # Initialize components
    # ─────────────────────────────────────────────────────────────────
    try:
        # Open database
        conn = init_db()
        
        # Create encryption manager with master password
        crypto = EncryptionManager(master_password_bytes)
        
        # Initialize database handler
        db = PasswordDatabase(conn)
        
        # Verify or create user
        if not db.verify_or_create_user(username, crypto):
            QMessageBox.critical(
                None,
                "Authentication Failed",
                "Invalid master password for existing user.\n\n"
                "If this is a new user, try a different username."
            )
            return
        
        # Create user session
        session = UserSession(username, crypto)
        
        # Launch main window
        window = MainWindow(db, session)
        window.show()
        
        # Run application event loop
        sys.exit(app.exec_())
        
    except Exception as e:
        QMessageBox.critical(
            None,
            "Error",
            f"An error occurred:\n\n{str(e)}"
        )
        return

# ═══════════════════════════════════════════════════════════════════════════
# RUN APPLICATION
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    main()
