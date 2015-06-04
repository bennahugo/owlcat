#!/usr/bin/python
# -*- coding: utf-8 -*-

#
#% $Id$
#
#
# Copyright (C) 2002-2011
# The MeqTree Foundation &
# ASTRON (Netherlands Foundation for Research in Astronomy)
# P.O.Box 2, 7990 AA Dwingeloo, The Netherlands
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, see <http://www.gnu.org/licenses/>,
# or write to the Free Software Foundation, Inc.,
# 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#

import sys
import re
import os.path
import numpy
## ugly hack to get around UGLY FSCKING ARROGNAT (misspelling fully intentional) pyfits-2.3 bug
import Kittens.utils
pyfits = Kittens.utils.import_pyfits();
import scipy.ndimage.measurements
import math

SANITIZE_DEFAULT = 12345e-7689


def stack_planes(fitslist, outfile='combined.fits', axis=0, ctype=None, keep_old=False, fits=False):
    """ Stack a list of fits files along a given axiis.
       
       fitslist: list of fits file to combine
       outfile: output file name
       axis: axis along which to combine the files
       fits: If True will axis FITS ordering axes
       ctype: Axis label in the fits header (if given, axis will be ignored)
       keep_old: Keep component files after combining?
    """

    hdu = pyfits.open(fitslist[0])[0]
    hdr = hdu.header
    naxis = hdr['NAXIS']

    # find axis via CTYPE key
    if ctype is not None:
        for i in range(1,naxis+1):
            if hdr['CTYPE%d'%i].lower().startswith(ctype.lower()):
                axis = naxis - i # fits to numpy convention
    elif fits:
      axis = naxis - axis

    fits_ind = abs(axis-naxis)
    crval = hdr['CRVAL%d'%fits_ind]

    imslice = [slice(None)]*naxis
    _sorted = sorted([pyfits.open(fits) for fits in fitslist],
                    key=lambda a: a[0].header['CRVAL%d'%(naxis-axis)])

    # define structure of new FITS file
    nn = [ hd[0].header['NAXIS%d'%(naxis-axis)] for hd in _sorted]
    shape = list(hdu.data.shape)
    shape[axis] = sum(nn)
    data = numpy.zeros(shape,dtype=float)

    for i, hdu0 in enumerate(_sorted):
        h = hdu0[0].header
        d = hdu0[0].data
        imslice[axis] = range(sum(nn[:i]),sum(nn[:i+1]) )
        data[imslice] = d
        if crval > h['CRVAL%d'%fits_ind]:
            crval =  h['CRVAL%d'%fits_ind]

    # update header
    hdr['CRVAL%d'%fits_ind] = crval
    hdr['CRPIX%d'%fits_ind] = 1

    pyfits.writeto(outfile,data,hdr,clobber=True)
    print("Successfully stacked images. Output image is %s"%outfile)

    # remove old files
    if not keep_old:
        for fits in fitslist:
            os.system('rm -f %s'%fits)


def unstack_planes(fitsname, each_chunk, axis=None, ctype=None, prefix=None,fits=False):
    """ 
        Unstack FITS image along a given axis into multiple 
        images each having each_chunk planes along that axis 
    """

    prefix = prefix or fitsname[:-5] # take everthing but .FITS/.fits
    hdu = pyfits.open(fitsname)
    hdr = hdu[0].header
    data = hdu[0].data.copy()
    naxis = hdr["NAXIS"]

    if axis is None and ctype is None:
        raise SystemExit('Please specify either axis or ctype')
    # find axis via CTYPE key

    if ctype :
        for i in range(1,naxis+1):
            if hdr['CTYPE%d'%i].lower().startswith(ctype.lower()):
                axis = naxis - i # fits to numpy indexing
    elif fits:
      axis = naxis - axis

    crval = hdr['CRVAL%d'%(naxis-axis)]
    cdelt = hdr['CDELT%d'%(naxis-axis)]
    crpix = hdr['CRPIX%d'%(naxis-axis)]
    # shift crval to crpix=1
    crval = crval - (crpix-1)*cdelt

    nstacks = hdr['NAXIS%d'%(naxis-axis)]
    nchunks = nstacks//each_chunk
    print("The FITS file %s has %s stacks along this axis. Breaking it up to %d images"%(fitsname, nstacks, nchunks))

    outfiles = []
    for i in range(0, nchunks):

        _slice = [slice(None)]*naxis
        _slice[axis] = range(i*each_chunk, (i+1)*each_chunk if i+1!=nchunks else nstacks)
        hdu[0].data = data[_slice]
        hdu[0].header['CRVAL%d'%(naxis-axis)] = crval + i*cdelt*each_chunk
        hdu[0].header['CRPIX%d'%(naxis-axis)] = 1
        outfile = '%s-%04d.fits'%(prefix, i)
        outfiles.append(outfile)
        print("Making chunk %d : %s. File is %s"%(i, repr(_slice[axis]), outfile))
        hdu.writeto(outfile, clobber=True)
    hdu.close()
    return outfiles


def swap_stokes_freq(fitsname, last="STOKES", outfile=None):
    """ Swap order of STOKES and FREQ planes in FITS image. Input FITS image must have 4 dimensions """

    # Get to know input FITS image
    hdu = pyfits.open(fitsname)
    hdr0 = hdu[0].header
    ndim = hdr0["NAXIS"]
    if ndim!=4:
        raise TypeError("ABORTING: FITS file does not have 4 dimensions. Je suis confused. ")

    # Check ordering before we do anything
    _last = hdr0["CTYPE4"].lower()
    if _last == last.lower():
        print("FITS Image already has the desired ordering of FREQ/STOKES axes")
        hdu.close()
        return

    # Ok, Lock and Load
    data = hdu[0].data
    # First re-order data
    hdu[0].data = numpy.rollaxis(data,1)

    hdr = hdr0.copy()
    mendatory = "CTYPE CRVAL CDELT CRPIX".split()
    optional = "CUNIT CROTA".split()

    for key in mendatory+optional:
        try:
            hdr["%s%d"%(key,3)] = hdr0["%s%d"%(key,4)]
            hdr["%s%d"%(key,4)] = hdr0["%s%d"%(key,3)]
        except KeyError: 
            if key in mendatory:
                raise KeyError("ARBORTNG: FITS file doesn't have the '%s' key in the header"%key)
            else:
                pass

    hdu[0].header = hdr
    outfile = outfile or "swapped_"+fitsname
    print("Successfully swapped FREQ and STOKES axes in FITS image. Output image is at %s"%outfile)
    hdu.writeto(outfile, clobber=True)
    

if __name__ == "__main__":

  # setup some standard command-line option parsing
  #
  from optparse import OptionParser
  parser = OptionParser(usage="""%prog: [options] <image names...>""");
  parser.add_option("-o","--output",dest="output",type="string",
                    help="name of output FITS file");
  parser.add_option("-r","--replace",action="store_true",
                    help="replace (first) input file by output. Implies '--force'.");
  parser.add_option("-f","--force",dest="force",action="store_true",
                    help="overwrite output file even if it exists");
  parser.add_option("-S","--sanitize",type="float",metavar="VALUE",
                    help="sanitize FITS files by replacing NANs and INFs with VALUE");
  parser.add_option("-N","--nonneg",action="store_true",
                    help="replace negative values by 0");
  parser.add_option("-m","--mean",dest="mean",action="store_true",
                    help="take mean of input images");
  parser.add_option("-d","--diff",dest="diff",action="store_true",
                    help="take difference of 2 input images");
  parser.add_option("-t","--transfer",action="store_true",
                    help="transfer data from image 2 into image 1, preserving the FITS header of image 1");
  parser.add_option("-z","--zoom",dest="zoom",type="int",metavar="NPIX",                    
                    help="zoom into central region of NPIX x NPIX size");
  parser.add_option("-R","--rescale",dest="rescale",type="float",
                    help="rescale image values");
  parser.add_option("-E","--edit-header",metavar="KEY=VALUE",type="string",action="append",
                    help="replace header KEY with VALUE. Use KEY=VALUE for floats and KEY='VALUE' for strings.");
  parser.add_option("--stack",metavar="outfile:axis",
                    help="Stack a list of FITS images along a given axis. This axis may given as an integer"
                    "(as it appears in the NAXIS keyword), or as a string (as it appears in the CTYPE keyword)")
  parser.add_option("--swap",metavar="LAST_AXIS",
                    help="Which axis do want to be last")
  parser.add_option("--unstack",metavar="prefix:axis:each_chunk",
                    help="Unstack a FITS image into smaller chunks each having [each_chunk] planes along a given axis. "
                    "This axis may given as an integer (as it appears in the NAXIS keyword), or as a string "
                    "(as it appears in the CTYPE keyword)")
  parser.add_option("-H","--header",action="store_true",help="print header(s) of input image(s)");
  parser.add_option("-s","--stats",action="store_true",help="print stats on images and exit. No output images will be written.");

  parser.set_defaults(output="",mean=False,zoom=0,rescale=1,edit_header=[]);

  (options,imagenames) = parser.parse_args();
  
  if not imagenames:
    parser.error("No images specified. Use '-h' for help.");

  # print "%d input image(s): %s"%(len(imagenames),", ".join(imagenames));
  images = [ pyfits.open(img) for img in imagenames ];
  updated = False;

  # Stack FITS images
  if options.stack:
    if len(imagenames)<1:
      parser.error("Need more than one image to stack")
    stack_args = options.stack.split(":")
    if len(stack_args) != 2:
      parser.error("Two --stack options are required. See ./fitstool.py -h")
   
    outfile,axis = stack_args

    _string = True
    try:
      axis = int(axis)
      _string = False
    except ValueError:
      _string = True

    stack_planes(imagenames,ctype=axis if _string else None,keep_old=True,
                 axis=None if _string else axis,outfile=outfile,fits=True)
    sys.exit(0)
  
  # Unstack FITS image
  if options.unstack:
    image = imagenames[0]
    if len(imagenames)<1:
      parser.error("Need more than one image to stack")
    unstack_args = options.unstack.split(":")
    if len(unstack_args) != 3:
      parser.error("Two --unstack options are required. See ./fitstool.py -h")

    prefix,axis,each_chunk = unstack_args
    
    _string = True
    try:
      axis = int(axis)
      _string = False
    except ValueError:
      _string = True

    each_chunk = int(each_chunk)
    
    unstack_planes(image,each_chunk,ctype=axis if _string else None,
            axis=None if _string else axis,prefix=prefix,fits=False)
    sys.exit(0)

  if options.swap:
    for image in imagenames:
      swap_stokes_freq(image,last=options.swap)
      updated = True
  
  if options.header:
    for filename,img in zip(imagenames,images):
      if len(imagenames)>1:
        print "======== FITS header for",filename;
      for hdrline in img[0].header.ascard:
        print hdrline; 
  
  if options.replace or len(imagenames)<2:
    if options.output:
      parser.error("Cannot combine -r/--replace with -o/--output");
    outname = imagenames[0];
    options.force = True;
    autoname = False;
  else:
    outname = options.output;
    autoname = not outname;
    if autoname:
      outname = re.split('[_]',imagenames[0],1)[-1];

  for keyval in options.edit_header:
    key,val = keyval.split("=");
    q = ''
    if val[0] == "'" and val[-1] == "'":
      images[0][0].header[key] = val[1:-1:];
      q = '"'
    elif val[-1] == 'd' or key.startswith('NAXIS'):
      images[0][0].header[key] = int(val[:-1] if val[-1]=='d' else val);
    else:
      try:
        images[0][0].header[key] = float(val);
      except:
        images[0][0].header[key] = val;
        q = '"';
    print "Setting header %s=%s%s%s"%(key,q,val,q);
    updated = True;

  if options.sanitize is not None:
    print "Sanitizing: replacing INF/NAN with",options.sanitize;
    for img in images:
      d = img[0].data;
      d[numpy.isnan(d)+numpy.isinf(d)] = options.sanitize;
    # if using stats, do not generate output
    if not options.stats:
      updated = True;

  if options.nonneg:
    print "Replacing negative value by 0";
    for img,name in zip(images,imagenames)[:1]:
      d = img[0].data;
      wh = d<0;
      d[wh] = 0;
      print "Image %s: replaced %d points"%(name,wh.sum());
    updated = True;

  if options.transfer:
    if len(images) != 2:
      parser.error("The --transfer option requires exactly two input images.");
    if autoname:
      outname = "xfer_" + outname;
    print "Transferring %s into coordinate system of %s"%(imagenames[1],imagenames[0]);
    images[0][0].data[...] = images[1][0].data;
    updated = True;
  elif options.diff:
    if len(images) != 2:
      parser.error("The --diff option requires exactly two input images.");
    if autoname:
      outname = "diff_" + outname;
    print "Computing difference";
    data = images[0][0].data;
    data -= images[1][0].data;
    updated = True;
  elif options.mean:
    if autoname:
      outname = "mean%d_"%len(images) + outname;
    print "Computing mean";
    data = images[0][0].data;
    for img in images[1:]:
      data += img[0].data;
    data /= len(images);
    images = [ images[0] ];
    updated = True;

  if options.zoom:
    z = options.zoom;
    if autoname:
      outname = "zoom%d_"%z + outname;
    if len(images) > 1:
      "Too many input images specified for this operation, at most 1 expected";
      sys.exit(2);
    data = images[0][0].data;
    nx = data.shape[2];
    ny = data.shape[3];
    zdata = data[:,:,(nx-z)/2:(nx+z)/2,(ny-z)/2:(ny+z)/2];
    print "Making zoomed image of shape","x".join(map(str,zdata.shape));
    images = [ pyfits.PrimaryHDU(zdata) ];
    updated = True;

  if options.rescale != 1:
    if autoname and not updated:
      outname = "rescale_" + outname;
    if len(images) > 1:
      "Too many input images specified for this operation, at most 1 expected";
      sys.exit(2);
    print "Applying scaling factor of %f to image values"%options.rescale;
    images[0][0].data *= options.rescale;
    updated = True;

  if updated:
    imagenames[0] = outname;

  if options.stats:
    for ff,filename in zip(images,imagenames):
      data = ff[0].data;
      min,max,dum1,dum2 = scipy.ndimage.measurements.extrema(data);
      sum = data.sum();
      mean = sum/data.size;
      std = math.sqrt(((data-mean)**2).mean());
      print "%s: min %g, max %g, sum %g, np %d, mean %g, std %g"%(filename,min,max,sum,data.size,mean,std); 
    sys.exit(0);
      
  if updated:
    print "Writing output image",outname;
    if os.path.exists(outname) and not options.force:
      print "Output image exists, rerun with the -f switch to overwrite.";
      sys.exit(1);
    images[0].writeto(outname,clobber=True);
  elif not (options.header or options.stack or options.unstack):
    print "No operations specified. Use --help for help."
