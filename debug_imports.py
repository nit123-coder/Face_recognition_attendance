import sys
print('sys.executable:', sys.executable)
print('sys.version:', sys.version)
print('\nsys.path:')
for p in sys.path:
    print(' ', p)
print('\nTrying imports...')
try:
    import PySide6
    print('PySide6 __file__:', getattr(PySide6, '__file__', 'built-in'))
except Exception as e:
    print('PySide6 import failed:', repr(e))
try:
    from PySide6.QtWidgets import QApplication, QWidget
    print('PySide6.QtWidgets import OK')
except Exception as e:
    print('PySide6.QtWidgets import failed:', repr(e))
try:
    import importlib.metadata as md
    print('PySide6 version:', md.version('PySide6'))
except Exception as e:
    print('Could not get PySide6 version via importlib.metadata:', repr(e))
