
import io
from os.path import dirname
import subprocess
import sys

from pcpp import Preprocessor, OutputDirective, Action

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

def preprocess_file(fname, include_paths=[]):
    '''
        Preprocesses the file via pcpp. Useful for dealing with files that have
        complex macros in them, as CppHeaderParser can't deal with them
    '''

    pp = H2WPreprocessor()
    if include_paths:
        for p in include_paths:
            pp.add_path(p)
    
    with open(fname) as fp:
        pp.parse(fp)
    
    if pp.errors:
        raise PreprocessorError('\n'.join(pp.errors))
    elif pp.return_code:
        raise PreprocessorError('failed with exit code %d' % pp.return_code)
    
    fp = io.StringIO()
    pp.write(fp)
    fp.seek(0)
    return fp.read()

if __name__ == '__main__':
    print(preprocess_file(sys.argv[1], sys.argv[2:]))