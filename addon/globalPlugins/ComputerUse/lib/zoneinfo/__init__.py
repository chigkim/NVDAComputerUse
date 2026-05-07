"""Compatibility fallback for Python builds without the stdlib ``zoneinfo`` package.

NVDA can run from an embedded Python layout where optional standard-library
packages are not always present. Pydantic imports ``zoneinfo`` during OpenAI
client initialization, so provide the small import surface it requires.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import sysconfig
from datetime import timedelta, tzinfo


def _load_stdlib_zoneinfo():
	stdlib_path = sysconfig.get_path("stdlib")
	if not stdlib_path:
		return None
	init_path = os.path.join(stdlib_path, "zoneinfo", "__init__.py")
	if not os.path.isfile(init_path):
		return None
	if os.path.abspath(init_path) == os.path.abspath(__file__):
		return None

	spec = importlib.util.spec_from_file_location(
		"_computeruse_stdlib_zoneinfo",
		init_path,
		submodule_search_locations=[os.path.dirname(init_path)],
	)
	if spec is None or spec.loader is None:
		return None
	module = importlib.util.module_from_spec(spec)
	sys.modules[spec.name] = module
	spec.loader.exec_module(module)
	return module


try:
	_stdlib_zoneinfo = _load_stdlib_zoneinfo()
except Exception:
	_stdlib_zoneinfo = None

if _stdlib_zoneinfo is not None:
	ZoneInfo = _stdlib_zoneinfo.ZoneInfo
	ZoneInfoNotFoundError = _stdlib_zoneinfo.ZoneInfoNotFoundError
	InvalidTZPathWarning = getattr(_stdlib_zoneinfo, "InvalidTZPathWarning", RuntimeWarning)
	TZPATH = getattr(_stdlib_zoneinfo, "TZPATH", ())
	available_timezones = getattr(_stdlib_zoneinfo, "available_timezones", lambda: set())
	reset_tzpath = getattr(_stdlib_zoneinfo, "reset_tzpath", lambda to=None: None)
else:
	class ZoneInfoNotFoundError(KeyError):
		"""Raised when the requested IANA time zone cannot be loaded."""


	class InvalidTZPathWarning(RuntimeWarning):
		"""Raised for invalid TZPATH values."""


	class ZoneInfo(tzinfo):
		"""Minimal UTC-only ``ZoneInfo`` replacement.

		This is enough for libraries that import or type-check ``ZoneInfo`` during
		startup. Real IANA database lookups still require a full stdlib/tzdata
		installation and will raise ``ZoneInfoNotFoundError`` here.
		"""

		__slots__ = ("_key",)

		def __init__(self, key):
			if key not in ("UTC", "Etc/UTC", "GMT", "Etc/GMT"):
				raise ZoneInfoNotFoundError("No time zone found with key %r" % (key,))
			self._key = key

		@property
		def key(self):
			return self._key

		def utcoffset(self, dt):
			return timedelta(0)

		def dst(self, dt):
			return timedelta(0)

		def tzname(self, dt):
			return self._key

		def fromutc(self, dt):
			return dt.replace(tzinfo=self)

		def __repr__(self):
			return "zoneinfo.ZoneInfo(key=%r)" % self._key

		@classmethod
		def clear_cache(cls, *, only_keys=None):
			return None

		@classmethod
		def no_cache(cls, key):
			return cls(key)

		@classmethod
		def from_file(cls, fobj, /, key=None):
			if key is None:
				key = "UTC"
			return cls(key)


	TZPATH = ()

	def available_timezones():
		return set()

	def reset_tzpath(to=None):
		return None


__all__ = [
	"ZoneInfo",
	"ZoneInfoNotFoundError",
	"available_timezones",
	"reset_tzpath",
	"TZPATH",
	"InvalidTZPathWarning",
]
