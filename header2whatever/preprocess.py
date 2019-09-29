
from os.path import dirname
import subprocess
import sys


def preprocess_file(fname, include_paths=[]):
    '''
        Preprocesses the file via pcpp. Useful for dealing with files that have
        complex macros in them, as CppHeaderParser can't deal with them
    '''

    # Execute pcpp externally because it's easier than dealing with
    # their API
    args = [
        sys.executable,
        "-c",
        "import pcpp; pcpp.main()",
        "--passthru-unfound-includes",
        "--passthru-comments",
        "--compress",
        "--line-directive=##__H2WLINE",
        fname,
        "-o",
        "-",
    ]

    for p in include_paths:
        args.append("-I")
        args.append(p)
    
    output = subprocess.check_output(args, universal_newlines=True).split("\n")

    # the output of pcpp includes the contents of all the included files,
    # which isn't what a typical user of h2w would want, so we strip out
    # the line directives and any content that isn't in our original file
    ew = '"' + fname + '"'
    new_output = []
    for line in output:
        if line.startswith("##__H2WLINE"):
            keep = line.endswith(ew)
            continue
        
        if keep:
            new_output.append(line)
    
    return "\n".join(new_output)
