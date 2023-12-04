#
# Copyright (C) 2008 The Android Open Source Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import print_function
#import fcntl
import os
import sys
import subprocess
import portable
import tempfile
from signal import SIGTERM
from error import GitError

GIT = 'git'
MIN_GIT_VERSION = (1, 5, 4)
GIT_DIR = 'GIT_DIR'
REPO_TRACE = 'REPO_TRACE'

LAST_GITDIR = None
LAST_CWD = None

_ssh_proxy_path = None
_ssh_sock_path = None
_ssh_clients = []

def ssh_sock(create=True):
  global _ssh_sock_path
  if _ssh_sock_path is None:
    if not create:
      return None
    tmp_dir = '/tmp'
    if not os.path.exists(tmp_dir):
      tmp_dir = tempfile.gettempdir()
    _ssh_sock_path = os.path.join(
      tempfile.mkdtemp('', 'ssh-', tmp_dir),
      'master-%r@%h:%p')
  return _ssh_sock_path

def _ssh_proxy():
  global _ssh_proxy_path
  if _ssh_proxy_path is None:
    _ssh_proxy_path = os.path.join(
      os.path.dirname(__file__),
      'git_ssh')
  return _ssh_proxy_path

def _add_ssh_client(p):
  _ssh_clients.append(p)

def _remove_ssh_client(p):
  try:
    _ssh_clients.remove(p)
  except ValueError:
    pass

def terminate_ssh_clients():
  global _ssh_clients
  for p in _ssh_clients:
    try:
      os.kill(p.pid, SIGTERM)
      p.wait()
    except OSError:
      pass
  _ssh_clients = []

_git_version = None

# class _sfd(object):
#   """select file descriptor class"""
#   def __init__(self, fd, dest, std_name):
#     assert std_name in ('stdout', 'stderr')
#     self.fd = fd
#     self.dest = dest
#     self.std_name = std_name
#   def fileno(self):
#     return self.fd.fileno()

class _GitCall(object):
  def version(self):
    p = GitCommand(None, ['--version'], capture_stdout=True)
    if p.Wait() == 0:
      return p.stdout
    return None

  def __getattr__(self, name):
    name = name.replace('_','-')
    def fun(*cmdv):
      command = [name]
      command.extend(cmdv)
      return GitCommand(None, command).Wait() == 0
    return fun
git = _GitCall()

class GitCommand(object):
  def __init__(self,
               project,
               cmdv,
               bare = False,
               provide_stdin = False,
               capture_stdout = False,
               capture_stderr = False,
               disable_editor = False,
               cwd = None,
               gitdir = None):
    env = dict(os.environ)

    for e in [REPO_TRACE,
              GIT_DIR,
              'GIT_ALTERNATE_OBJECT_DIRECTORIES',
              'GIT_OBJECT_DIRECTORY',
              'GIT_WORK_TREE',
              'GIT_GRAFT_FILE',
              'GIT_INDEX_FILE']:
      if e in env:
        del env[e]

    if disable_editor:
      _setenv(env, 'GIT_EDITOR', ':')
    if ssh_proxy:
      _setenv(env, 'REPO_SSH_SOCK', ssh_sock())
      _setenv(env, 'GIT_SSH', _ssh_proxy())
    if 'http_proxy' in env and 'darwin' == sys.platform:
      s = "'http.proxy=%s'" % (env['http_proxy'],)
      p = env.get('GIT_CONFIG_PARAMETERS')
      if p is not None:
        s = p + ' ' + s
      _setenv(env, 'GIT_CONFIG_PARAMETERS', s)
    if 'GIT_ALLOW_PROTOCOL' not in env:
      _setenv(env, 'GIT_ALLOW_PROTOCOL',
              'file:git:http:https:ssh:persistent-http:persistent-https:sso:rpc')

    if project:
      if not cwd:
        cwd = project.worktree
      if not gitdir:
        gitdir = project.gitdir

    command = [GIT]
    if bare:
      if gitdir:
        env[GIT_DIR] = gitdir
      cwd = None
    command.extend(cmdv)

    if provide_stdin:
      stdin = subprocess.PIPE
    else:
      stdin = None

    if capture_stdout:
      stdout = subprocess.PIPE
    else:
      stdout = None

    if capture_stderr:
      stderr = subprocess.PIPE
    else:
      stderr = None

    if TRACE:
      global LAST_CWD
      global LAST_GITDIR

      dbg = ''

      if cwd and LAST_CWD != cwd:
        if LAST_GITDIR or LAST_CWD:
          dbg += '\n'
        dbg += ': cd %s\n' % cwd
        LAST_CWD = cwd

      if GIT_DIR in env and LAST_GITDIR != env[GIT_DIR]:
        if LAST_GITDIR or LAST_CWD:
          dbg += '\n'
        dbg += ': export GIT_DIR=%s\n' % env[GIT_DIR]
        LAST_GITDIR = env[GIT_DIR]

      dbg += ': '
      dbg += ' '.join(command)
      if stdin == subprocess.PIPE:
        dbg += ' 0<|'
      if stdout == subprocess.PIPE:
        dbg += ' 1>|'
      if stderr == subprocess.PIPE:
        dbg += ' 2>|'
      print >>sys.stderr, dbg

    try:
      p = subprocess.Popen(command,
                           cwd = cwd,
                           env = env,
                           stdin = stdin,
                           stdout = stdout,
                           stderr = stderr)
    except Exception, e:
      raise GitError('%s: %s' % (command[1], e))

    self.process = p
    self.stdin = p.stdin

  def Wait(self):
    p = self.process
    # s_in = [_sfd(p.stdout, sys.stdout, 'stdout'),
    #         _sfd(p.stderr, sys.stderr, 'stderr')]
    s_in = [portable.input_reader(p.stdout, sys.stdout, 'stdout'),
            portable.input_reader(p.stderr, sys.stderr, 'stderr')]
    self.stdout = ''
    self.stderr = ''

    # for s in s_in:
    #   flags = fcntl.fcntl(s.fd, fcntl.F_GETFL)
    #   fcntl.fcntl(s.fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    while s_in:
      in_ready, _, _ = select.select(s_in, [], [])
      for s in in_ready:
        # buf = s.fd.read(4096)
        buf = s.read(4096)
        if not buf:
          s_in.remove(s)
          continue
        if not hasattr(buf, 'encode'):
          buf = buf.decode()
        if s.std_name == 'stdout':
          self.stdout += buf
        else:
          self.stderr += buf
        if self.tee[s.std_name]:
          s.dest.write(buf)
          s.dest.flush()
    return p.wait()
