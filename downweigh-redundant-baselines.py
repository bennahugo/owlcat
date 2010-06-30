#!/usr/bin/python
# -*- coding: utf-8 -*-

import sys
import os.path
import re
import time
import math
import Owlcat

ROWCHUNK = 50000;

time_start = time.time();

try:
  from pyrap_tables import table,tablecopy,tableexists,tabledelete
except:
  from pyrap.tables import table,tablecopy,tableexists,tabledelete

def timestamp (format="%H:%M:%S:"):
  return time.strftime(format,time.gmtime(time.time()-time_start));

def progress (message,newline=True):
  sys.stdout.write("%s %-60s%s"%(timestamp(),message,'\n' if newline else '\r'));
  sys.stdout.flush();

if __name__ == "__main__":

  # setup some standard command-line option parsing
  #
  from optparse import OptionParser
  parser = OptionParser(usage="""%prog: [options] MS""",
      description="""Finds redundant baselines and modifies the IMAGING_WEIGHT column of the MS,
reweighting the redundant baselines by 1/n. This compensates for the lack of this option
in the casa imager. For proper treatment of redundant baselines in e.g. WSRT, first make
an image using radial weighting (so that the imager fills in the IMAGING_WEIGHT column
appropriately), then run this script to modify the weights, then run the imager again, but
this time tell it to use the default weights.""");
  #parser.add_option("-o","--output",dest="output",type="string",
                    #help="name of output FITS file");
  #parser.add_option("-z","--zoom",dest="output_quad",type="string",
                    #help="name of zoomed output FITS file");
  parser.add_option("-t","--tolerance",dest="tolerance",type="float",
                    help="How close (in meters) two baselines need to be to each other to be considered redundant (default .1)");
  parser.add_option("-I","--ifrs",dest="ifrs",type="string",
                    help="subset of interferometers to use.");
  parser.add_option("-s","--select",dest="select",action="store",
                    help="additional TaQL selection string. Note that redundant baselines are counted only within the subset "
                         "given by the --ifrs and --select options.");
  parser.set_defaults(tolerance=.1,select="",ifrs="");

  (options,msnames) = parser.parse_args();

  if len(msnames) != 1:
    parser.error("MS name not supplied.");

  msname = msnames[0];
  ms = table(msname,readonly=False);

  taqls = [];
  # get IFR set
  import Meow.IfrSet
  ifrset = Meow.IfrSet.from_ms(ms);
  if options.ifrs:
    ifrset = ifrset.subset(options.ifrs);
    taqls.append(ifrset.taql_string());

  if options.select:
    taqls.append(options.select);

  if taqls:
    select = "( " + " ) &&( ".join(taqls) + " )";
    progress("Applying TaQL selection %s"%select,newline=True);
    ms = ms.query(select);
  progress("Looking for redundant baselines",newline=True);
  ant1 = ms.getcol('ANTENNA1');
  ant2 = ms.getcol('ANTENNA2');

  IFRS = sorted(set([ (p,q) for p,q in zip(ant1,ant2) ]));
  print "%d baselines"%len(IFRS);
  groups = [];

  for i,(p,q) in enumerate(IFRS):
    bl = ifrset.baseline_vector(p,q);
    # see if this baseline is within the tolerance of a previous group's baseline
    for ig,(bl0,members) in enumerate(groups):
      if abs(bl-bl0).max() < options.tolerance:
        members.append((p,q));
        break;
    # if none, start a new group
    else:
      members = [(p,q)];
      ig = len(groups);
      groups.append([]);
    # update baseline (as mean baseline of group)
    length = reduce(lambda x,y:x+y,[ifrset.baseline_vector(*ifr) for ifr in members])/len(members);
    groups[ig] = (length,members);

  # make a dictionary of per-IFR weights
  have_redundancy = False;
  weight = dict([((p,q),1.) for p,q in IFRS]);
  for baseline,members in sorted(groups,lambda a,b:cmp((a[0]**2).sum(),(b[0]**2).sum())):
    if len(members) > 1:
      print "Baseline %dm, %d ifrs: %s"%(round(math.sqrt((baseline**2).sum())),len(members),
        " ".join(["%d-%d"%(p,q) for p,q in members]));
      have_redundancy = True;
      for p,q in members:
        weight[p,q] = 1.0/len(members);
  if not have_redundancy:
    print "No redundant baselines found, nothing to do."
    sys.exit(0);

  # apply weights
  nrows = ms.nrows();
  for row0 in range(0,nrows,ROWCHUNK):
    progress("Applying weights, row %d of %d"%(row0,nrows),newline=False);
    row1 = min(nrows,row0+ROWCHUNK);
    w = ms.getcol('IMAGING_WEIGHT',row0,row1-row0);
    for i in range(row0,row1):
      w[i-row0,:] *= weight[ant1[i],ant2[i]];
    ms.putcol('IMAGING_WEIGHT',w,row0,row1-row0);

  progress("Closing MS.");
  ms.close();