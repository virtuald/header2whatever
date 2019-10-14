header2whatever (h2w)
=====================

Generate arbitrary files from C/C++ header files using CppHeaderParser to read
the input files and Jinja2 templates to generate the outputs.

This grew out of a desire to generate pybind11 wrapping code from C++ header
files. pybind11gen was created, but then I wanted to generate more things...

There are still rough edges, and the documentation is mostly nonexistent, but
pull requests with fixes/improvements are very welcome!

As of 0.3.0, h2w requires Python 3.3+

Install
-------

::

    pip install header2whatever

Usage
=====

First, you need to create a jinja2 template that represents whatever you want
to generate from the header file. For example, maybe you want to describe the
functions in yaml::

    ---
    {% for header in headers %}
    {% for fn in header.functions %}
    {{ fn.name }}:
      returns: {{ fn.returns }}
      params:
      {% for param in fn.parameters %}
      - { name: {{ param.name }}, type: "{{ param.type }}" }
      {% endfor %}

    {% endfor %}
    {% endfor %}

And let's say you have the following header file ``foo.h``::

    void some_fn(int i);
    int returns_int(int p1, char* p2);

You can execute the following::

    h2w foo.h -o foo.yml

And you'll get the following output::

    ---
    returns_int:
      returns: int
      params:
      - { name: p1, type: "int" }
      - { name: p2, type: "char *" }

    some_fn:
      returns: void
      params:
      - { name: i, type: "int" }

As you can see, while this is a silly example, this approach is very flexible
and fairly powerful.

Currently, the data structure passed to the template isn't documented -- but
it's a filtered version of whatever CppHeaderParser outputs when it parses a
header.

See the examples folder for more examples.

Batch mode
----------

If you need to process multiple files, or just want to record the parameters for
autogenerating a file without writing a shell script, batch mode is useful. You
pass two parameters: a yaml file with the configuration, and an output directory
to write the files to.


Using data from external sources
--------------------------------

Sometimes you want to mix in data that CppHeaderParser can't give you. If you
pass the ``--yaml`` option, it will load the yaml into a dictionary and make it
available to the template as the 'data' variable.

You can also pass key=value parameters via the ``--param`` option, and
the specified keys will be available to the template.

Custom processing
-----------------

When you need to do more complex logic that a jinja2 template just isn't
appropriate for, you can specify a python file to load custom hooks from.

See [the default hooks](header2whatever/default_hooks.py) for documentation.

License
=======

Apache 2

Author
======

Dustin Spicuzza (dustin@virtualroadside.com)
