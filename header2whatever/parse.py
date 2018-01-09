
import argparse
import os
from os.path import basename, dirname, exists, join
import tempfile

import CppHeaderParser
import jinja2
import yaml

from . import default_hooks
from .config import Config, Template
from .util import import_file, read_file

def call_hook(hooks, hook_name, *args):
    for hook in hooks[hook_name]:
        hook(*args)

def _process_method(method, hooks, data):
    call_hook(hooks, 'method_hook', method, data)

def _process_class(cls, hooks, data):
    for method in cls['methods']['public']:
        _process_method(method, hooks, data)

    call_hook(hooks, 'class_hook', cls, data)

def process_header(fname, hooks, data):
    '''Returns a list of lines'''

    header = CppHeaderParser.CppHeader(read_file(fname),
                                       argType='string')

    header.full_fname = fname
    header.fname = basename(fname)

    classes = []

    for cls in sorted(header.classes.values(), key=lambda c: c['line_number']):
        _process_class(cls, hooks, data)
        classes.append(cls)

    header.classes = classes

    for cls in header.classes:
        call_hook(hooks, 'class_hook', cls, data)

    for fn in header.functions:
        call_hook(hooks, 'function_hook', fn, data)

    call_hook(hooks, 'header_hook', header, data)
    return header

def process_module(headers, hooks, data):

    headers = [process_header(header, hooks, data) for header in headers]

    data = {}
    data['headers'] = headers

    # optimization for single-header use case
    if len(headers) == 1:
        data['header'] = headers[0]

    return data

def process_config(cfg):

    # Setup the default hooks first
    hook_modules = [default_hooks]
    if cfg.hooks:
        hook_modules.append(import_file(cfg.hooks))

    hooks = {}
    for mod in hook_modules:
        for n in ['function_hook', 'method_hook', 'class_hook', 'header_hook']:
            fn = getattr(mod, n, None)
            if fn:
                hooks.setdefault(n, []).append(fn)

    gbls = {}
    gbls['config'] = cfg
    gbls.update(cfg.vars)

    if cfg.data:
        with open(cfg.data) as fp:
            gbls['data'] = yaml.safe_load(fp)

    # Process the module
    data = process_module(cfg.headers, hooks, gbls)

    for tmpl in cfg.templates:

        # Load the template
        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(searchpath=dirname(tmpl.src)),
            undefined=jinja2.StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
        )

        jtmpl = env.get_template(basename(tmpl.src), globals=gbls)
        s = jtmpl.render(**data)

        if tmpl.dst:
            with open(tmpl.dst, 'w') as fp:
                fp.write(s)
        else:
            print(s)


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument('template', help='Jinja2 template to use for generation. If set to "pprint", then it will output the data structure available')
    parser.add_argument('headers', nargs='+')
    parser.add_argument('-o', '--output', help='Output results to specified file')
    parser.add_argument('-p', '--param', nargs='+', help="k=v parameter", default=[])
    parser.add_argument('-d', '--data', help='Load YAML data file and make it available under the data key')

    parser.add_argument('--hooks', help='Specify custom hooks file to load')

    args = parser.parse_args()

    # convert the arguments into a Config object
    cfg = Config()

    tmpl = Template()
    cfg.templates = [tmpl]

    cfg.headers = args.headers
    tmpl.src = args.template
    tmpl.dst = args.output
    cfg.hooks = args.hooks
    cfg.data = args.data

    # Special hook
    tmpfile = None
    if args.template == 'pprint':
        tmpfile = tempfile.NamedTemporaryFile()
        tmpfile.write(b'{% for h in headers %}\n{{ h | pprint }}\n{% endfor %}\n')
        tmpfile.flush()
        tmpl.src = tmpfile.name

    try:

        for p in args.param:
            if '=' not in p:
                raise ValueError("Invalid --param `%s`" % p)
            pp = p.split('=', 2)
            cfg.vars[pp[0]] = pp[1]

        cfg.validate()

        process_config(cfg)
    finally:
        if tmpfile:
            tmpfile.close()


def batch():
    parser = argparse.ArgumentParser()
    parser.add_argument('config')
    parser.add_argument('outdir')
    parser.add_argument('-r', '--root',
                        help="Root directory of headers")

    args = parser.parse_args()

    try:
        batch_convert(args.config,
                      args.outdir,
                      args.root)
    except BatchError as e:
        parser.error(str(e))

class BatchError(Exception):
    pass

def batch_convert(config_path, outdir, root):

    with open(config_path) as fp:
        raw_cfg = yaml.safe_load(fp)

    if not isinstance(raw_cfg, list):
        raise BatchError("Invalid cfg %s: root element must be a list" % config_path)

    cfgdir = dirname(config_path)

    cfgs = []
    for raw in raw_cfg:
        cfg = Config(raw)

        for tmpl in cfg.templates:
            if tmpl.src:
                tmpl.src = join(cfgdir, tmpl.src)

            # Prepend outdir to output if specified
            if tmpl.dst:
                tmpl.dst = join(outdir, tmpl.dst)

        # resolve files relative to the configuration
        # -> hooks and templates are expected to be near config
        if cfg.data:
            cfg.data = join(cfgdir, cfg.data)

        if cfg.hooks:
            cfg.hooks = join(cfgdir, cfg.hooks)

        # Headers are different
        if root:
            cfg.headers = [join(root, header) for header in cfg.headers]

        cfg.validate()
        cfgs.append(cfg)

    if not exists(outdir):
        os.makedirs(outdir)

    for cfg in cfgs:
        process_config(cfg)

if __name__ == '__main__':
    main()
