import os
import logging

from configobj import ConfigObj, ConfigObjError, flatten_errors
from configobj.validate import Validator
import globalVars

from .configspec import configspec


log = logging.getLogger(__name__)
config = None


def load_config():
	global config
	path = os.path.abspath(os.path.join(globalVars.appArgs.configPath, "ComputerUse.conf"))
	configspec.seek(0)
	try:
		config = ConfigObj(
			infile=path,
			configspec=configspec,
			default_encoding="UTF8",
			create_empty=True,
		)
	except ConfigObjError:
		log.exception("Unable to load Computer Use configuration")
		return
	validator = Validator()
	result = config.validate(validator, copy=True)
	if result is not True:
		log.error("Computer Use configuration validation failed:\n%s", "\n".join(_validation_errors(config, result)))


def _validation_errors(conf, validation_result):
	errors = []
	for section_list, key, _ in flatten_errors(conf, validation_result):
		if key:
			errors.append('"%s" in section "%s" failed validation' % (key, ", ".join(section_list)))
		else:
			errors.append('missing section "%s"' % ", ".join(section_list))
	return errors
