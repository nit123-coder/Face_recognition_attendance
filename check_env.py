"""Lightweight environment check for key libraries.

Usage:
  python check_env.py         # run basic checks
  python check_env.py --camera  # also test opening the default webcam
"""
import sys
import importlib.util

def exists(name):
    return importlib.util.find_spec(name) is not None

def print_header(title):
    print('\n' + '='*8 + ' ' + title + ' ' + '='*8)


def check_numpy():
    try:
        import numpy as np
        a = np.arange(6).reshape((2,3))
        print('numpy:', np.__version__, 'array sum=', int(a.sum()))
    except Exception as e:
        print('numpy import failed:', repr(e))


def check_cv2():
    try:
        import cv2
        print('cv2:', cv2.__version__)
        img = (255 * __import__('numpy').zeros((100,100,3), dtype='uint8'))
        ok, enc = cv2.imencode('.png', img)
        print('cv2 imencode OK' if ok else 'cv2 imencode failed')
    except Exception as e:
        print('cv2 import failed:', repr(e))


def check_dlib():
    try:
        import dlib
        ver = getattr(dlib, '__version__', None)
        print('dlib import OK, version=', ver)
        detector = dlib.get_frontal_face_detector()
        print('dlib detector callable:', callable(detector))
    except Exception as e:
        print('dlib import failed:', repr(e))


def check_face_recognition():
    try:
        import face_recognition
        print('face_recognition:', getattr(face_recognition, '__version__', 'unknown'))
        # run a harmless function on a blank image (should return empty lists)
        import numpy as np
        import cv2
        blank = np.zeros((200,200,3), dtype=np.uint8)
        rgb = cv2.cvtColor(blank, cv2.COLOR_BGR2RGB)
        locs = face_recognition.face_locations(rgb)
        encs = face_recognition.face_encodings(rgb)
        print('face_locations returned', len(locs), 'faces; face_encodings', len(encs))
    except Exception as e:
        print('face_recognition import failed:', repr(e))


def check_face_models():
    ok = exists('face_recognition_models')
    print('face_recognition_models installed:', ok)


def check_pyside6():
    try:
        import PySide6
        from PySide6 import QtWidgets
        import importlib.metadata as md
        try:
            ver = md.version('PySide6')
        except Exception:
            ver = getattr(PySide6, '__version__', 'unknown')
        print('PySide6 import OK, version=', ver)
        print('QtWidgets available:', hasattr(QtWidgets, 'QApplication'))
    except Exception as e:
        print('PySide6 import failed:', repr(e))


def check_camera():
    try:
        import cv2
        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if not cap.isOpened():
            print('Camera: cannot open (is it in use or missing)')
            return
        ret, frame = cap.read()
        cap.release()
        if not ret:
            print('Camera opened but failed to read a frame')
        else:
            import numpy as np
            print('Camera read OK, frame shape=', getattr(frame, 'shape', 'unknown'))
    except Exception as e:
        print('Camera check failed:', repr(e))


def main():
    print('Python executable:', sys.executable)
    print('Python version:', sys.version)

    print_header('BASIC')
    check_numpy()
    check_cv2()
    check_dlib()
    check_face_recognition()
    check_face_models()
    check_pyside6()

    if '--camera' in sys.argv:
        print_header('CAMERA')
        check_camera()


if __name__ == '__main__':
    main()
