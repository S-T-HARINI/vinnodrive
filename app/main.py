from fastapi import FastAPI, Request, UploadFile, File as FastFile, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import List
import os
import hashlib
import secrets
from datetime import datetime, timedelta


from app.database import engine, SessionLocal
from app import models, helpers


app = FastAPI()
models.Base.metadata.create_all(bind=engine)


templates = Jinja2Templates(directory="templates")


UPLOAD_DIR = "storage/blobs"
os.makedirs(UPLOAD_DIR, exist_ok=True)


# Configuration
RATE_LIMIT_CALLS = 2  # API calls per second
RATE_LIMIT_WINDOW = 1  # seconds
STORAGE_QUOTA_MB = 10  # MB per user (configurable)




def get_db():
    db = SessionLocal()
    try:
        return db
    finally:
        db.close()




def check_rate_limit(username: str, endpoint: str, db: Session) -> bool:
    """Check if user has exceeded rate limit. Returns True if allowed, False if blocked."""
    now = datetime.utcnow()
    window_start = now - timedelta(seconds=RATE_LIMIT_WINDOW)
   
    # Count requests in the time window
    recent_requests = db.query(models.RateLimit).filter(
        models.RateLimit.username == username,
        models.RateLimit.endpoint == endpoint,
        models.RateLimit.timestamp >= window_start
    ).count()
   
    if recent_requests >= RATE_LIMIT_CALLS:
        return False
   
    # Log this request
    db.add(models.RateLimit(username=username, endpoint=endpoint, timestamp=now))
    db.commit()
   
    # Clean up old entries (older than 1 minute)
    cleanup_time = now - timedelta(minutes=1)
    db.query(models.RateLimit).filter(models.RateLimit.timestamp < cleanup_time).delete()
    db.commit()
   
    return True




def check_storage_quota(username: str, file_size: int, db: Session) -> tuple[bool, str]:
    """Check if user has enough storage quota. Returns (allowed, error_message)."""
    user = db.query(models.User).filter_by(username=username).first()
    if not user:
        return False, "User not found"
   
    if user.storage_used + file_size > user.storage_quota:
        quota_mb = user.storage_quota / (1024 * 1024)
        used_mb = user.storage_used / (1024 * 1024)
        return False, f"Storage quota exceeded! You have {used_mb:.2f} MB / {quota_mb:.2f} MB used."
   
    return True, ""




# ---------------- HOME ----------------
@app.get("/")
def home():
    return RedirectResponse("/login")




# ---------------- SIGNUP ----------------
@app.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request})




@app.post("/signup")
def signup(request: Request, username: str = Form(...), password: str = Form(...)):
    db: Session = get_db()


    if db.query(models.User).filter_by(username=username).first():
        return templates.TemplateResponse(
            "signup.html",
            {"request": request, "error": "Username already exists"}
        )


    user = models.User(
        username=username,
        password=helpers.hash_password(password),
        storage_quota=STORAGE_QUOTA_MB * 1024 * 1024,  # Convert MB to bytes
        storage_used=0
    )
    db.add(user)
    db.commit()


    return RedirectResponse("/login", status_code=302)




# ---------------- LOGIN ----------------
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})




@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    db: Session = get_db()
    user = db.query(models.User).filter_by(username=username).first()


    if not user:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "User not found. Kindly sign up."}
        )


    if not helpers.verify_password(password, user.password):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Incorrect password."}
        )


    response = RedirectResponse("/upload", status_code=302)
    response.set_cookie(key="user", value=username, path="/", httponly=True)
    return response




# ---------------- LOGOUT ----------------
@app.get("/logout")
def logout():
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie("user")
    return response




# ---------------- UPLOAD PAGE ----------------
@app.get("/upload", response_class=HTMLResponse)
def upload_page(request: Request):
    username = request.cookies.get("user")
    if not username:
        return RedirectResponse("/login")


    db: Session = get_db()


    # Get user info
    user = db.query(models.User).filter_by(username=username).first()
    storage_quota_mb = user.storage_quota / (1024 * 1024)
    storage_used_mb = user.storage_used / (1024 * 1024)
    storage_percent = (user.storage_used / user.storage_quota * 100) if user.storage_quota > 0 else 0


    # Get user's folders
    user_folders = db.query(models.Folder).filter_by(owner=username).all()
    folder_names = [f.name for f in user_folders]


    # Own files
    own_files = db.query(models.File).filter_by(uploader=username).all()


    # Calculate storage statistics
    # Actual storage used (after deduplication) - only count original files
    actual_storage_used = sum(f.size for f in own_files if not f.is_duplicate)
   
    # Original size (before deduplication) - count all files
    original_total_size = sum(f.size for f in own_files)
   
    # Savings
    total_savings_bytes = original_total_size - actual_storage_used
    savings_percentage = (total_savings_bytes / original_total_size * 100) if original_total_size > 0 else 0


    # Files shared with user
    shared_entries = db.query(models.SharedFile).filter_by(shared_with=username).all()
    shared_files = []
    for entry in shared_entries:
        file = db.query(models.File).filter_by(id=entry.file_id).first()
        if file:
            shared_files.append({
                "file": file,
                "shared_by": entry.shared_by,
                "shared_at": entry.shared_at
            })


    # Group own files by folder
    folders_data = {"Root": []}
    for f in own_files:
        folder_name = f.folder if f.folder else "Root"
        if folder_name not in folders_data:
            folders_data[folder_name] = []
        folders_data[folder_name].append(f)


    for name in folder_names:
        if name not in folders_data:
            folders_data[name] = []


    # Sort folders: Root first
    sorted_folders = {"Root": folders_data["Root"]}
    for k in sorted([k for k in folders_data if k != "Root"]):
        sorted_folders[k] = folders_data[k]


    # Public share info
    files_with_shares = []
    for f in own_files:
        share = db.query(models.Share).filter_by(file_id=f.id, is_active=True).first()
       
        has_duplicates = False
        if not f.is_duplicate:
            has_duplicates = db.query(models.File).filter_by(
                uploader=username,
                file_hash=f.file_hash,
                is_duplicate=True
            ).count() > 0
       
        files_with_shares.append({
            "file": f,
            "share_token": share.share_token if share else None,
            "share": share,
            "has_duplicates": has_duplicates
        })


    # All users for sharing
    all_users = [u.username for u in db.query(models.User).all() if u.username != username]


    # Get error messages
    upload_error = request.query_params.get("upload_error")
    delete_error = request.query_params.get("error")


    total_files = len(own_files)


    return templates.TemplateResponse(
        "upload.html",
        {
            "request": request,
            "user": username,
            "folders": sorted_folders,
            "folder_names": folder_names,
            "files_with_shares": files_with_shares,
            "shared_files": shared_files,
            "all_users": all_users,
            "total_files": total_files,
            "actual_storage_used": actual_storage_used,
            "original_total_size": original_total_size,
            "total_savings_bytes": total_savings_bytes,
            "savings_percentage": savings_percentage,
            "delete_error": delete_error,
            "upload_error": upload_error,
            "storage_quota_mb": storage_quota_mb,
            "storage_used_mb": storage_used_mb,
            "storage_percent": storage_percent
        }
    )




# ---------------- UPLOAD FILE (MULTIPLE FILES SUPPORT) ----------------
@app.post("/upload")
def upload_file(request: Request, files: List[UploadFile] = FastFile(...), folder: str = Form(None)):
    username = request.cookies.get("user")
    if not username:
        return RedirectResponse("/login")


    db: Session = get_db()


    # Rate limiting check
    if not check_rate_limit(username, "upload", db):
        return RedirectResponse("/upload?upload_error=rate_limit", status_code=302)


    uploaded_count = 0
    skipped_count = 0
   
    for file in files:
        content = file.file.read()
        size = len(content)
        file_hash = hashlib.sha256(content).hexdigest()
        blob_path = os.path.join(UPLOAD_DIR, file_hash)


        # Check if user already uploaded this file
        user_has_uploaded_before = db.query(models.File).filter_by(
            uploader=username,
            file_hash=file_hash
        ).first() is not None


        # Only count against quota if it's NOT a duplicate for this user
        if not user_has_uploaded_before:
            # Check storage quota
            quota_ok, quota_error = check_storage_quota(username, size, db)
            if not quota_ok:
                # Skip this file if quota exceeded
                skipped_count += 1
                continue


        # Save blob if doesn't exist globally
        blob_exists_globally = os.path.exists(blob_path)
        if not blob_exists_globally:
            with open(blob_path, "wb") as f:
                f.write(content)


        folder_name = folder.strip() if folder else None


        record = models.File(
            filename=file.filename,
            uploader=username,
            size=size,
            file_hash=file_hash,
            is_duplicate=user_has_uploaded_before,
            folder=folder_name
        )
        db.add(record)


        # Update user's storage usage (only if not duplicate)
        if not user_has_uploaded_before:
            user = db.query(models.User).filter_by(username=username).first()
            user.storage_used += size


        uploaded_count += 1


    db.commit()


    # Show appropriate message
    if skipped_count > 0:
        return RedirectResponse(f"/upload?upload_error=quota&msg=Uploaded {uploaded_count} file(s). {skipped_count} file(s) skipped due to storage quota.", status_code=302)
   
    return RedirectResponse("/upload", status_code=302)




# ---------------- CREATE FOLDER ----------------
@app.post("/create-folder")
def create_folder(request: Request, folder_name: str = Form(...)):
    username = request.cookies.get("user")
    if not username:
        return RedirectResponse("/login")


    db: Session = get_db()


    # Rate limiting
    if not check_rate_limit(username, "create-folder", db):
        return RedirectResponse("/upload?upload_error=rate_limit", status_code=302)


    folder_name = folder_name.strip()


    if not folder_name or "/" in folder_name or "\\" in folder_name:
        return RedirectResponse("/upload", status_code=302)


    if db.query(models.Folder).filter_by(name=folder_name, owner=username).first():
        return RedirectResponse("/upload", status_code=302)


    db.add(models.Folder(name=folder_name, owner=username))
    db.commit()
    return RedirectResponse("/upload", status_code=302)




# ---------------- PRIVATE SHARE ----------------
@app.post("/share-with-user/{file_id}")
def share_with_user(file_id: int, request: Request, target_user: str = Form(...)):
    username = request.cookies.get("user")
    if not username:
        return RedirectResponse("/login")


    db: Session = get_db()


    # Rate limiting
    if not check_rate_limit(username, "share-with-user", db):
        return RedirectResponse("/upload?upload_error=rate_limit", status_code=302)


    file = db.query(models.File).filter_by(id=file_id, uploader=username).first()
    if not file:
        raise HTTPException(status_code=404)


    if not db.query(models.User).filter_by(username=target_user).first():
        return RedirectResponse("/upload", status_code=302)


    if db.query(models.SharedFile).filter_by(file_id=file_id, shared_with=target_user).first():
        return RedirectResponse("/upload", status_code=302)


    db.add(models.SharedFile(
        file_id=file_id,
        shared_by=username,
        shared_with=target_user
    ))
    db.commit()
    return RedirectResponse("/upload", status_code=302)




# ---------------- DOWNLOAD ----------------
@app.get("/download/{file_id}")
def download_file(file_id: int, request: Request):
    username = request.cookies.get("user")
    if not username:
        return RedirectResponse("/login")


    db: Session = get_db()
    file = db.query(models.File).filter_by(id=file_id).first()
    if not file:
        raise HTTPException(status_code=404)


    # Allow if owner or shared
    if file.uploader != username:
        shared = db.query(models.SharedFile).filter_by(file_id=file_id, shared_with=username).first()
        if not shared:
            raise HTTPException(status_code=403, detail="Access denied")


    blob_path = os.path.join(UPLOAD_DIR, file.file_hash)
    if not os.path.exists(blob_path):
        raise HTTPException(status_code=404)


    return FileResponse(blob_path, filename=file.filename)




# ---------------- DELETE FILE ----------------
@app.post("/delete/{file_id}")
def delete_file(file_id: int, request: Request):
    username = request.cookies.get("user")
    if not username:
        return RedirectResponse("/login")


    db: Session = get_db()


    # Rate limiting
    if not check_rate_limit(username, "delete", db):
        return RedirectResponse("/upload?upload_error=rate_limit", status_code=302)


    file = db.query(models.File).filter_by(id=file_id, uploader=username).first()
    if not file:
        raise HTTPException(status_code=404)


    # Check if original with duplicates
    if not file.is_duplicate:
        duplicate_count = db.query(models.File).filter_by(
            uploader=username,
            file_hash=file.file_hash,
            is_duplicate=True
        ).count()
       
        if duplicate_count > 0:
            return RedirectResponse("/upload?error=delete_duplicates_first", status_code=302)


    blob_path = os.path.join(UPLOAD_DIR, file.file_hash)


    # Update storage usage (only if not duplicate)
    if not file.is_duplicate:
        user = db.query(models.User).filter_by(username=username).first()
        user.storage_used -= file.size
        if user.storage_used < 0:
            user.storage_used = 0


    # Clean up shares
    db.query(models.Share).filter_by(file_id=file_id).delete()
    db.query(models.SharedFile).filter_by(file_id=file_id).delete()


    db.delete(file)
    db.commit()


    # Remove blob if no one has it
    if db.query(models.File).filter_by(file_hash=file.file_hash).count() == 0:
        if os.path.exists(blob_path):
            os.remove(blob_path)


    return RedirectResponse("/upload", status_code=302)




# ---------------- PUBLIC SHARE ----------------
@app.post("/share/{file_id}")
def create_share(file_id: int, request: Request):
    username = request.cookies.get("user")
    if not username:
        return RedirectResponse("/login")


    db: Session = get_db()


    # Rate limiting
    if not check_rate_limit(username, "share", db):
        return RedirectResponse("/upload?upload_error=rate_limit", status_code=302)


    file = db.query(models.File).filter_by(id=file_id, uploader=username).first()
    if not file:
        raise HTTPException(status_code=404)


    if db.query(models.Share).filter_by(file_id=file_id, is_active=True).first():
        return RedirectResponse("/upload", status_code=302)


    token = secrets.token_urlsafe(16)
    db.add(models.Share(
        file_id=file_id,
        share_token=token,
        created_by=username,
        is_active=True,
        download_count=0
    ))
    db.commit()
    return RedirectResponse("/upload", status_code=302)




@app.post("/unshare/{file_id}")
def revoke_share(file_id: int, request: Request):
    username = request.cookies.get("user")
    if not username:
        return RedirectResponse("/login")


    db: Session = get_db()
    file = db.query(models.File).filter_by(id=file_id, uploader=username).first()
    if not file:
        raise HTTPException(status_code=404)


    db.query(models.Share).filter_by(file_id=file_id).update({"is_active": False})
    db.commit()
    return RedirectResponse("/upload", status_code=302)




# ---------------- PUBLIC SHARE PAGE ----------------
@app.get("/s/{share_token}", response_class=HTMLResponse)
def public_share_page(share_token: str, request: Request):
    db: Session = get_db()
    share = db.query(models.Share).filter_by(share_token=share_token, is_active=True).first()
    if not share:
        raise HTTPException(status_code=404)
    file = db.query(models.File).filter_by(id=share.file_id).first()
    if not file:
        raise HTTPException(status_code=404)


    return templates.TemplateResponse("share.html", {
        "request": request,
        "file": file,
        "share_token": share_token,
        "shared_by": share.created_by,
        "download_count": share.download_count
    })




@app.get("/s/{share_token}/download")
def public_download(share_token: str):
    db: Session = get_db()
    share = db.query(models.Share).filter_by(share_token=share_token, is_active=True).first()
    if not share:
        raise HTTPException(status_code=404)
    file = db.query(models.File).filter_by(id=share.file_id).first()
    if not file:
        raise HTTPException(status_code=404)


    blob_path = os.path.join(UPLOAD_DIR, file.file_hash)
    if not os.path.exists(blob_path):
        raise HTTPException(status_code=404)


    share.download_count += 1
    db.commit()


    return FileResponse(blob_path, filename=file.filename)
