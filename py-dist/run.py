# An example of embedding CEF browser in a PyQt4 application.
# Tested with PyQt 4.10.3 (Qt 4.8.5).
import re, os, sys, platform, traceback, time, codecs 
import subprocess,time,socket
import json
import compileall
from distutils import util

from PyQt5 import QtGui
from PyQt5 import QtCore
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *

from cefpython3 import cefpython

proc = None

class Info:
    initial_width = 800
    initial_height = 600
    max_width = 0
    max_height = 0

    window_title = "Test App"
    icon_name = "icon.png"
    splashscreen_img = "splashscreen.png"
    fullscreen_allowed = True

    project_dir_name = "app"
    project_dir_path = "../app/"
    dev_tools_menu_enabled = True

    def copy_properties(self, target_object):
        import inspect
        for name,value in inspect.getmembers(target_object):
            if (name.startswith('__') and name.endswith('__')):
                continue
            setattr(self, name, value)

    def process_configuration(self):
        config_file_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'config', 'config.json'))
        try:
            with open(config_file_path) as data_file:
                from types import SimpleNamespace as Namespace
                data = json.load(data_file, object_hook=lambda d: Namespace(**d))

                self.splashscreen_img = data.splashscreen_img

                self.copy_properties(data.application)
                self.copy_properties(data.window)
                self.copy_properties(data.database)

                # Do some fixup for some of the settings
                self.icon_name = os.path.abspath(os.path.join(os.path.dirname( __file__ ), '..', 'config', data.icon))
                self.project_dir_path = os.path.abspath(os.path.join(os.path.dirname( __file__ ), '..', self.project_dir_name))
        except Exception as e:
            print (e)
            print ("Failed Reading Config")

    def check_if_migration_performed(self):
        if os.path.exists('migrate.py'):
            from migrate import Database
            db = Database()
            db.makeMigrationsAndmigrate()
            os.remove('migrate.py')

def GetApplicationPath(file=None):
    # import re, os, platform
    # On Windows after downloading file and calling Browser.GoForward(),
    # current working directory is set to %UserProfile%.
    # Calling os.path.dirname(os.path.realpath(__file__))
    # returns for eg. "C:\Users\user\Downloads". A solution
    # is to cache path on first call.
    if not hasattr(GetApplicationPath, "dir"):
        if hasattr(sys, "frozen"):
            dir = os.path.dirname(sys.executable)
        elif "__file__" in globals():
            dir = os.path.dirname(os.path.realpath(__file__))
        else:
            dir = os.getcwd()
        GetApplicationPath.dir = dir
    # If file is None return current directory without trailing slash.
    if file is None:
        file = ""
    # Only when relative path.
    if not file.startswith("/") and not file.startswith("\\") and (
            not re.search(r"^[\w-]+:", file)):
        path = GetApplicationPath.dir + os.sep + file
        if platform.system() == "Windows":
            path = re.sub(r"[/\\]+", re.escape(os.sep), path)
        path = re.sub(r"[/\\]+$", "", path)
        return path
    return str(file)

def ExceptHook(excType, excValue, traceObject):
    # import traceback, os, time, codecs
    # This hook does the following: in case of exception write it to
    # the "error.log" file, display it to the console, shutdown CEF
    # and exit application immediately by ignoring "finally" (os._exit()).
    errorMsg = "\n".join(traceback.format_exception(excType, excValue,
            traceObject))
    errorFile = GetApplicationPath("error.log")
    try:
        appEncoding = cefpython.g_applicationSettings["string_encoding"]
    except:
        appEncoding = "utf-8"
    if type(errorMsg) == bytes:
        errorMsg = errorMsg.decode(encoding=appEncoding, errors="replace")
    try:
        with codecs.open(errorFile, mode="a", encoding=appEncoding) as fp:
            fp.write("\n[%s] %s\n" % (
                    time.strftime("%Y-%m-%d %H:%M:%S"), errorMsg))
    except:
        print("[run.py] WARNING: failed writing to error file: %s" % (
                errorFile))
    # Convert error message to ascii before printing, otherwise
    # you may get error like this:
    # | UnicodeEncodeError: 'charmap' codec can't encode characters
    errorMsg = errorMsg.encode("ascii", errors="replace")
    errorMsg = errorMsg.decode("ascii", errors="replace")
    print("\n"+errorMsg+"\n")
    cefpython.QuitMessageLoop()
    cefpython.Shutdown()
    os._exit(1)

class MainWindow(QMainWindow):
    mainFrame = None

    def __init__(self):
        super(MainWindow, self).__init__(None)

        info = Info()
        info.process_configuration()
        self.mainFrame = MainFrame(self)
        self.setCentralWidget(self.mainFrame)
        self.setMinimumSize(info.min_width,info.min_height)

        if info.fullscreen_allowed == False and info.max_height != 0 and info.max_width != 0: 
            self.setMaximumSize(info.max_width,info.max_height)

        self.resize(info.initial_width, info.initial_height)
        self.setWindowTitle(info.window_title)
        self.setWindowIcon(QtGui.QIcon(info.icon_name))
        self.setFocusPolicy(QtCore.Qt.StrongFocus)

    def createMenu(self):
        menubar = self.menuBar()
        filemenu = menubar.addMenu("&File")
        filemenu.addAction(QtGui.QAction("Open", self))
        filemenu.addAction(QtGui.QAction("Exit", self))
        aboutmenu = menubar.addMenu("&About")

    def forceResize(self):
        self.mainFrame.resizeEvent(None)

    def focusInEvent(self, event):
        cefpython.WindowUtils.OnSetFocus(int(self.centralWidget().winId()), 0, 0, 0)

    def closeEvent(self, event):
        subprocess.call(['taskkill', '/F', '/T', '/PID', str(proc.pid)])
        self.mainFrame.browser.CloseBrowser()

class MainFrame(QWidget):
    browser = None

    def __init__(self, parent=None):
        super(MainFrame, self).__init__(parent)
        windowInfo = cefpython.WindowInfo()
        windowInfo.SetAsChild(int(self.winId()))    
        attempt_count = 0
        while True:
            attempt_count += 1
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.01)
            result = sock.connect_ex(('127.0.0.1', info.target_port))
            sock.close()
            if result == 0:
                break
            if attempt_count >= info.connect_attempt_limit:
                raise Exception('Failure while attempting to connect to Django server: attempts exceeded limit ({})'.format(attempt_count))
            time.sleep(0.01)

        print("MainFrame connection loop took " + str(attempt_count) + " attempts")

        self.browser = cefpython.CreateBrowserSync(
            windowInfo,
            browserSettings={},
            navigateUrl=GetApplicationPath("http://127.0.0.1:" + str(info.target_port)))
        self.show()

    def moveEvent(self, event):
        cefpython.WindowUtils.OnSize(int(self.winId()), 0, 0, 0)

    def resizeEvent(self, event):
        cefpython.WindowUtils.OnSize(int(self.winId()), 0, 0, 0)

class CefApplication(QApplication):
    timer = None

    def __init__(self, args):
        super(CefApplication, self).__init__(args)
        self.createTimer()

    def createTimer(self):
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.onTimer)
        self.timer.start(10)

    def onTimer(self):
        # The proper way of doing message loop should be:
        # 1. In createTimer() call self.timer.start(0)
        # 2. In onTimer() call MessageLoopWork() only when
        #    QtGui.QApplication.instance()->hasPendingEvents() returns False.
        # But... there is a bug in Qt, hasPendingEvents() returns always true.
        cefpython.MessageLoopWork()

    def stopTimer(self):
        # Stop the timer after Qt message loop ended, calls to MessageLoopWork()
        # should not happen anymore.
        self.timer.stop()

info = Info()

if __name__ == '__main__':
    appscreen = QApplication(sys.argv)
    info.process_configuration()

    if info.display_splashscreen:
        # Create and display the splash screen
        splash_pix = QPixmap(os.path.abspath(os.path.join(os.path.dirname( __file__ ), '..', 'img', info.splashscreen_img)))

        splash = QSplashScreen(splash_pix, Qt.WindowStaysOnTopHint)
        splash.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        splash.setEnabled(False)

        # adding progress bar
        progressBar = QProgressBar(splash)
        progressBar.setMaximum(10)
        progressBar.setGeometry(0, splash_pix.height() - 50, splash_pix.width(), 20)
        progressBar.setStyleSheet ("QProgressBar {border: 2px solid beige;border-radius: 5px;margin-left: 14ex;margin-right: 14ex;text-align: center;} QProgressBar::chunk {background-color: #0A2F3D;width: 20px;margin: 0.5px;}")

        splash.show()
        splash.showMessage("<h1><font color='white'>Configuring the server, Please wait ....</font></h1>", Qt.AlignTop | Qt.AlignCenter, Qt.black)

    if info.attempt_migration:
        for i in range(1, 11):
            if info.display_splashscreen:
                progressBar.setValue(i)
            t = time.time()
            while time.time() < t + 0.1:
                appscreen.processEvents()
                info.check_if_migration_performed()

    # This isn't ideal, but it catches running from debugger vs launchapp.bat
    base_path = '.\\'
    cwd = os.getcwd()
    file_path = os.path.dirname(os.path.abspath(__file__))
    if (cwd == file_path):
        base_path = '..\\'

    proc = subprocess.Popen(['python', base_path + info.project_dir_name + '\manage.py', 'runserver', '127.0.0.1:' + str(info.target_port)])
    print("[pyqt.py] PyQt version: %s" % QtCore.PYQT_VERSION_STR)
    print("[pyqt.py] QtCore version: %s" % QtCore.qVersion())

    # Intercept python exceptions. Exit app immediately when exception
    # happens on any of the threads.
    sys.excepthook = ExceptHook

    # Application settings
    settings = {
        # "cache_path": "webcache/", # Disk cache
        "debug": True, # cefpython debug messages in console and in log_file
        "log_severity": cefpython.LOGSEVERITY_INFO, # LOGSEVERITY_VERBOSE
        "log_file": GetApplicationPath("debug.log"), # Set to "" to disable.
        "release_dcheck_enabled": True, # Enable only when debugging.
        # This directories must be set on Linux
        "locales_dir_path": cefpython.GetModuleDirectory()+"/locales",
        "resources_dir_path": cefpython.GetModuleDirectory(),
        "browser_subprocess_path": "%s/%s" % (
            cefpython.GetModuleDirectory(), "subprocess"),
        "context_menu":{
            "enabled" : info.dev_tools_menu_enabled
        },
    }

    # Command line switches set programmatically
    switches = {
        # "proxy-server": "socks5://127.0.0.1:8888",
        # "enable-media-stream": "",
        # "--invalid-switch": "" -> Invalid switch name
    }

    cefpython.Initialize(settings, switches)
    app = CefApplication(sys.argv)
    mainWindow = MainWindow()

    if info.display_splashscreen:
        splash.close()

    mainWindow.show()
    mainWindow.forceResize()

    app.exec_()
    app.stopTimer()

    # Need to destroy QApplication(), otherwise Shutdown() fails.
    # Unset main window also just to be safe.
    del mainWindow
    del app
    cefpython.Shutdown()

    proc.kill()
    os._exit(1)
