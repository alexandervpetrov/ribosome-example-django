#!/usr/bin/env python

import os
import io
import sys
import shutil
import subprocess
import time

import click
import ruamel.yaml as ryaml
import jinja2

HERE = os.path.abspath(os.path.dirname(__file__))


def print_error(*args):
    print('ERROR:', *args, file=sys.stderr)


def load_settings(service, config):
    service_descriptor_filepath = os.path.join(HERE, 'services', '{}.yaml'.format(service))
    yaml = ryaml.YAML()
    try:
        with io.open(service_descriptor_filepath, encoding='utf-8') as f:
            descriptor = yaml.load(f)
    except Exception as e:
        return None, 'Failed to load descriptor for service [{}]: {}'.format(service, e)
    else:
        if not descriptor or 'configs' not in descriptor:
            return None, 'Service descriptor invalid or empty'
        if config not in descriptor['configs']:
            return None, 'Config definition not found: {}'.format(config)

        def deep_format(obj):
            if isinstance(obj, dict):
                return {k: deep_format(v) for k, v in obj.items()}
            if isinstance(obj, str):
                return obj.format(service=service, config=config)
            return obj

        settings_common = descriptor.get('common', {})
        settings = deep_format(settings_common)
        settings.update(descriptor['configs'][config] or {})
        settings['SERVICE'] = service
        settings['CONFIG'] = config
        settings['HOME'] = HERE
        settings['PYTHON_CMD'] = sys.executable
        settings['LOGGING_DIR'] = '/var/log/example'
        # settings['env']['LOG_CONFIG'] = os.path.join(os.getcwd(), 'services', 'logging', '{}.yaml'.format(settings['logconfig']))
        env_prefix = descriptor.get('env_prefix')
        if env_prefix:
            settings['env'] = {'{}_{}'.format(env_prefix, k): v for k, v in settings['env'].items()}
        return settings, None


def render_template(localpath, context):
    loader = jinja2.FileSystemLoader(HERE)
    env = jinja2.Environment(loader=loader)
    env.undefined = jinja2.StrictUndefined
    template = env.get_template(localpath)
    result = template.render(context)
    return result


def derive_systemd_name(service, config):
    return 'example.{}.{}.service'.format(service, config)


def systemd_service_path(service_name):
    return os.path.join('/etc/systemd/system', service_name)


def systemd_install(service_name, service_def):
    systemd_path = systemd_service_path(service_name)
    try:
        with io.open(systemd_path, 'w', encoding='utf-8') as ostream:
            shutil.copyfileobj(io.StringIO(service_def), ostream)
        subprocess.run('systemctl daemon-reload'.split(), check=True)
        subprocess.run('systemctl enable {}'.format(service_name).split(), check=True)
        return None, None
    except Exception as e:
        return None, 'Failed to install [{}]: {}'.format(service_name, e)


def systemd_uninstall(service_name):
    systemd_path = systemd_service_path(service_name)
    try:
        if os.path.exists(systemd_path):
            subprocess.run('systemctl stop {}'.format(service_name).split(), check=True)
            subprocess.run('systemctl disable {}'.format(service_name).split(), check=True)
            os.remove(systemd_path)
        return None, None
    except FileNotFoundError:
        return None, None
    except Exception as e:
        return None, 'Failed to uninstall [{}]: {}'.format(service_name, e)


WAIT_FOR_STARTUP = 2.0  # second(s)


def systemd_start(service_name):
    job = subprocess.run('systemctl restart {}'.format(service_name).split())
    if job.returncode != 0:
        return None, 'Failed to start service: {}'.format(service_name)
    time.sleep(WAIT_FOR_STARTUP)
    job = subprocess.run('systemctl -q status {}'.format(service_name).split(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if job.returncode != 0:
        # TODO: inconsistent behavior: service remains enabled
        subprocess.run('systemctl stop {}'.format(service_name).split())
        return None, 'Failed to get service status: {}'.format(service_name)
    return None, None


def systemd_stop(service_name):
    job = subprocess.run('systemctl stop {}'.format(service_name).split())
    if job.returncode != 0:
        return None, 'Failed to stop service: {}'.format(service_name)
    return None, None


def copy_files(srcdir, dstdir):
    shutil.rmtree(dstdir, ignore_errors=True)
    os.makedirs(dstdir)
    if not os.path.exists(srcdir):
        return None, 'Source directory not exists: {}'.format(srcdir)
    job = subprocess.run('rsync -r {}/ {}'.format(srcdir, dstdir).split())
    if job.returncode != 0:
        return None, 'Failed to copy files'
    return None, None


@click.group()
def cli():
    """Tool for service control"""
    pass


@cli.command()
@click.argument('service')
@click.argument('config')
def install(service, config):
    """Install systemd service"""
    print('Setting up service [{}] for config [{}]...'.format(service, config))
    settings, error = load_settings(service, config)
    if error is not None:
        print_error(error)
        sys.exit(1)
    if service in ('webapp',):
        settings['GUNICORN_CMD'] = os.path.join(os.path.dirname(settings['PYTHON_CMD']), 'gunicorn')
        settings['GUNICORN_CONFIG_PATH'] = os.path.join(settings['HOME'], 'services', 'gunicorn_config.py')
        service_template_path = os.path.join('services', 'templates', 'systemd.gunicorn.service')
        service_def = render_template(service_template_path, settings)
        targetroot = settings['targetroot']
        __, error = copy_files(os.path.join(HERE, 'project_static'), targetroot)
        if error is not None:
            print_error(error)
            sys.exit(1)
    elif service in ('taskplanner', 'taskworker'):
        settings['CELERY_CMD'] = os.path.join(os.path.dirname(settings['PYTHON_CMD']), 'celery')
        service_template_path = os.path.join('services', 'templates', 'systemd.celery.service')
        service_def = render_template(service_template_path, settings)
    else:
        print_error('Unsupported service: {}'.format(service))
        sys.exit(1)
        # service_template_path = os.path.join('services', 'templates', 'systemd.run.service')
        # service_def = render_template(service_template_path, settings)
    # print(service_def)
    systemd_name = derive_systemd_name(service, config)
    __, error = systemd_install(systemd_name, service_def)
    if error is not None:
        print_error(error)
        sys.exit(1)
    print('Service installed:', systemd_name)


@cli.command()
@click.argument('service')
@click.argument('config')
def uninstall(service, config):
    """Uninstall systemd service"""
    print('Removing service [{}] for config [{}]...'.format(service, config))
    systemd_name = derive_systemd_name(service, config)
    __, error = systemd_uninstall(systemd_name)
    if error is not None:
        print_error(error)
        sys.exit(1)
    print('Service uninstalled:', systemd_name)


@cli.command()
@click.argument('service')
@click.argument('config')
def start(service, config):
    """Start systemd service"""
    print('Starting service [{}] for config [{}]...'.format(service, config))
    systemd_name = derive_systemd_name(service, config)
    __, error = systemd_start(systemd_name)
    if error is not None:
        print_error(error)
        sys.exit(1)
    print('Service started:', systemd_name)


@cli.command()
@click.argument('service')
@click.argument('config')
def stop(service, config):
    """Stop systemd service"""
    print('Stopping service [{}] for config [{}]...'.format(service, config))
    systemd_name = derive_systemd_name(service, config)
    __, error = systemd_stop(systemd_name)
    if error is not None:
        print_error(error)
        sys.exit(1)
    print('Service stopped:', systemd_name)


def guess_and_fix_command(cmdline):
    args = cmdline.split()
    first_arg = args[0]
    if first_arg.endswith('.py'):
        return '{} {}'.format(sys.executable, ' '.join(args))
    pythondir = os.path.abspath(os.path.dirname(sys.executable))
    possible_executable_name = os.path.join(pythondir, first_arg)
    if os.path.exists(possible_executable_name):
        return '{} {}'.format(possible_executable_name, ' '.join(args[1:]))
    return cmdline


@cli.command(short_help='Run as foreground child process')
@click.argument('service')
@click.argument('config')
def run(service, config):
    """Run as foreground child process (convenient for development)"""

    settings, error = load_settings(service, config)
    if error is not None:
        print_error(error)
        sys.exit(1)

    run_command_args = settings.get('run')
    if not run_command_args:
        print_error('Settings do not have run command specified')
        sys.exit(1)

    run_command = guess_and_fix_command(run_command_args)

    job_env = os.environ.copy()
    job_env.update({k: str(v) for k, v in settings['env'].items()})
    job = subprocess.run(run_command.split(), env=job_env)
    if job.returncode != 0:
        print_error('Service stopped with return code:', job.returncode)
        sys.exit(1)


@cli.command(short_help='Run command for service')
@click.argument('service')
@click.argument('config')
@click.argument('action')
@click.argument('args', nargs=-1)
def do(service, config, action, args):
    """Run service command"""

    settings, error = load_settings(service, config)
    if error is not None:
        print_error(error)
        sys.exit(1)

    if 'actions' not in settings:
        print_error('No actions found for service')
        sys.exit(1)

    action_command_base_args = settings['actions'].get(action)
    if not action_command_base_args:
        print_error('Settings do not have action [{}] command specified'.format(action))
        sys.exit(1)

    action_command_args = '{} {}'.format(action_command_base_args, ' '.join(args))
    action_command = guess_and_fix_command(action_command_args)

    job_env = os.environ.copy()
    job_env.update({k: str(v) for k, v in settings['env'].items()})
    job = subprocess.run(action_command.split(), env=job_env)
    if job.returncode != 0:
        print_error('Command stopped with return code:', job.returncode)
        sys.exit(1)


if __name__ == '__main__':
    cli()
