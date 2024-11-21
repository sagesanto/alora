import os
import time
import servicemanager
import win32serviceutil
import win32service
import win32event
import win32api
import logging
import subprocess

class AloraWatchdog(win32serviceutil.ServiceFramework):
    _svc_name_ = "AloraWatchdog"
    _svc_display_name_ = "Alora Watchdog Service"
    _svc_description_ = "Watch for internet to drop out and, if it does, shut down the observatory"

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        self.is_running = True
        logpath = r'C:\Users\observatory\alora\alora\observatory\watchdog.log'
        if not os.path.exists(logpath):
            with open(logpath,"w+") as f:
                pass
        logging.basicConfig(
            filename=logpath,
            level=logging.DEBUG,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.venv_path = r"C:\Users\observatory\alora\.venv"
        self.python_exe = os.path.join(self.venv_path, 'Scripts', 'python.exe')  
        self.script_path = r"C:\Users\observatory\alora\alora\observatory\watchdog.py"

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.hWaitStop)
        self.is_running = False

    def SvcDoRun(self):
        servicemanager.LogMsg(servicemanager.EVENTLOG_INFORMATION_TYPE,
                              servicemanager.PYS_SERVICE_STARTED,
                              (self._svc_name_, ''))

        env = os.environ.copy()
        env["PATH"] = os.path.join(self.venv_path, "Scripts") + ";" + env["PATH"]
        env["PYTHONHOME"] = self.venv_path
        env["PYTHONPATH"] = os.path.join(self.venv_path, "Lib") 

        try:
            logging.info("Running...")
            subprocess.run([self.python_exe, self.script_path], env=env, check=True)

        except Exception as e:
            logging.info(f"Got error {e}")
            self.SvcStop()

if __name__ == '__main__':
    win32serviceutil.HandleCommandLine(AloraWatchdog)
