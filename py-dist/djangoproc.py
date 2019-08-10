import subprocess
import threading
import signal
import time
import os

def dbg_print(msg):
    print('[django]: {0}'.format(msg))

class DjangoProcess:
    subproc = None
    subproc_thread = None
    complete = False
    should_kill = False
    is_crashed = False

    def begin(self, django_path, target_port, app_settings):
        dbg_print('begin startup (targeting ' + django_path + ')')

        def run_in_thread():
            self.subproc = subprocess.Popen(['python', django_path + '\manage.py', 'runserver', '127.0.0.1:' + str(target_port)], cwd=django_path)
            dbg_print('process started: ' + str(self.subproc))

            while True:
                if self.should_kill:
                    dbg_print('sending kill signal')
                    # this is apparently the only way to do it without an error... :'(
                    subprocess.call(['taskkill', '/F', '/T', '/PID', str(self.subproc.pid)])
                    self.subproc.wait()
                    dbg_print('process terminated')
                    break
                time.sleep(0.5)
                if not (self.subproc.poll() is None):
                    dbg_print("process heartbeat - FAILED")
                    self.complete = True
                    self.is_crashed = True
                    break
                else:
                    if app_settings.debug_settings.print_django_heartbeat:
                        dbg_print("process heartbeat - success")

        self.subproc_thread = threading.Thread(target=run_in_thread)
        self.subproc_thread.start()
        dbg_print('thread launched')

    def kill_now(self):
        self.should_kill = True
        if not (self.subproc_thread is None):
            self.subproc_thread.join()
            self.subproc_thread = None
        self.complete = True

    def is_alive(self):
        return not self.complete and not self.is_crashed
