# Face-Recognition Attendance System 

A lightweight desktop application designed to scan faces via a local camera or IP webcam and automatically log attendance. Built with Python, OpenCV, and PySide6.

---

## Table of Contents

* [Overview]
* [Requirements]
* [Quick Start & Installation]
* [How to Run the App]
* [Project Structure]
* [Data & Storage]
* [Configuration]
* [Troubleshooting]

---

##  Overview

This project utilizes OpenCV and the `face_recognition` library to detect and identify faces in a live video stream.

### Key Features

* **PySide6 GUI:** Intuitive interface to start/stop scanners and review logs.
* **Flexible Input:** Supports both local hardware webcams and IP webcam network streams.
* **Admin Dashboard:** Simplified user registration and face database management.

---

##  Requirements

* **Python:** Version 3.10 or higher recommended.
* **Core Dependencies:** 
OpenCV, `face_recognition`, `dlib`, PySide6, and `requests`.

> 💡 **Note on Models:** 
`face_recognition` uses HOG-based detection by default (lightweight, no extra files). Switching to `model='cnn'` offers higher accuracy but requires downloading dlib model files and increases CPU/GPU overhead.

---

##  Quick Start & Installation

Follow these steps to set up the project locally.

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/your-repo-name.git
cd your-repo-name

```

### 2. Set Up a Virtual Environment

```bash
# Create environment
python -m venv venv

# Activate environment (Windows PowerShell)
.\venv\Scripts\Activate.ps1

# Activate environment (Mac/Linux)
source venv/bin/activate

```

### 3. Install Dependencies

```bash
pip install -r requirements.txt

```

---

##  How to Run the App

1. Launch the application from your terminal:
```bash
python main.py

```


2. **Start Camera:** Use the **Start Camera Scanner** control to select your local webcam or input an IP webcam URL.
3. **Register Users:** Head to the **Admin Dashboard** to register new users and save their face images.

---

## 📂 Project Structure

```text
├── main.py                 # Application entry point
├── UI/                     # PySide6 GUI modules and custom widgets
├── known_faces/            # Folders of labeled face images used for recognition
│   └── <user_name>/        # Individual user image directories
├── dataset/                # Captured images
│   └── unknown/            # Temporarily saved unknown face captures
├── attendance_photos/      # Saved snapshot captures mapped to attendance events
├── attendance.db           # SQLite database storing attendance and user records
└── requirements.txt        # Python package dependencies

```

---

##  Data & Storage

* **Face Database:** Images for known users are stored as JPGs under `known_faces/<label>/`.
* **Logs & Metadata:** User records and historical attendance data are maintained in an SQLite database (`attendance.db`).

> ⚠️ **Warning:** 
Deleting or altering the `attendance.db` file or the `known_faces/` folder will permanently reset the application state.

---

##  Configuration

* **Camera Backends:** OpenCV automatically selects the best backend (`CAP_DSHOW` / `CAP_MSMF` on Windows).
* **IP Webcams:** Accepts standard MJPEG or RTSP network URLs. Use the built-in tester inside the **IP Webcam Dialog** to verify your stream link before deploying.

---

##  Troubleshooting

* **Camera not opening**
* **Root Cause:** Permissions or hardware conflict.
* **Solution:** Ensure no other app (e.g., Zoom, Teams) is using the camera. Check your operating system's privacy settings to make sure camera access is allowed for your terminal or Python.


* **Missing Dependencies**
* **Root Cause:** Uninstalled packages.
* **Solution:** Run `pip install -r requirements.txt` within your activated virtual environment to install all required libraries.


* **`dlib` / `face_recognition` install failure**
* **Root Cause:** Missing C++ compiler tools on your system.
* **Solution:** On **Windows**, download and install the Visual Studio Build Tools. Make sure to check the "Desktop development with C++" workload during installation. Alternatively, look for pre-built `.whl` files compatible with your Python version to bypass the compilation step.
