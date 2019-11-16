
import argparse
import os
from os.path import basename, dirname, exists, join, relpath
import tempfile

import CppHeaderParser
import jinja2
import yaml

from . import default_hooks
from .config import Config, Template
from .preprocess import preprocess_file
from .util import import_file, read_file

class HookError(Exception):
    pass

class SkipGeneration(Exception):
    pass

def call_hook(name, hooks, hook_name, *args):
    for hook in hooks[hook_name]:
        try:
            hook(*args)
        except Exception as e:
            raise HookError(hook_name + ": " + name) from e

def _process_method(method, hooks, data):
    call_hook(method["name"], hooks, 'method_hook', method, data)

def _process_class(cls, hooks, data):
    for method in cls['methods']['public']:
        _process_method(method, hooks, data)

    call_hook(cls["name"], hooks, 'class_hook', cls, data)

def _fix_header(contents):
    # CppHeaderParser doesn't handle 'enum class' yet
    contents = contents.replace('enum class', 'enum')
    return contents

def _only_this_file(l, fname):
    r = []
    for i in l:
        if 'filename' not in i:
            raise ValueError(i)
        if i['filename'] == fname:
            r.append(i)
    return r

def process_header(cfg, fname, hooks, data):
    '''Returns a list of lines'''

    if cfg.preprocess:
        contents = preprocess_file(fname, cfg.pp_include_paths)
    else:
        contents = read_file(fname)

    header = CppHeaderParser.CppHeader(_fix_header(contents),
                                       argType='string')

    header.full_fname = fname
    root = getattr(cfg, 'root', None)
    if root:
        header.rel_fname = relpath(fname, root)
    else:
        header.rel_fname = fname

    header.fname = basename(fname)

    header.classes = header.classes_order

    # move and filter
    header.all_classes = header.classes
    header.all_functions = header.functions
    header.all_enums = header.enums
    header.all_global_enums = header.global_enums
    header.all_variables = header.variables

    if cfg.preprocess:
        header.classes = _only_this_file(header.classes, fname)
        header.functions = _only_this_file(header.functions, fname)
        header.enums = _only_this_file(header.enums, fname)
        header.global_enums = _only_this_file(header.global_enums, fname)
        header.variables = _only_this_file(header.variables, fname)

    for cls in header.classes:
        _process_class(cls, hooks, data)

    for fn in header.functions:
        call_hook(fn["name"], hooks, 'function_hook', fn, data)

    call_hook(header.fname, hooks, 'header_hook', header, data)
    return header

def process_module(cfg, hooks, data):

    headers = [process_header(cfg, header, hooks, data) for header in cfg.headers]

    data = {}
    data['headers'] = headers

    # optimization for single-header use case
    if len(headers) == 1:
        data['header'] = headers[0]

    return data

def process_config(cfg, data=None):
    # If data is passed in, this is used for data instead of loading it
    # from file
    old_ignored = CppHeaderParser.ignoreSymbols
    CppHeaderParser.ignoreSymbols = old_ignored[:]
    if cfg.ignore_symbols:
        CppHeaderParser.ignoreSymbols.extend(cfg.ignore_symbols)

    try:
        return _process_config(cfg, data)
    finally:
        CppHeaderParser.ignoreSymbols = old_ignored

def _render_template(tmpl, data, gbls):
    # Load the template
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(searchpath=dirname(tmpl.src)),
        undefined=jinja2.StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )

    jtmpl = env.get_template(basename(tmpl.src), globals=gbls)

    try:
        s = jtmpl.render(**data)
    except SkipGeneration:
        return

    dst = tmpl.dst
    if dst:
        if '{' in dst:
            env = jinja2.Environment(
                loader=jinja2.FunctionLoader(lambda _: dst),
                undefined=jinja2.StrictUndefined,
            )
            dst = env.get_template('_', globals=gbls).render(**data)
        
        with open(dst, 'w') as fp:
            fp.write(s)
    else:
        print(s)

def _process_config(cfg, data):
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

    if data is not None:
        gbls['data'] = data
    elif cfg.data:
        with open(cfg.data) as fp:
            gbls['data'] = yaml.safe_load(fp)

        if gbls['data'] is None:
            gbls['data'] = {}
    
    # Provide an escape mechanism
    def _skip_generation():
        raise SkipGeneration()

    gbls['skip_generation'] = _skip_generation

    # Process the module
    data = process_module(cfg, hooks, gbls)

    for tmpl in cfg.templates:
        _render_template(tmpl, data, gbls)
        
    if cfg.class_templates:
        for header in data["headers"]:
            for clsdata in header.classes:
                data["cls"] = clsdata
                for tmpl in cfg.class_templates:
                    _render_template(tmpl, data, gbls)



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
            cfg.pp_include_paths = [join(root, ppath) for ppath in cfg.pp_include_paths]

        cfg.validate()
        cfg.root = root
        cfgs.append(cfg)

    if not exists(outdir):
        os.makedirs(outdir)

    for cfg in cfgs:
        process_config(cfg)

if __name__ == '__main__':
    main()
