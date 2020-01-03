
from schematics.models import Model
from schematics.types import ModelType, BooleanType, StringType, ListType, DictType


class Template(Model):

    # source Jinja2 template name
    src = StringType(required=True)

    # output filename (relative to outdir). If a { is present, this is 
    # processed as a Jinja2 template
    dst = StringType(default=None)


class Config(Model):
    '''
        Used to validate the batch configuration file
    '''

    # Input C/C++ header files to parse
    headers = ListType(StringType, required=True)

    # Jinja2 templates processed once per config
    templates = ListType(ModelType(Template), default=[])

    # Jinja2 templates processed for each class
    class_templates = ListType(ModelType(Template), default=[])

    # Input custom hooks
    hooks = StringType()

    #: YAML file to load with variables
    data = StringType()

    #: Variables to pass to the template
    vars = DictType(StringType, default={})

    #: For macros or other nonsense, these will
    #: be added to CppHeaderParser's ignore list
    ignore_symbols = ListType(StringType)

    #: Enable preprocessing of the file
    preprocess = BooleanType(default=False)

    #: If True, don't modify preprocessed output and keep #line preprocessing
    #: tokens in the output. Otherwise, remove anything not associated with
    #: the file being parsed.
    pp_retain_all_content = BooleanType(default=False)

    #: Include directories (relative to root) to use for preprocessing
    pp_include_paths = ListType(StringType, default=[])

    #: Preprocessor defines. For example, if you're parsing C++ code,
    #: it might make sense to add '__cplusplus 201103L' here
    pp_defines = ListType(StringType, default=[])


