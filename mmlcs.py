# mmlcs.py
# Trevor Pottinger
# Tue May 12 22:56:34 PDT 2015

from __future__ import print_function

# stdlib imports
import argparse
import glob
import json
import multiprocessing
import os
import struct
import sys
import time

# local imports
from extractors import (ngrams, substrings)
from filefuncs import (simpleFunc, multiFunc)
from sorting import (mergeSort, multiMergeSort)

DEBUG = False
ENABLE_MULTICORE = True
NUM_CORES = multiprocessing.cpu_count()
NGRAMS_DEFAULT = 3
OUTPUT_FORMAT_DEFAULT = 'tsv'

def __hist_cmp(x, y):
  if x[1] > y[1]:
    return 1
  elif x[1] < y[1]:
    return -1
  else:
    return 0

def __substr_hist_cmp(x, y):
  # how many occurances
  if x[1] > y[1]:
    return 1
  elif x[1] < y[1]:
    return -1
  else:
    # length of substrs
    if len(x[0]) > len(y[0]):
      return 1
    elif len(x[0]) < len(y[0]):
      return -1
    else:
      return 0

def sortedHist(hist, minT=0):
  "Actually returns a sorted list of (key, value) tuples"
  tuples = hist.items()
  if minT > 0:
    tuples = filter(lambda kvtuple: kvtuple[1] > minT, tuples)
  # True implies reverse=True, aka DESCENDING
  return mergeSort(tuples, __hist_cmp, True)

def sortedSubstrHist(hist, minT=0):
  tuples = hist.items()
  if minT > 0:
    tuples = filter(lambda kvtuple: kvtuple[1] > minT, tuples)
  # True implies reverse=True, aka DESCENDING
  return mergeSort(tuples, __substr_hist_cmp, True)

def multiSortedHist(hist, minT=0):
  "This seems to be memory bound :("
  tuples = hist.items()
  if minT > 0:
    tuples = filter(lambda kvtuple: kvtuple[1] > minT, tuples)
  # True implies reverse=True, aka DESCENDING
  return multiMergeSort(tuples, __hist_cmp, True)

def topKHist(tuples, k):
  "Expects tuples to be sorted (key, value) tuples, lowest first"
  ret = {}
  for i in range(k):
    ret[tuples[-i][0]] = tuples[-i][1]
  return ret

def bin2hex(s):
  return ''.join( ("%02x" % ord(c) for c in s) )

def hex2bin(s):
  binstr = ''
  for i in range(0, len(s), 2):
    # don't use += to be explicit about ordering
    binstr = binstr + struct.pack('B', int(s[i:i+2], 16))
  return binstr

def prettyhist(hist):
  "Expects a histogram where the keys are bytestrings"
  ret = {}
  for gram in hist:
    hexgram = bin2hex(gram)
    ret[hexgram] = hist[gram]
  return ret

def percentiles(ns, k):
  "Expects a list of integers and the number of percentiles"
  assert len(ns) > k, 'There must be more integers than k: %d <= %d' % (len(ns), k)
  # TODO expects ns to be sorted
  ret = []
  # TODO len(ns) / k is not the correct step size
  # I'd expect len(ret) == k + 1, but it's not
  for i in range(0, len(ns), len(ns) / k):
    ret.append(ns[i])
  ret.append(ns[-1])
  return ret

def main(path_regex, outfile, outformat, use_multi, N, verbosity):
  start = time.time()
  filenames = glob.glob(path_regex)
  print("Running mmlcs on %d files using %d cores looking for %d-grams" % (
    len(filenames),
    NUM_CORES if use_multi else 1,
    N
  ))
  # TODO we could probably select a set instead of a histogram per file
  if not use_multi:
    (_, _, common_ngrams) = simpleFunc(
      (filenames, ngrams, [N])
    )
  else:
    (_, _, common_ngrams) = multiFunc(
      (filenames, ngrams, [N])
    )
  now = time.time()
  print("[+] Reading %d files complete; time elapsed: %1.3f" % (len(filenames), now - start))
  start = now
  # note that the following functions currently take a histogram and return
  #  a sorted list of (ngram, count) tuples
  if not use_multi or True:
    # SLOW because common_ngrams gets huge
    sorted_common_ngrams = sortedHist(common_ngrams, 1)
  else:
    # multi core sorting doesn't work yet...
    sorted_common_ngrams = multiSortedHist(common_ngrams, 1)
  now = time.time()
  print("[+] Sorting %d ngrams complete; time elapsed: %1.3f" % (len(sorted_common_ngrams), now - start))
  start = now
  # RFC does top 25% make sense?
  top_k_index = len(sorted_common_ngrams) / 4
  top_common_ngram_set = set(map(
    lambda kvtuple: kvtuple[0],
    sorted_common_ngrams[:top_k_index]
  ))
  if not use_multi:
    # RFC we're ignoring the count of distinct substrings
    (_, _, common_substrings) = simpleFunc(
      (filenames, substrings, [N, top_common_ngram_set])
    )
  else:
    (_, _, common_substrings) = multiFunc(
      (filenames, substrings, [N, top_common_ngram_set])
    )
  now = time.time()
  print("[+] Extracting %d substrings complete; time elapsed: %1.3f" % (len(common_substrings), now - start))
  start = now
  if not use_multi or True:
    if N == 2:
      print("[-] WARNING: n=2 for the following function sometimes resulted in []")
    # This shouldn't be too slow since its sample size is much smaller than above
    # Note that this returns a sorted list of (substring, count) tuples
    sorted_common_substrings = sortedSubstrHist(common_substrings, 1)
  else:
    # TODO multicore substr sorting
    sorted_common_substrings = sortedSubstrHist(common_substrings, 1)
  now = time.time()
  print("[+] Sorting %d substrings complete; time elapsed: %1.3f" % (len(sorted_common_substrings), now - start))
  start = now
  pretty_common_substrings_raw = map(
    lambda kvtuple: (bin2hex(kvtuple[0]), kvtuple[1]),
    sorted_common_substrings
  )
  if outfile is not None:
    assert outformat is not None, 'outformat should never be None'
    with open(outfile, 'w') as f:
      print("[+] Writing %d substrings and counts to %s" % (len(sorted_common_substrings), outfile))
      if outformat == 'json':
        f.write("%s\n" % pretty_common_substrings_raw)
      elif outformat == 'tsv':
        for kvtuple in pretty_common_substrings_raw:
          f.write("%s\t%s\n" % (kvtuple[0], kvtuple[1]))
      else:
        print("Unknown output format %s" % outformat)
  else:
    # no stored output, so lets print some stuff to stdout
    print("Count\tLength\tPreview")
    # TODO allow for more than the top 10 common substrings?
    for kvtuple in pretty_common_substrings_raw[:10]:
      # note: divide length by 2 since it's hex..
      # TODO allow for different preview lengths?
      print("%d\t%d\t%s" % (kvtuple[1], len(kvtuple[0]) / 2, kvtuple[0][:30]))
  return

def validateInput(args):
  # input directory
  if args.input_dir is None:
    raise Exception('input_dir is needed')
  elif not os.path.isdir(args.input_dir):
    raise Exception("%s is not a directory" % args.input_dir)
  else:
    input_dir = "%s/*" % args.input_dir
  # output file
  if args.output is not None and not os.path.exists(args.output):
    output = args.output
  elif args.output is not None and os.path.isdir(args.output):
    raise Exception("%s is a directory, can't write to it" % args.output)
  elif args.output is None:
    output = None
  else:
    # TODO verify output file is writable
    print("[-] WARNING: Don't know what to do with %s, #doitlive" % args.output)
    output = args.output
  # output format
  if args.format is None:
    output_format = OUTPUT_FORMAT_DEFAULT
  elif args.format.lower() == 'json':
    output_format = 'json'
  elif args.format.lower() == 'tsv':
    output_format = 'tsv'
  else:
    print("[-] WARNING: Unknown output format %s, assuming json" % args.format)
    output_format = OUTPUT_FORMAT_DEFAULT
  # verbosity
  if args.verbose is None:
    verbosity = 0
  else:
    # action='count' implies the value will be an integer
    verbosity = args.verbose
  if args.n is None:
    N = NGRAMS_DEFAULT
  else:
    N = args.n
  return (input_dir, output, output_format, args.multi, N, verbosity)

if __name__ == '__main__':
  # TODO argparse
  parser = argparse.ArgumentParser(
    description='Approximates longest common substring'
  )
  parser.add_argument(
    'input_dir',
    help='Where the data files are stored that should be read'
  )
  parser.add_argument('-o', '--output', help='Where to store the results')
  parser.add_argument(
    '-f',
    '--format',
    help='How the output should be formated. TSV or JSON'
  )
  parser.add_argument(
    '-m',
    '--multi',
    action='store_true',
    help='Toggles whether or not to use multiple cores'
  )
  parser.add_argument('-n', help='The value of n for n-grams', type=int)
  parser.add_argument('-v', '--verbose', action='count')
  (input_dir_regex, output, outformat, use_multi, n, verbosity) = validateInput(
    parser.parse_args()
  )
  main(input_dir_regex, output, outformat, use_multi, n, verbosity)
