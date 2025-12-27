# VinnoDrive - Cloud Storage with File Deduplication

A secure cloud storage application with intelligent file deduplication that saves storage space by detecting and storing duplicate files only once.

## Features

- **Smart Deduplication**: Automatically detects duplicate files and stores them only once
- **Multiple File Upload**: Upload multiple files simultaneously
- **Folder Organization**: Create and manage folders
- **File Sharing**: Share files publicly or privately with specific users
- **Storage Management**: Track usage with quota visualization
- **Modern UI**: Responsive design with dark/light theme toggle

## Setup Instructions

### Prerequisites
- Python 3.8+

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/S-T-HARINI/vinnodrive.git
cd vinnodrive
```

2. **Create virtual environment**
```bash
python -m venv venv
```

3. **Activate virtual environment**
- Windows: `venv\Scripts\activate`
- Mac/Linux: `source venv/bin/activate`

4. **Install dependencies**
```bash
pip install -r requirements.txt
```

5. **Run the application**
```bash
uvicorn app.main:app --reload
```

6. **Open in browser**
```
http://127.0.0.1:8000
```

## Usage

1. Sign up and create an account
2. Upload files (drag & drop or click to browse)
3. Create folders to organize files
4. Share files via public links or privately
5. Track storage savings from deduplication

## Tech Stack

- **Backend**: FastAPI
- **Database**: SQLAlchemy + SQLite
- **Authentication**: bcrypt
- **Frontend**: HTML, CSS, JavaScript

## Project Structure
```
## Project Structure
```
vinnodrive/
├── app/
│   ├── database.py
│   ├── helpers.py
│   ├── main.py
│   └── models.py
├── storage/
│   └── blobs/           # Auto-created for file storage
├── templates/
│   ├── base.html
│   ├── dashboard.html
│   ├── login.html
│   ├── share.html
│   ├── signup.html
│   └── upload.html
├── requirements.txt
└── README.md
```

**Note:** The `storage/blobs/` directory is automatically created when you run the application for the first time.
```

## How Deduplication Works

Files are stored using SHA-256 hashing:
- Each file's content generates a unique hash
- If the hash exists, only a new reference is created (no duplicate storage)
- Dashboard shows storage savings from deduplication

## Configuration

- Default storage quota: 10 MB per user
- Rate limiting: 2 requests/second
- Configurable in `app/main.py`

## Author

S T Harini