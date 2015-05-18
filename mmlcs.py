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
  if not use_multi:
    (lens, count_distinct_ngrams, common_ngrams) = simpleFunc(
      (filenames, ngrams, [N])
    )
  else:
    (lens, count_distinct_ngrams, common_ngrams) = multiFunc(
      (filenames, ngrams, [N])
    )
  now = time.time()
  print("[+] Reading %d files complete; time elapsed: %1.3f" % (len(lens), now - start))
  start = now
  # not slow because their len is the number of samples
  lens.sort(reverse=True)
  count_distinct_ngrams.sort(reverse=True)
  if not use_multi or True:
    # SLOW +1 because common_ngrams gets huge
    sorted_common_ngrams = sortedHist(common_ngrams)
  else:
    sorted_common_ngrams = multiSortedHist(common_ngrams)
  # these next three are really just for pretty printing
  # begin can this be removed?
  sorted_duplicated_common_ngrams = filter(lambda kvtuple: kvtuple[1] > 1, sorted_common_ngrams)
  pretty_common_ngrams = map(lambda kvtuple: (bin2hex(kvtuple[0]), kvtuple[1]), sorted_common_ngrams)
  pretty_duplicated_ngrams = map(lambda kvtuple: (bin2hex(kvtuple[0]), kvtuple[1]), sorted_duplicated_common_ngrams)
  now = time.time()
  print("[+] Sorting distinct ngrams complete; time elapsed: %1.3f" % (now - start))
  start = now
  # end can this be removed?
  # TODO how do we pick 30?
  top_common_ngram_set = set(map(lambda kvtuple: kvtuple[0], filter(lambda kvtuple: kvtuple[1] > 30, sorted_common_ngrams)))
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
    print("[-] WARNING: n=2 for the following function sometimes resulted in []")
    # This shouldn't be too slow since its sample size is much smaller than above
    # Note that this returns a list of (substring, count) tuples
    sorted_common_substrings = sortedSubstrHist(common_substrings, 1)
  else:
    # TODO
    sorted_common_substrings = sortedSubstrHist(common_substrings, 1)
  # TODO don't take the first 40 bytes...
  pretty_common_substrings = map(lambda kvtuple: (bin2hex(kvtuple[0][:40]), kvtuple[1]), sorted_common_substrings)
  pretty_common_substrings_raw = map(lambda kvtuple: (bin2hex(kvtuple[0]), kvtuple[1]), sorted_common_substrings)
  substring_lens = map(lambda kvtuple: len(kvtuple[0]), sorted_common_substrings)
  substring_lens.sort(reverse=True)
  now = time.time()
  print("[+] Sorting distinct substrings complete; time elapsed: %1.3f" % (now - start))
  start = now
  if outfile is not None:
    assert outformat is not None, 'outformat should never be None'
    f = open(outfile, 'w')
    if outformat == 'json':
      print("[+] Writing output to %s" % (outfile))
      f.write("%s\n" % pretty_common_substrings_raw)
    elif outformat == 'tsv':
      for kvtuple in pretty_common_substrings_raw:
        f.write("%s\t%s\n" % (kvtuple[0], kvtuple[1]))
    else:
      print("Unknown output format %s" % outformat)
    f.close()
  print("\tLength percentiles: %s" % (json.dumps(percentiles(lens, 15))))
  print("\tDistinct ngram percentiles: %s" % (json.dumps(percentiles(count_distinct_ngrams, 15))))
  #print("\tTop K ngrams: %s" % (json.dumps(prettyhist(topKHist(sorted_common_ngrams, 80)))))
  print("\tShared ngram percentiles: %s" % (json.dumps(percentiles(pretty_common_ngrams, 15))))
  print("\tShared ngram (>1) percentiles: %s" % (json.dumps(percentiles(pretty_duplicated_ngrams, 15))))
  print("\tNum total distinct ngrams: %d" % (len(common_ngrams)))
  print("\tNum total distinct ngrams (>1 occurance): %d" % (len(sorted_duplicated_common_ngrams)))
  #print("\tSample of substrings: %s" % (json.dumps(prettyhist(common_substrings).items()[:30])))
  print("\tShared substring percentiles: %s" % (json.dumps(percentiles(pretty_common_substrings, 15))))
  print("\tSubstring length percentiles: %s" % (json.dumps(percentiles(substring_lens, 15))))
  print("\tNum total distinct substrings: %d" % (len(substring_lens)))

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
    output_format = 'json'
  elif args.format.lower() == 'json':
    output_format = 'json'
  elif args.format.lower() == 'tsv':
    output_format = 'tsv'
  else:
    print("[-] WARNING: Unknown output format %s, assuming json" % args.format)
    output_format = 'json'
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
