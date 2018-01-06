'''
    These hooks don't actually do anything. Instead, they exist to document
    the available hooks. Hooks are called after the specified object is
    processed.
    
    The hooks can do whatever they want to the objects when they're passed in.
    The indended use is to parse the available attributes, and create new
    attributes based on those.
    
    To use your own hooks, define the functions you need in a python file, and
    pass the file in via the --hooks argument.
'''


def function_hook(fn, data):
    '''Called for each function in the header'''

def method_hook(fn, data):
    '''Called for each public method in a class'''
    
def class_hook(cls, data):
    '''Called for each class in a header'''
    
def header_hook(header, data):
    '''Called for each header processed'''

