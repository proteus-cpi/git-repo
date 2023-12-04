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

import sys
from command import Command
from git_command import git

class Start(Command):
  common = True
  helpSummary = "Start a new branch for development"
  helpUsage = """
%prog <newbranchname> [<project>...]

This subcommand starts a new branch of development that is automatically
pulled from a remote branch.

It is equivalent to the following git commands:

"git branch --track <newbranchname> m/<codeline>",
or 
"git checkout --track -b <newbranchname> m/<codeline>".

All three forms set up the config entries that repo bases some of its
processing on.  Use %prog or git branch or checkout with --track to ensure
the configuration data is set up properly.

"""

  def Execute(self, opt, args):
    if not args:
      self.Usage()

    nb = args[0]
    if not git.check_ref_format('heads/%s' % nb):
      print >>sys.stderr, "error: '%s' is not a valid name" % nb
      sys.exit(1)

    err = []
    projects = []
    if not opt.all:
      projects = args[1:]
      if len(projects) < 1:
        projects = ['.',]  # start it in the local project by default

    all_projects = self.GetProjects(projects,
                                    missing_ok=bool(self.gitc_manifest))

    # This must happen after we find all_projects, since GetProjects may need
    # the local directory, which will disappear once we save the GITC manifest.
    if self.gitc_manifest:
      gitc_projects = self.GetProjects(projects, manifest=self.gitc_manifest,
                                       missing_ok=True)
      for project in gitc_projects:
        if project.old_revision:
          project.already_synced = True
        else:
          project.already_synced = False
          project.old_revision = project.revisionExpr
        project.revisionExpr = None
      # Save the GITC manifest.
      gitc_utils.save_manifest(self.gitc_manifest)

      # Make sure we have a valid CWD
      if not os.path.exists(os.getcwd()):
        os.chdir(self.manifest.topdir)

    pm = Progress('Starting %s' % nb, len(all_projects))
    for project in all_projects:
      pm.update()

      if self.gitc_manifest:
        gitc_project = self.gitc_manifest.paths[project.relpath]
        # Sync projects that have not been opened.
        if not gitc_project.already_synced:
          proj_localdir = os.path.join(self.gitc_manifest.gitc_client_dir,
                                       project.relpath)
          project.worktree = proj_localdir
          if not os.path.exists(proj_localdir):
            os.makedirs(proj_localdir)
          project.Sync_NetworkHalf()
          sync_buf = SyncBuffer(self.manifest.manifestProject.config)
          project.Sync_LocalHalf(sync_buf)
          project.revisionId = gitc_project.old_revision

      # If the current revision is a specific SHA1 then we can't push back
      # to it; so substitute with dest_branch if defined, or with manifest
      # default revision instead.
      branch_merge = ''
      if IsId(project.revisionExpr):
        if project.dest_branch:
          branch_merge = project.dest_branch
        else:
          branch_merge = self.manifest.default.revisionExpr

      if not project.StartBranch(nb, branch_merge=branch_merge):
        err.append(project)
    pm.end()

    if err:
      for p in err:
        print("error: %s/: cannot start %s" % (p.relpath, nb),
              file=sys.stderr)
      sys.exit(1)
