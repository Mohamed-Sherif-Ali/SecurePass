# SecurePass

**Local Multi-User Password Manager**

SecurePass is an desktop password manager built with Python, PyQt5, SQLite, and authenticated encryption.

Stored passwords are encrypted locally using AES-256-GCM. Encryption keys are derived from each user's master password using PBKDF2 and randomly generated salts.

> SecurePass is a learning project and has not undergone an independent security audit. Do not use it as the only storage location for critical credentials.

## ✨ Features

### 🛡️ **Security**
- AES-256-GCM authenticated encryption
- PBKDF2-based key derivation
- Random salt and nonce for each encryption operation
- Authentication tags for detecting modified ciphertext
- Master-password verification without storing the master password
- Local SQLite storage
- Owner-only database permissions where supported
- Clipboard clearing after 30 seconds

### 🎨 **User Experience**
- **Multi-User Support** - Different users, different master passwords
- **Password Strength Analyzer** - Real-time visual feedback
- **Secure Password Generator** - Cryptographically random passwords
- **Auto-Clearing Clipboard** - Passwords auto-clear after 30 seconds
- **Dark Theme** - Easy on the eyes
- **Intuitive Interface** - Simple tabbed layout

### 🔒 **Password Management**
- **Add Entries** - Store passwords for any service
- **Retrieve Entries** - Quick password lookup
- **Generate Passwords** - Create strong random passwords (8-128 characters)
- **View All Services** - See what you've saved at a glance

---

## 📸 Screenshots

```
┌────────────────────────────────────────────────┐
│ 🔐 SecurePass — mohamed                       │
├────────────────────────────────────────────────┤
│  ➕ Add  🔍 Retrieve  🔑 Generate  📋 View All │
├────────────────────────────────────────────────┤
│                                                │
│  Service:    [_________________________]      │
│  Username:   [_________________________]      │
│  Password:   [•••••••••••••••••••••••••]      │
│  Strength:   [████████░░░░░░░░░░] 80%         │
│              ☐ Show Password                   │
│              [💾 Save Entry]                   │
│                                                │
└────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### Installation

```bash
# Clone repository
git clone https://github.com/Mohamed-Sherif-Ali/SecurePass.git
cd SecurePass

# Install dependencies
pip install -r requirements.txt

# Run application
python secure_password_manager.py
```

### First Launch

1. **Enter username** - Choose any username (alphanumeric + underscore)
2. **Set master password** - This encrypts ALL your passwords
3. **Start adding passwords!**

⚠️ **IMPORTANT**: Your master password cannot be recovered. If you forget it, your passwords are permanently lost!

---

## 📋 Requirements

- **Python 3.8+**
- **PyQt5** - GUI framework
- **PyCryptodome** - Encryption library
- **pyperclip** - Clipboard management

### Platform-Specific

**Linux:**
```bash
# Install Qt dependencies
sudo apt install python3-pyqt5

# Install clipboard tool (choose one)
sudo apt install xclip  # or xsel
```

**macOS:**
```bash
# No additional dependencies needed
```

**Windows:**
```bash
# No additional dependencies needed
```

---

## 🔐 Security Technical Details

### Encryption Flow

```
┌─────────────────────────────────────────────────┐
│          ENCRYPTION PROCESS                     │
└─────────────────────────────────────────────────┘

1. User enters plaintext password
2. Generate random 16-byte salt
3. Generate random 16-byte IV
4. Derive AES key: PBKDF2(master_password, salt, 600k iterations)
5. Encrypt with AES-256-GCM
6. Store: base64(salt + IV + ciphertext + auth_tag)
```

### Master Password Verification

Instead of storing the master password, SecurePass encrypts a known string ("verifyme") with your master password. When you log in, it tries to decrypt this string:
- ✅ **Decryption succeeds** → Correct password
- ❌ **Decryption fails** → Wrong password

This way, your master password is never stored anywhere.

### Key Security Features

| Feature | Implementation | Why It Matters |
|---------|---------------|----------------|
| **Encryption** | AES-256-GCM | Industry standard, used by governments |
| **Key Derivation** | PBKDF2 (600k iterations) | Makes brute-force attacks expensive |
| **Unique Salts** | Random per encryption | Prevents rainbow table attacks |
| **Authentication** | GCM mode | Detects data tampering |
| **Database Perms** | 0600 (owner only) | Other users can't read your file |
| **Local Storage** | SQLite file | No cloud = no remote attacks |

---

## 💻 Usage Guide

### Adding a Password

1. Click **"➕ Add"** tab
2. Enter service name (e.g., "Gmail")
3. Enter username/email
4. Enter password (or generate one in the Generate tab)
5. Watch the strength indicator
6. Click **"💾 Save Entry"**

### Retrieving a Password

1. Click **"🔍 Retrieve"** tab
2. Enter service name
3. Enter username
4. Click **"🔍 Retrieve Password"**
5. Password appears (hidden by default)
6. Check "Show Password" to reveal
7. Click **"📋 Copy to Clipboard"**
   - Auto-clears after 30 seconds!

### Generating a Strong Password

1. Click **"🔑 Generate"** tab
2. Choose length (8-128 characters)
3. Toggle symbol inclusion
4. Click **"🎲 Generate Password"**
5. Copy to clipboard or use in "Add Entry" tab

### Viewing All Saved Services

1. Click **"📋 View All"** tab
2. Click **"🔄 Refresh List"**
3. See all your saved service:username pairs

---

## 🗂️ File Structure

```
securepass/
├── secure_password_manager.py    # Main application
├── requirements.txt              # Python dependencies
├── README.md                     # This file
└── passwords.db                  # Created on first run (encrypted data)
```

### Database Schema

```sql
-- Users table
CREATE TABLE users (
    username TEXT PRIMARY KEY,
    verify_blob TEXT NOT NULL  -- Encrypted verification string
);

-- Passwords table
CREATE TABLE passwords (
    service TEXT NOT NULL,
    username TEXT NOT NULL,
    encrypted_password TEXT NOT NULL,
    owner TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (service, username, owner),
    FOREIGN KEY (owner) REFERENCES users(username) ON DELETE CASCADE
);
```

---

## 🔧 Advanced Usage

### Multiple Users

Each user has their own isolated password vault:

```bash
# User 1 logs in with username "alice" and her master password
# → Can only see/access her passwords

# User 2 logs in with username "bob" and his master password
# → Can only see/access his passwords
```

Users share the same database file but cannot decrypt each other's passwords.

### Backup Your Database

```bash
# Create backup
cp passwords.db passwords_backup_$(date +%Y%m%d).db

# Restore backup
cp passwords_backup_20250101.db passwords.db
```

⚠️ **Important**: Backups contain encrypted data. You still need your master password to access them!

### Changing Master Password

Currently not supported. To change your master password:

1. Export all passwords (write them down temporarily)
2. Delete database: `rm passwords.db`
3. Re-launch app with new master password
4. Re-add all passwords

*Future versions will include a password change feature.*

---

## 🛡️ Security Best Practices

### ✅ DO:
- Use a **strong master password** (16+ characters, mixed case, symbols)
- **Back up** your database regularly
- Keep your computer **malware-free**
- Use **full disk encryption** (FileVault, BitLocker, LUKS)
- Generate **unique passwords** for each service

### ❌ DON'T:
- Share your master password
- Store master password in plaintext anywhere
- Use the same password across multiple services
- Run on untrusted/shared computers
- Leave application open when away from computer

---

## 🐛 Troubleshooting

### "Module not found" errors

```bash
# Reinstall dependencies
pip install -r requirements.txt --upgrade
```

### Clipboard not working (Linux)

```bash
# Install xclip
sudo apt install xclip

# Or xsel
sudo apt install xsel
```

### PyQt5 installation fails

```bash
# Use system package instead
sudo apt install python3-pyqt5  # Debian/Ubuntu
sudo dnf install python3-qt5    # Fedora
brew install pyqt5              # macOS
```

### "Invalid master password" on first login

This is a **new user**. The message is misleading—just try a different username. Each username needs a unique master password.

### Forgot master password

**There is no recovery**. Your passwords are permanently encrypted. This is by design—even the developer cannot decrypt your passwords without your master password.

Options:
1. Try to remember it
2. Check password managers you might have saved it in
3. Start fresh (delete `passwords.db` and create new account)

---

## 🔬 Technical Deep Dive

### Why AES-GCM?

**AES-GCM** (Galois/Counter Mode) provides:
- **Confidentiality** - Data is encrypted
- **Authenticity** - Tampering is detected
- **Performance** - Hardware acceleration available

Traditional AES-CBC only encrypts but doesn't detect tampering. An attacker could modify ciphertext. GCM prevents this with authentication tags.


### Key Derivation

SecurePass currently configures PBKDF2 with 600,000 iterations and derives a 32-byte encryption key from the user's master password and a randomly generated salt.

The work factor makes password guessing more computationally expensive, but actual resistance depends heavily on the strength of the user's master password, the selected PBKDF2 hash function, and the attacker's hardware.

Cryptographic parameters should be reviewed and benchmarked before treating the application as production-ready.

**600k iterations** is the 2023 OWASP recommendation for maximum security without impacting user experience.

### Salt and IV Explained

**Salt:**
- Prevents rainbow table attacks
- Makes identical passwords encrypt differently
- 16 random bytes per encryption operation

**IV (Initialization Vector):**
- Ensures same plaintext encrypts differently each time
- 16 random bytes per encryption operation
- Never reused with the same key

**Example:**
```
Password: "MyPassword123"

Encryption 1:
Salt: a3f7c91b2e4d...
IV:   9c3e8f1a7b2d...
Ciphertext: xe9f2a...

Encryption 2 (same password):
Salt: 7b4e9f2c1a3d...  ← Different!
IV:   1f8e3b9c7a2d...  ← Different!
Ciphertext: 4a8e7f...    ← Different!
```

Attackers can't use precomputed tables because every encryption is unique.

---

## 📊 Performance

- **Encryption speed**: ~10ms per password (on modern CPU)
- **Login time**: ~1-2 seconds (PBKDF2 key derivation)
- **Database size**: ~1KB per 100 passwords
- **Memory usage**: ~50MB (Qt5 GUI)

---

## 🎓 Learning Outcomes

This project demonstrates:
- **Cryptography**: AES-GCM, PBKDF2, salts, IVs
- **Security**: Master password verification, secure storage
- **GUI Development**: PyQt5 interface design
- **Database**: SQLite schema design, foreign keys
- **Python**: OOP, exception handling, type hints

---

## 🚀 Future Enhancements

- [ ] Master password change functionality
- [ ] Password history tracking
- [ ] Export/import passwords (encrypted)
- [ ] Password expiration warnings
- [ ] 2FA integration
- [ ] Browser extension
- [ ] Mobile app (Android/iOS)
- [ ] Biometric authentication
- [ ] Secure notes storage
- [ ] Password audit (check for reused passwords)

---

## 📄 License

MIT License - See LICENSE file for details

---

## 👤 Author

**Mohamed Sherif Ali**   

---

## 🙏 Acknowledgments

- **PyCryptodome** - Excellent cryptography library
- **PyQt5** - Powerful GUI framework
- **OWASP** - Security best practices

---

## Security Disclaimer

SecurePass is an educational project provided without warranty.

Although it uses established cryptographic primitives, the application has not received an independent security audit, penetration test, or formal cryptographic review. Implementation errors, endpoint compromise, malware, weak master passwords, or backup exposure may still place stored credentials at risk.

For important credentials, use a mature and independently audited password manager.

---

**🔐 Keep your master password safe. It's the key to everything.**
