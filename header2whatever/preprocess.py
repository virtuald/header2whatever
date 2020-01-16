
import io
from os.path import dirname, relpath
import subprocess
import sys

from ._pcpp import Preprocessor, OutputDirective, Action
from .util import read_file

class PreprocessorError(Exception):
    pass

class H2WPreprocessor(Preprocessor):

    def __init__(self):
        Preprocessor.__init__(self)
        self.errors = []

    def on_error(self,file,line,msg):
        self.errors.append('%s:%d error: %s' % (file, line, msg))

    def on_include_not_found(self,is_system_include,curdir,includepath):
        raise OutputDirective(Action.IgnoreAndPassThrough)

    def on_comment(self,tok):
        return True


def _filter_self(fname, fp):
    # the output of pcpp includes the contents of all the included files,
    # which isn't what a typical user of h2w would want, so we strip out
    # the line directives and any content that isn't in our original file

    # Compute the filename to match based on how pcpp does it
    try:
        relfname = relpath(fname)
    except Exception:
        relfname = fname
    relfname = relfname.replace('\\', '/')

    relfname += '"\n'

    new_output = io.StringIO()
    keep = True

    for line in fp:
        if line.startswith("#line"):
            keep = line.endswith(relfname)
        
        if keep:
            new_output.write(line)
    
    new_output.seek(0)
    return new_output.read()


def preprocess_file(fname, include_paths=[], retain_all_content=False, defines=[]):
    '''
        Preprocesses the file via pcpp. Useful for dealing with files that have
        complex macros in them, as CppHeaderParser can't deal with them
    '''

    pp = H2WPreprocessor()
    if include_paths:
        for p in include_paths:
            pp.add_path(p)
    
    for define in defines:
        pp.define(define)
    
    if not retain_all_content:
        pp.line_directive = "#line"
    
    pp_content = read_file(fname)
    pp.parse(pp_content, fname)
    
    if pp.errors:
        raise PreprocessorError('\n'.join(pp.errors))
    elif pp.return_code:
        raise PreprocessorError('failed with exit code %d' % pp.return_code)
    
    fp = io.StringIO()
    pp.write(fp)
    fp.seek(0)
    if retain_all_content:
        return fp.read()
    else:
        return _filter_self(fname, fp)


if __name__ == '__main__':
    print(preprocess_file(sys.argv[1], sys.argv[2:]))