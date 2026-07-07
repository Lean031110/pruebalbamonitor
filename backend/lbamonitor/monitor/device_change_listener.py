"""DeviceChangeListener — WM_DEVICECHANGE con ventana oculta (como MIRON)."""
from __future__ import annotations
import ctypes, ctypes.wintypes, threading, time
from typing import Callable, Optional
from lbamonitor.utils.logging_setup import get_logger
log = get_logger(__name__)
WM_DEVICECHANGE = 0x0219; DBT_DEVICEARRIVAL = 0x8000; DBT_DEVICEREMOVECOMPLETE = 0x8004
DBT_DEVTYP_VOLUME = 0x00000002

class DEV_BROADCAST_HDR(ctypes.Structure):
    _fields_ = [("dbch_size",ctypes.wintypes.DWORD),("dbch_devicetype",ctypes.wintypes.DWORD),("dbch_reserved",ctypes.wintypes.DWORD)]

class DEV_BROADCAST_VOLUME(ctypes.Structure):
    _fields_ = [("dbcv_size",ctypes.wintypes.DWORD),("dbcv_devicetype",ctypes.wintypes.DWORD),("dbcv_reserved",ctypes.wintypes.DWORD),("dbcv_unitmask",ctypes.wintypes.DWORD),("dbcv_flags",ctypes.wintypes.WORD)]

class DeviceChangeListener:
    def __init__(self, on_inserted: Callable[[str],None], on_removed: Callable[[str],None]) -> None:
        self.on_inserted=on_inserted; self.on_removed=on_removed
        self.hwnd=None; self._running=False; self._thread=None
        self._wnd_class_name="LBAMonitorDeviceListener"
    def _is_windows(self)->bool:
        import os; return os.name=="nt"
    def _wnd_proc(self,hwnd,msg,wparam,lparam)->int:
        if msg==WM_DEVICECHANGE:
            if wparam in (DBT_DEVICEARRIVAL,DBT_DEVICEREMOVECOMPLETE):
                drives=self._get_drive_letters(lparam)
                if drives:
                    action="insertada" if wparam==DBT_DEVICEARRIVAL else "extraída"
                    for d in drives:
                        log.info(f"WM_DEVICECHANGE: USB {action}: {d}")
                        try:
                            if wparam==DBT_DEVICEARRIVAL: self.on_inserted(d)
                            else: self.on_removed(d)
                        except Exception as e: log.exception(f"Error en callback: {e}")
        try:
            import win32gui; return win32gui.DefWindowProc(hwnd,msg,wparam,lparam)
        except Exception: return 0
    def _get_drive_letters(self,lparam)->list[str]:
        try:
            hdr=ctypes.cast(lparam,ctypes.POINTER(DEV_BROADCAST_HDR)).contents
            if hdr.dbch_devicetype!=DBT_DEVTYP_VOLUME: return []
            dbv=ctypes.cast(lparam,ctypes.POINTER(DEV_BROADCAST_VOLUME)).contents
            drives=[]
            for i in range(26):
                if dbv.dbcv_unitmask&(1<<i):
                    d=chr(65+i)+":"
                    if self._is_removable_drive(d): drives.append(d)
                    else: log.debug(f"Unidad {d} ignorada (no removible)")
            return drives
        except Exception as e:
            log.debug(f"Error parseando: {e}"); return []
    def _is_removable_drive(self,drive_letter)->bool:
        try:
            import win32api,win32con
            dt=win32api.GetDriveType(drive_letter+"\\")
            return dt in (win32con.DRIVE_REMOVABLE,win32con.DRIVE_FIXED)
        except Exception: return True
    def start(self)->bool:
        if not self._is_windows(): return False
        if self._running: return True
        try:
            import win32gui
        except ImportError: return False
        self._running=True; self._thread=threading.Thread(target=self._run,name="DeviceChangeListener",daemon=True); self._thread.start()
        log.info("DeviceChangeListener arrancado (WM_DEVICECHANGE)"); return True
    def _run(self):
        import win32gui,win32api
        try:
            wc=win32gui.WNDCLASS(); wc.lpfnWndProc=self._wnd_proc; wc.lpszClassName=self._wnd_class_name
            wc.hInstance=win32api.GetModuleHandle(None)
            try: class_atom=win32gui.RegisterClass(wc)
            except Exception: class_atom=win32gui.FindWindow(self._wnd_class_name,None)
            self.hwnd=win32gui.CreateWindow(class_atom,"LBAMonitor",0,0,0,0,0,0,0,wc.hInstance,None)
            log.info(f"Ventana oculta creada (hwnd={self.hwnd})")
            while self._running:
                win32gui.PumpWaitingMessages(); time.sleep(0.05)
            if self.hwnd:
                try: win32gui.DestroyWindow(self.hwnd)
                except Exception: pass
            try: win32gui.UnregisterClass(self._wnd_class_name,wc.hInstance)
            except Exception: pass
        except Exception as e: log.exception(f"Error fatal: {e}")
        finally: self._running=False; log.info("DeviceChangeListener detenido")
    def stop(self):
        self._running=False
        if self.hwnd:
            try:
                import win32gui,win32con; win32gui.PostMessage(self.hwnd,win32con.WM_CLOSE,0,0)
            except Exception: pass
        if self._thread and self._thread.is_alive(): self._thread.join(timeout=2.0)
        self._thread=None
