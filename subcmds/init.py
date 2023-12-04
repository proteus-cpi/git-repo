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

import os
import sys

from color import Coloring
from command import InteractiveCommand
from error import ManifestParseError
from remote import Remote
from git_command import git, MIN_GIT_VERSION

class Init(InteractiveCommand):
  common = True
  helpSummary = "Initialize repo in the current directory"
  helpUsage = """
%prog [options]
"""
  helpDescription = """
The '%prog' command is run once to install and initialize repo.
The latest repo source code and manifest collection is downloaded
from the server and is installed in the .repo/ directory in the
current working directory.

The optional -b argument can be used to select the manifest branch
to checkout and use.  If no branch is specified, master is assumed.

The optional -m argument can be used to specify an alternate manifest
to be used. If no manifest is specified, the manifest default.xml
will be used.

The --reference option can be used to point to a directory that
has the content of a --mirror sync. This will make the working
directory use as much data as possible from the local reference
directory when fetching from the server. This will make the sync
go a lot faster by reducing data traffic on the network.

The --no-clone-bundle option disables any attempt to use
$URL/clone.bundle to bootstrap a new Git repository from a
resumeable bundle file on a content delivery network. This
may be necessary if there are problems with the local Python
HTTP client or proxy configuration, but the Git binary works.

Switching Manifest Branches
---------------------------

To switch to another manifest branch, `repo init -b otherbranch`
may be used in an existing client.  However, as this only updates the
manifest, a subsequent `repo sync` (or `repo sync -d`) is necessary
to update the working directory files.
"""

  def _Options(self, p):
    # Logging
    g = p.add_option_group('Logging options')
    g.add_option('-q', '--quiet',
                 dest="quiet", action="store_true", default=False,
                 help="be quiet")

    # Manifest
    g = p.add_option_group('Manifest options')
    g.add_option('-u', '--manifest-url',
                 dest='manifest_url',
                 help='manifest repository location', metavar='URL')
    g.add_option('-b', '--manifest-branch',
                 dest='manifest_branch',
                 help='manifest branch or revision', metavar='REVISION')
    g.add_option('-m', '--manifest-name',
                 dest='manifest_name', default='default.xml',
                 help='initial manifest file', metavar='NAME.xml')
    g.add_option('--mirror',
                 dest='mirror', action='store_true',
                 help='create a replica of the remote repositories '
                      'rather than a client working directory')
    g.add_option('--reference',
                 dest='reference',
                 help='location of mirror directory', metavar='DIR')
    g.add_option('--depth', type='int', default=None,
                 dest='depth',
                 help='create a shallow clone with given depth; see git clone')
    g.add_option('--archive',
                 dest='archive', action='store_true',
                 help='checkout an archive instead of a git repository for '
                      'each project. See git archive.')
    g.add_option('-g', '--groups',
                 dest='groups', default='default',
                 help='restrict manifest projects to ones with specified '
                      'group(s) [default|all|G1,G2,G3|G4,-G5,-G6]',
                 metavar='GROUP')
    g.add_option('-p', '--platform',
                 dest='platform', default='auto',
                 help='restrict manifest projects to ones with a specified '
                      'platform group [auto|all|none|linux|darwin|...]',
                 metavar='PLATFORM')
    g.add_option('--no-clone-bundle',
                 dest='no_clone_bundle', action='store_true',
                 help='disable use of /clone.bundle on HTTP/HTTPS')

    # Tool
    g = p.add_option_group('Version options')
    g.add_option('--repo-url',
                 dest='repo_url',
                 help='repo repository location', metavar='URL')
    g.add_option('--repo-branch',
                 dest='repo_branch',
                 help='repo branch or revision', metavar='REVISION')
    g.add_option('--no-repo-verify',
                 dest='no_repo_verify', action='store_true',
                 help='do not verify repo source code')

  def _CheckGitVersion(self):
    ver_str = git.version()
    if not ver_str.startswith('git version '):
      print >>sys.stderr, 'error: "%s" unsupported' % ver_str
      sys.exit(1)

    ver_str = ver_str[len('git version '):].strip()
    ver_act = tuple(map(lambda x: int(x), ver_str.split('.')[0:3]))
    if ver_act < MIN_GIT_VERSION:
      need = '.'.join(map(lambda x: str(x), MIN_GIT_VERSION))
      print >>sys.stderr, 'fatal: git %s or later required' % need
      sys.exit(1)

  def _SyncManifest(self, opt):
    m = self.manifest.manifestProject

    if not m.Exists:
      if not opt.manifest_url:
        print >>sys.stderr, 'fatal: manifest url (-u) is required.'
        sys.exit(1)

      if not opt.quiet:
        print >>sys.stderr, 'Getting manifest ...'
        print >>sys.stderr, '   from %s' % opt.manifest_url
      m._InitGitDir()

      if opt.manifest_branch:
        m.revision = opt.manifest_branch
      else:
        m.revision = 'refs/heads/master'
    else:
      if opt.manifest_branch:
        m.revision = opt.manifest_branch
      else:
        m.PreSync()

    if opt.manifest_url:
      r = m.GetRemote(m.remote.name)
      r.url = opt.manifest_url
      r.ResetFetch()
      r.Save()

    groups = re.split(r'[,\s]+', opt.groups)
    all_platforms = ['linux', 'darwin', 'windows']
    platformize = lambda x: 'platform-' + x
    if opt.platform == 'auto':
      if (not opt.mirror and
          not m.config.GetString('repo.mirror') == 'true'):
        groups.append(platformize(platform.system().lower()))
    elif opt.platform == 'all':
      groups.extend(map(platformize, all_platforms))
    elif opt.platform in all_platforms:
      groups.append(platformize(opt.platform))
    elif opt.platform != 'none':
      print('fatal: invalid platform flag', file=sys.stderr)
      sys.exit(1)

    groups = [x for x in groups if x]
    groupstr = ','.join(groups)
    if opt.platform == 'auto' and groupstr == 'default,platform-' + platform.system().lower():
      groupstr = None
    m.config.SetString('manifest.groups', groupstr)

    if opt.reference:
      m.config.SetString('repo.reference', opt.reference)

    if opt.archive:
      if is_new:
        m.config.SetString('repo.archive', 'true')
      else:
        print('fatal: --archive is only supported when initializing a new '
              'workspace.', file=sys.stderr)
        print('Either delete the .repo folder in this workspace, or initialize '
              'in another location.', file=sys.stderr)
        sys.exit(1)

    if opt.mirror:
      if is_new:
        m.config.SetString('repo.mirror', 'true')
      else:
        print('fatal: --mirror is only supported when initializing a new '
              'workspace.', file=sys.stderr)
        print('Either delete the .repo folder in this workspace, or initialize '
              'in another location.', file=sys.stderr)
        sys.exit(1)

    if not m.Sync_NetworkHalf(is_new=is_new, quiet=opt.quiet,
        clone_bundle=not opt.no_clone_bundle):
      r = m.GetRemote(m.remote.name)
      print('fatal: cannot obtain manifest %s' % r.url, file=sys.stderr)

      # Better delete the manifest git dir if we created it; otherwise next
      # time (when user fixes problems) we won't go through the "is_new" logic.
      if is_new:
        portable.rmtree(m.gitdir)
      sys.exit(1)

    if opt.manifest_branch:
      m.MetaBranchSwitch()

    syncbuf = SyncBuffer(m.config)
    m.Sync_LocalHalf(syncbuf)
    syncbuf.Finish()

    if is_new or m.CurrentBranch is None:
      if not m.StartBranch('default'):
        print('fatal: cannot create default in manifest', file=sys.stderr)
        sys.exit(1)

  def _LinkManifest(self, name):
    if not name:
      print >>sys.stderr, 'fatal: manifest name (-m) is required.'
      sys.exit(1)

    try:
      self.manifest.Link(name)
    except ManifestParseError, e:
      print >>sys.stderr, "fatal: manifest '%s' not available" % name
      print >>sys.stderr, 'fatal: %s' % str(e)
      sys.exit(1)

  def _PromptKey(self, prompt, key, value):
    mp = self.manifest.manifestProject

    sys.stdout.write('%-10s [%s]: ' % (prompt, value))
    a = sys.stdin.readline().strip()
    if a != '' and a != value:
      mp.config.SetString(key, a)

  def _ConfigureUser(self):
    mp = self.manifest.manifestProject

    print ''
    self._PromptKey('Your Name', 'user.name', mp.UserName)
    self._PromptKey('Your Email', 'user.email', mp.UserEmail)

  def _HasColorSet(self, gc):
    for n in ['ui', 'diff', 'status']:
      if gc.Has('color.%s' % n):
        return True
    return False

  def _ConfigureColor(self):
    gc = self.manifest.globalConfig
    if self._HasColorSet(gc):
      return

    class _Test(Coloring):
      def __init__(self):
        Coloring.__init__(self, gc, 'test color display')
        self._on = True
    out = _Test()

    print ''
    print "Testing colorized output (for 'repo diff', 'repo status'):"

    for c in ['black','red','green','yellow','blue','magenta','cyan']:
      out.write(' ')
      out.printer(fg=c)(' %-6s ', c)
    out.write(' ')
    out.printer(fg='white', bg='black')(' %s ' % 'white')
    out.nl()

    for c in ['bold','dim','ul','reverse']:
      out.write(' ')
      out.printer(fg='black', attr=c)(' %-6s ', c)
    out.nl()

    sys.stdout.write('Enable color display in this user account (y/n)? ')
    a = sys.stdin.readline().strip().lower()
    if a in ('y', 'yes', 't', 'true', 'on'):
      gc.SetString('color.ui', 'auto')

  def Execute(self, opt, args):
    self._CheckGitVersion()
    self._SyncManifest(opt)
    self._LinkManifest(opt.manifest_name)

    if os.isatty(0) and os.isatty(1) and not opt.mirror:
      self._ConfigureUser()
      self._ConfigureColor()

    if opt.mirror:
      type = 'mirror '
    else:
      type = ''

    print ''
    print 'repo %sinitialized in %s' % (type, self.manifest.topdir)
