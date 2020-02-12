
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

class CppHeaderParserError(Exception):
    pass

class PreprocessorError(Exception):
    pass


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
        try:
            contents = preprocess_file(fname,
                                    cfg.pp_include_paths,
                                    cfg.pp_retain_all_content,
                                    cfg.pp_defines)
        except Exception as e:
            raise PreprocessorError("processing " + fname) from e
    else:
        contents = read_file(fname)

    try:
        header = CppHeaderParser.CppHeader(contents,
                                        argType='string')
    except Exception as e:
        raise CppHeaderParserError("processing " + fname) from e

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

    if cfg.preprocess and cfg.pp_retain_all_content:
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

class ConfigProcessor:

    def __init__(self, searchpath, hookobj=None):
        self._env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(searchpath=searchpath),
            undefined=jinja2.StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.hookobj = hookobj

    def process_config(self, cfg, data=None, hookobj=None):
        # If data is passed in, this is used for data instead of loading it
        # from file
        old_ignored = CppHeaderParser.ignoreSymbols
        CppHeaderParser.ignoreSymbols = old_ignored[:]
        if cfg.ignore_symbols:
            CppHeaderParser.ignoreSymbols.extend(cfg.ignore_symbols)

        try:
            return self._process_config(cfg, data, hookobj)
        finally:
            CppHeaderParser.ignoreSymbols = old_ignored

    def _process_config(self, cfg, data, hookobj):
        # Setup the default hooks first
        hook_modules = [default_hooks]
        if cfg.hooks:
            hook_modules.append(import_file(cfg.hooks))
        if self.hookobj:
            hook_modules.append(self.hookobj)
        if hookobj:
            hook_modules.append(hookobj)

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
            with open(cfg.data, encoding='utf-8-sig') as fp:
                gbls['data'] = yaml.safe_load(fp)

            if gbls['data'] is None:
                gbls['data'] = {}
        
        # Provide an escape mechanism
        def _skip_generation():
            raise SkipGeneration()

        gbls['skip_generation'] = _skip_generation

        # Process the module
        data = process_module(cfg, hooks, gbls)

        gbls.update(data)

        for tmpl in cfg.templates:
            self._render_template(tmpl, gbls)
            
        if cfg.class_templates:
            for header in data["headers"]:
                for clsdata in header.classes:
                    gbls["cls"] = clsdata
                    for tmpl in cfg.class_templates:
                        self._render_template(tmpl, gbls)

    def _render_template(self, tmpl, data):
        
        jtmpl = self._env.get_template(basename(tmpl.src))

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
                dst = env.get_template('_').render(**data)
            
            with open(dst, 'w', encoding='utf-8') as fp:
                fp.write(s)
        else:
            print(s)

def process_config(cfg, data=None, hooks=None):
    searchpath = set()
    for tmpl in cfg.templates:
        searchpath.add(dirname(tmpl.src))
    for tmpl in cfg.class_templates:
        searchpath.add(dirname(tmpl.src))
    
    cp = ConfigProcessor(searchpath, hooks)
    cp.process_config(cfg, data)


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument('template', help='Jinja2 template to use for generation. If set to "pprint", then it will output the data structure available')
    parser.add_argument('headers', nargs=argparse.REMAINDER)
    parser.add_argument('-o', '--output', help='Output results to specified file')
    parser.add_argument('-p', '--param', nargs='+', help="k=v parameter", default=[])
    parser.add_argument('-d', '--data', help='Load YAML data file and make it available under the data key')
    
    parser.add_argument('--preprocess', action='store_true', default=False, help="Preprocess file with pcpp")
    parser.add_argument('--pp-retain-all-content', action='store_true', default=False)
    parser.add_argument('--include', '-I', action='append', default=[], help="Preprocessor include paths")
    parser.add_argument('--define', '-D', action='append', default=[], help="Preprocessor #define macros")

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
    cfg.preprocess = args.preprocess
    cfg.pp_include_paths = args.include
    cfg.pp_defines = args.define
    cfg.pp_retain_all_content = args.pp_retain_all_content

    # Special hook
    tmpfile = None
    if args.template == 'pprint':
        tmpfile = tempfile.NamedTemporaryFile()
        tmpfile.write(b'{% for h in headers %}\n{{ h.__dict__ | pprint }}\n{% endfor %}\n')
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
