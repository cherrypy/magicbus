"""A library of helper functions for the magicbus test suite."""

import os
thisdir = os.path.abspath(os.path.dirname(__file__))

import sys
import time

from magicbus._compat import basestring, ntob

# --------------------------- Spawning helpers --------------------------- #


class Process(object):
    
    pid_file = os.path.join(thisdir, 'test.pid')
    config_file = os.path.join(thisdir, 'test.conf')
    
    def __init__(self, wait=False, daemonize=False, ssl=False, socket_host=None, socket_port=None):
        self.wait = wait
        self.daemonize = daemonize
        self.ssl = ssl
        self.host = socket_host or cherrypy.server.socket_host
        self.port = socket_port or cherrypy.server.socket_port
    
    def start(self, imports=None):
        """Start the subprocess."""
        servers.wait_for_free_port(self.host, self.port)
        
        args = [sys.executable, os.path.join(thisdir, '..', 'cherryd'),
                '-c', self.config_file, '-p', self.pid_file]
        
        if not isinstance(imports, (list, tuple)):
            imports = [imports]
        for i in imports:
            if i:
                args.append('-i')
                args.append(i)
        
        if self.daemonize:
            args.append('-d')

        env = os.environ.copy()
        # Make sure we import the cherrypy package in which this module is defined.
        grandparentdir = os.path.abspath(os.path.join(thisdir, '..', '..'))
        if env.get('PYTHONPATH', ''):
            env['PYTHONPATH'] = os.pathsep.join((grandparentdir, env['PYTHONPATH']))
        else:
            env['PYTHONPATH'] = grandparentdir
        if self.wait:
            self.exit_code = os.spawnve(os.P_WAIT, sys.executable, args, env)
        else:
            os.spawnve(os.P_NOWAIT, sys.executable, args, env)
            servers.wait_for_occupied_port(self.host, self.port)
        
        # Give the engine a wee bit more time to finish STARTING
        if self.daemonize:
            time.sleep(2)
        else:
            time.sleep(1)
    
    def get_pid(self):
        return int(open(self.pid_file, 'rb').read())
    
    def join(self):
        """Wait for the process to exit."""
        try:
            try:
                # Mac, UNIX
                os.wait()
            except AttributeError:
                # Windows
                try:
                    pid = self.get_pid()
                except IOError:
                    # Assume the subprocess deleted the pidfile on shutdown.
                    pass
                else:
                    os.waitpid(pid, 0)
        except OSError:
            x = sys.exc_info()[1]
            if x.args != (10, 'No child processes'):
                raise

