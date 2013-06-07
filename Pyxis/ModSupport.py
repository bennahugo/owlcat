"""Pyxis.ModSupport: functions for programming Pyxides modules"""

import fnmatch    

import Pyxis
from Pyxis import *

from Pyxis.Commands import _verbose,_warn,_abort
from Pyxis.Internals import _superglobals,_namespaces,_modules

def makedir (dirname,no_interpolate=False):
  """Makes sure the supplied directory exists, by creating parents as necessary. Interpolates the dirname.""";
  if not no_interpolate:
    dirname = interpolate(dirname,inspect.currentframe().f_back);
  parent = dirname;
  # go back and accumulate list of dirs to be created
  parents = [];
  while parent and not os.path.exists(parent):
    parents.append(parent);
    parent = os.path.dirname(parent);
  # create in reverse
  for parent in parents[::-1]:
    verbose(1,"creating directory %s"%parent);
    os.mkdir(parent);
  
def register_pyxis_module (superglobals=""):
  """Registers a module (the callee) as part of the Pyxis environment.
  'superglobals' can be a list of super-global variables defined by the module.
  Superglobals are propagated across all modules that register for them.
  It is also possible to generate them as v.define() instead.""";
  frame = inspect.currentframe().f_back;
  globs = frame.f_globals;
  # check for double registration
  if id(globs) in _superglobals:
    raise RuntimeError,"module '%s' is already registered"%modname;
  modname = globs['__name__'];
  _modules.add(modname);
  if modname.startswith("Pyxides."):
    modname = modname.split(".",1)[-1];
  # build list of superglobals
  if isinstance(superglobals,str):
    superglobs = superglobals.split();
  else:
    superglobs = itertools.chain(*[ x.split() for x in superglobals ]);
  superglobs = set(superglobs);
  _verbose(1,"registered module '%s'"%modname);
  _namespaces[modname] = globs;
  _superglobals[id(globs)] = superglobs;
  # add superglobals
  for sym in superglobs:
    # if superglobal is already defined, copy its value to the new module
    # if superglobal was not yet defined, get its value form the module (or use None),
    # and propagate this value super-globally via assign
    if sym in Pyxis.Context:
      globs[sym] = Pyxis.Context[sym];
    else:
      assign(sym,globs.get(sym,None),namespace=Pyxis.Context,frame=frame)
  # report 
  Pyxis.Internals.report_symbols(modname,superglobs,
      [ (name,obj) for name,obj in globs.iteritems() if not name.startswith("_") and name not in Pyxis.Commands.__dict__ and name not in superglobs ]);
      
def def_global (name,default,doc=None):
  """Defines a module global with the given name, default value and documentation string.
  Mainly useful in Pyxides modules, to provide documentation on their globals.
  At module level, calling def_global('NAME',value,doc) is equivalent to
      NAME = value
      _doc_NAME = doc
  """;
  globs = inspect.currentframe().f_back.f_globals;
  globs[name] = default;
  if name.endswith("_Template"):
    name = name[:-9];
  globs.setdefault("_symdocs",{})[name] = doc;

    
def document_globals (obj,*patterns):
  """Updates an object's documentation string with a list of globals that match the specified patterns.
  Mainly useful in Pyxides modules, to form documentation strings for functions, e.g.:
  
    def_global(FOO_A,"1","option A for function foo");
    def_global(FOO_B,"2","option B for function foo");
    
    def foo ():
      # uses FOO_A and FOO_B
    
    document_globals(foo,"FOO_*");
    
  This results in foo.__doc__ being extended with documentation for FOO_A and FOO_B
  """
  globs = inspect.currentframe().f_back.f_globals;
  modname = globs['__name__'];
  moddocs = globs.get('_symdocs',{});
  globdocs = Pyxis.Context.get('_symdocs',{});
  # make set of all global symbols, plus symbols that may not yet be defined, but already have documentation,
  # plus superglobals
  allsyms = set(globs.iterkeys());
  allsyms.update(moddocs.iterkeys());
  # keep track of what's been documented, to avoid duplicates
  documented = set();
  doclist = [];
  for patt in patterns:
    # if patt matches a superglobal exactly, add to list
    if Pyxis.Internals.is_superglobal(globs,patt):
      doclist += [ ("v."+patt,globdocs.get(patt,'')) ];
    # else look for matching module-level globals
    else:
      # make sorted list of matching module globals for each pattern
      syms = sorted([ sym for sym in allsyms if fnmatch.fnmatch(sym,patt) and not sym.endswith("_Template") ]);
      # add them to doclist
      doclist += [ ("%s.%s"%(modname,sym),moddocs.get(sym,'')) for sym in syms if sym not in documented ];
      # add them to set of already documented syms
      documented.update(syms);
  # now generate documentation string
  if doclist:
    text = "\nThe following variables also apply:\n\n"
    for sym,doc in doclist:
      text += "  %-20s %s\n"%(sym,doc);
    obj.__doc__ = obj.__doc__ + text;
  
def interpolate_locals (*varnames):
  """interpolates the variable names (from the local context) given by its argument(s).
  Returns new values in the order given. Useful as the opening line of a function, for example:
  
  def f(a="$A",b="$a.1"):
    a,b = interpolate_locals("a b")   # can also be specified as "a","b"
    
  will assign the global variable A to a, and the value of a (in this case, the value of A) plus ".1" to b.
  """;
  ## NB: the rationale for implementing it like this, as opposed to directly manipulating f_locals
  ## of the caller frame, is because f_locals of the caller can be read-only depending on Python implementation.
  Pyxis.Internals.assign_templates();
  # interpolate the whole locals() dict
  frame = inspect.currentframe().f_back;
  locs = interpolate(frame.f_locals,frame,depth=2);
  # return variables in the order listed
  ret = [ locs.get(name) for name in itertools.chain(*[ v.split(" ") for v in varnames ]) ];
  return ret if len(ret) != 1 else ret[0];
    