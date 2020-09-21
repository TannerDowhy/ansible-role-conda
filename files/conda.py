#!/usr/bin/env python

# Copyright: (c) 2019, Tanner Dowhy <tanner.dowhy@usask.ca>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

import os
import json
from ansible.module_utils.basic import AnsibleModule


class Conda(object):
    def __init__(self, module, env_name):
        self.module = module
        self.pyv = self._get_python(module.params['pyv'])
        self.executable = self._get_conda(module.params['executable'])
        if env_name:
            env_opt = '--prefix' if os.path.sep in env_name else '--name'
            self.env_args = [env_opt, env_name]
        else:
            self.env_args = []
        # if module.params['python'] is not None:
        # self.python = module.params['python']

    def _get_conda(self, executable):
        conda_exe = None
        if executable:
            if os.path.isfile(executable):
                conda_exe = executable
            else:
                self.module.fail_json(msg = "%s is not a valid conda executable."
                    % (executable))
        else:
            conda_exe = self.module.get_bin_path('conda')
            if not conda_exe:
                self.module.fail_json(msg = 'Conda not fount in PATH and executable is not specified.')
        return conda_exe

    def _get_python(self, pyv):
        return pyv

    def create_env(self, env_name):
        # if self.python is not None:
        return self._run_conda('create', '--yes', '--quiet', 'python=%s' % self.pyv, *self.env_args)
        # return self._run_conda('create', '--yes', '--quiet', *self.env_args)

    def _run_conda(self, subcmd, *args, **kwargs):
        # check_rc = kwargs.pop('check_rc', True)
        cmd = [self.executable, subcmd]
        cmd += args
        cmd += ["--json"]
        rc, out, err = self.module.run_command(cmd)
        if rc != 0:
            try:
                outobj = json.loads(out)
                self.module.fail_json(command=cmd, msg=outobj['error'], stdout=out,
                    stderr=err, exception_name=outobj['exception_name'],
                    exception_type=outobj['exception_type'])
            except ValueError:
                self.module.fail_json(command=cmd, msg="Unable to parse error.",
                    rc=rc, stdout=out, stderr=err)
        try:
            return rc, json.loads(out), err
        except ValueError:
            self.module.fail_json(command=cmd, msg="Failed to parse output of command.",
                stdout=out, stderr=err)

    def check_env(self, env_name):
        if env_name == 'base':
            return True
        if os.sep in env_name:
            return os.path.isdir(env_name)
        envs = self.list_envs()
        for e in envs:
            tmp = e.split('/')[-1]
            if tmp == env_name:
                return True
        return False

    def list_envs(self):
        rc, out, err = self._run_conda('env', 'list')
        return out['envs']

    @staticmethod
    def _is_present(package, installed_packages, check_version=False):
        """Check if the package is present in the list of installed packages.
        Compare versions of the target and installed package
        if check_version is set.
        """
        target_name = package['name']

        match = [p for p in installed_packages if p['name'] == target_name]
        if not match:
            return False
        installed_package = match[0]

        # Match only as specific as the version is specified.
        # Ex only major/minor/patch level.
        target_version = package['version']
        if target_version and check_version:
            target_version = target_version.split('.')
            installed_version = installed_package['version'].split('.')
            return target_version == installed_version[:len(target_version)]
        return True

    def get_absent_packages(self,
                            target_packages,
                            installed_packages,
                            check_version):
        """Return the list of packages that are not installed.
        If check_version is set, result will include
        packages with the wrong version.
        """
        return [p for p in target_packages
                if not self._is_present(p, installed_packages, check_version)]

    def get_present_packages(self,
                             target_packages,
                             installed_packages,
                             check_version):
        """Return the list of packages that are
           installed and should be removed"""
        return [p for p in target_packages
                if self._is_present(p, installed_packages, check_version)]

    def install_packages(self, packages, channel):
        """Install the packages"""
        pkg_strs = []
        for package in packages:
            if package['version']:
                pkg_strs.append('{name}={version}'.format(**package))
            else:
                pkg_strs.append(package['name'])
        return self._run_package_cmd('install',
                                     channel,
                                     *pkg_strs + self.env_args)

    def remove_packages(self, packages, channel):
        """Remove the packages"""
        return self._run_package_cmd('remove',
                                     channel,
                                     *packages + self.env_args)

    def update_packages(self, packages, channel, dry_run=False):
        """Update the packages.
        If dry_run is set, no actions are taken.
        """
        args = packages + self.env_args
        if dry_run:
            args.append('--dry-run')
        return self._run_package_cmd('update', channel, *args)

    def list_packages(self, env):
        """List all packages installed in the environment"""
        rc, out, err = self._run_conda('list', *self.env_args)
        return [dict(name=p['name'], version=p['version']) for p in out]

    def _run_package_cmd(self, subcmd, channels, *args, **kwargs):
        if channels is not None:
            for channel in channels:
                args += ('--channel', channel)
        rc, out, err = self._run_conda(subcmd,
                                       '--quiet',
                                       '--yes',
                                       *args,
                                       **kwargs
                                       )
        return out['actions'] if 'actions' in out else []

    @staticmethod
    def split_name_version(package_spec, default_version=None):
        name = package_spec
        version = default_version
        if '=' in package_spec:
            name, version = package_spec.split('=')
        return {'name': name, 'version': version}
