from Pyxis.ModSupport import *

import tempfile

# register ourselves with Pyxis, and define the superglobals
register_pyxis_module();

v.define("OUTDIR","",
  """base output directory""");
v.define("DESTDIR_Template",'${OUTDIR>/}plots-${MS:BASE}-spw${DDID}',
  """destination directory for plots, images, etc.""");
v.define("OUTFILE_Template",'${DESTDIR>/}${MS:BASE}${_spw<DDID}${_s<STEP}${_<LABEL}',
  """base output filename for plots, images, etc.""");
v.define("STEP",1,
  """step counter, automatically incremented. Useful for decorating filenames.""")
v.define("LABEL","",
  """decorative label, mainly used for decorating filenames.""")
  
remove          = xo.rm.args("-fr");
copy            = x.cp.args("-a");
plotparms       = x("plot-parms.py").args("$PLOTPARMS_ARGS");
fitstool        = x("fitstool.py");

casapy = x.casapy.args("--nologger --log2term -c");

def runcasapy (command):
  command = interpolate_locals("command");
  # write command to script file
  tf = tempfile.NamedTemporaryFile(suffix=".py");
  tf.write(command+"\nexit\n");
  tf.flush();
  tfname = tf.name;
  # run casapy
  info("Running casapy $tfname");
  casapy(tfname);
  tf.close();


