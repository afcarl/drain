import sys
import dateutil
import logging

from drain import util

aggregator_name = sys.argv[1]
date = dateutil.parser.parse(sys.argv[2]).date()
basedir = sys.argv[3]

logging.info('Initializing %s' % aggregator_name)
aggregator = util.get_attr(aggregator_name)(basedir)
aggregator.write_date(date)
