
import collections
import os.path
import sys

import yaml

class ImportedObject(object):
    pass

def import_file(filename):
    '''
        Imports a file directly, and stores the resulting variables in
        a :class:`ImportedObject`. Works in Python 2 and 3.

        :param filename: File to import
        :returns: python module belonging to the file
    '''

    filename = os.path.abspath(filename)

    config_obj = ImportedObject()
    config_obj.__file__ = filename

    if sys.version_info[0] < 3:
        execfile(filename, config_obj.__dict__, config_obj.__dict__)
    else:
        with open(filename) as f:
            code = compile(f.read(), filename, 'exec')
            exec(code, config_obj.__dict__, config_obj.__dict__)

    return config_obj

def read_file(fname):
    # CppHeaderParser doesn't deal well with weirdly formatted files
    with open(fname, 'rb') as fp:
        contents = fp.read().decode('utf-8-sig', 'replace')

    return contents

_mapping_tag = yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG

def dict_constructor(loader, node):
    loader.flatten_mapping(node)
    return collections.OrderedDict(loader.construct_pairs(node))

yaml.SafeLoader.add_constructor(_mapping_tag, dict_constructor)

def yaml_load(fname):
    with open(fname) as fp:
        yaml.safe_load(fp)
