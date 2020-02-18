"""passlib.ext.django.utils - helper functions used by this plugin"""
#=============================================================================
# imports
#=============================================================================
# core
from functools import update_wrapper, wraps
import logging; log = logging.getLogger(__name__)
import sys
import weakref
from warnings import warn
# site
try:
    from django import VERSION as DJANGO_VERSION
    log.debug("found django %r installation", DJANGO_VERSION)
except ImportError:
    log.debug("django installation not found")
    DJANGO_VERSION = ()
# pkg
from passlib import exc, registry
from passlib.context import CryptContext
from passlib.exc import PasslibRuntimeWarning
from passlib.utils.compat import get_method_function, iteritems, OrderedDict, unicode
from passlib.utils.decor import memoized_property
# local
__all__ = [
    "DJANGO_VERSION",
    "MIN_DJANGO_VERSION",
    "get_preset_config",
    "get_django_hasher",
]

#: minimum version supported by passlib.ext.django
MIN_DJANGO_VERSION = (1, 8)

#=============================================================================
# default policies
#=============================================================================

# map preset names -> passlib.app attrs
_preset_map = {
    "django-1.0": "django10_context",
    "django-1.4": "django14_context",
    "django-1.6": "django16_context",
    "django-latest": "django_context",
}

def get_preset_config(name):
    """Returns configuration string for one of the preset strings
    supported by the ``PASSLIB_CONFIG`` setting.
    Currently supported presets:

    * ``"passlib-default"`` - default config used by this release of passlib.
    * ``"django-default"`` - config matching currently installed django version.
    * ``"django-latest"`` - config matching newest django version (currently same as ``"django-1.6"``).
    * ``"django-1.0"`` - config used by stock Django 1.0 - 1.3 installs
    * ``"django-1.4"`` - config used by stock Django 1.4 installs
    * ``"django-1.6"`` - config used by stock Django 1.6 installs
    """
    # TODO: add preset which includes HASHERS + PREFERRED_HASHERS,
    #       after having imported any custom hashers. e.g. "django-current"
    if name == "django-default":
        if not DJANGO_VERSION:
            raise ValueError("can't resolve django-default preset, "
                             "django not installed")
        name = "django-1.6"
    if name == "passlib-default":
        return PASSLIB_DEFAULT
    try:
        attr = _preset_map[name]
    except KeyError:
        raise ValueError("unknown preset config name: %r" % name)
    import passlib.apps
    return getattr(passlib.apps, attr).to_string()

# default context used by passlib 1.6
PASSLIB_DEFAULT = """
[passlib]

; list of schemes supported by configuration
; currently all django 1.6, 1.4, and 1.0 hashes,
; and three common modular crypt format hashes.
schemes =
    django_pbkdf2_sha256, django_pbkdf2_sha1, django_bcrypt, django_bcrypt_sha256,
    django_salted_sha1, django_salted_md5, django_des_crypt, hex_md5,
    sha512_crypt, bcrypt, phpass

; default scheme to use for new hashes
default = django_pbkdf2_sha256

; hashes using these schemes will automatically be re-hashed
; when the user logs in (currently all django 1.0 hashes)
deprecated =
    django_pbkdf2_sha1, django_salted_sha1, django_salted_md5,
    django_des_crypt, hex_md5

; sets some common options, including minimum rounds for two primary hashes.
; if a hash has less than this number of rounds, it will be re-hashed.
sha512_crypt__min_rounds = 80000
django_pbkdf2_sha256__min_rounds = 10000

; set somewhat stronger iteration counts for ``User.is_staff``
staff__sha512_crypt__default_rounds = 100000
staff__django_pbkdf2_sha256__default_rounds = 12500

; and even stronger ones for ``User.is_superuser``
superuser__sha512_crypt__default_rounds = 120000
superuser__django_pbkdf2_sha256__default_rounds = 15000
"""

#=============================================================================
# helpers
#=============================================================================

#: prefix used to shoehorn passlib's handler names into django hasher namespace
PASSLIB_WRAPPER_PREFIX = "passlib_"

#: prefix used by all the django-specific hash formats in passlib;
#: all of these hashes should have a ``.django_name`` attribute.
DJANGO_COMPAT_PREFIX = "django_"

#: set of hashes w/o "django_" prefix, but which also expose ``.django_name``.
_other_django_hashes = set(["hex_md5"])

def _wrap_method(method):
    """wrap method object in bare function"""
    @wraps(method)
    def wrapper(*args, **kwds):
        return method(*args, **kwds)
    return wrapper

#=============================================================================
# translator
#=============================================================================
class DjangoTranslator(object):
    """
    Object which helps translate passlib hasher objects / names
    to and from django hasher objects / names.

    These methods are wrapped in a class so that results can be cached,
    but with the ability to have independant caches, since django hasher
    names may / may not correspond to the same instance (or even class).
    """
    #=============================================================================
    # instance attrs
    #=============================================================================

    #: CryptContext instance
    #: (if any -- generally only set by DjangoContextAdapter subclass)
    context = None

    #: internal cache of passlib hasher -> django hasher instance.
    #: key stores weakref to passlib hasher.
    _django_hasher_cache = None

    #: special case -- unsalted_sha1
    _django_unsalted_sha1 = None

    #: internal cache of django name -> passlib hasher
    #: value stores weakrefs to passlib hasher.
    _passlib_hasher_cache = None

    #=============================================================================
    # init
    #=============================================================================

    def __init__(self, context=None, **kwds):
        super(DjangoTranslator, self).__init__(**kwds)
        if context is not None:
            self.context = context

        self._django_hasher_cache = weakref.WeakKeyDictionary()
        self._passlib_hasher_cache = weakref.WeakValueDictionary()

    def reset_hashers(self):
        self._django_hasher_cache.clear()
        self._passlib_hasher_cache.clear()
        self._django_unsalted_sha1 = None

    def _get_passlib_hasher(self, passlib_name):
        """
        resolve passlib hasher by name, using context if available.
        """
        context = self.context
        if context is None:
            return registry.get_crypt_handler(passlib_name)
        else:
            return context.handler(passlib_name)

    #=============================================================================
    # resolve passlib hasher -> django hasher
    #=============================================================================

    def passlib_to_django_name(self, passlib_name):
        """
        Convert passlib hasher / name to Django hasher name.
        """
        return self.passlib_to_django(passlib_name).algorithm

    # XXX: add option (in class, or call signature) to always return a wrapper,
    #      rather than native builtin -- would let HashersTest check that
    #      our own wrapper + implementations are matching up with their tests.
    def passlib_to_django(self, passlib_hasher, cached=True):
        """
        Convert passlib hasher / name to Django hasher.

        :param passlib_hasher:
            passlib hasher / name

        :returns:
            django hasher instance
        """
        # resolve names to hasher
        if not hasattr(passlib_hasher, "name"):
            passlib_hasher = self._get_passlib_hasher(passlib_hasher)

        # check cache
        if cached:
            cache = self._django_hasher_cache
            try:
                return cache[passlib_hasher]
            except KeyError:
                pass
            result = cache[passlib_hasher] = \
                self.passlib_to_django(passlib_hasher, cached=False)
            return result

        # find native equivalent, and return wrapper if there isn't one
        django_name = getattr(passlib_hasher, "django_name", None)
        if django_name:
            return self._create_django_hasher(django_name)
        else:
            return _PasslibHasherWrapper(passlib_hasher)

    _builtin_django_hashers = dict(
        md5="MD5PasswordHasher",
    )

    def _create_django_hasher(self, django_name):
        """
        helper to create new django hasher by name.
        wraps underlying django methods.
        """
        # if we haven't patched django, can use it directly
        module = sys.modules.get("passlib.ext.django.models")
        if module is None or not module.adapter.patched:
            from django.contrib.auth.hashers import get_hasher
            return get_hasher(django_name)

        # We've patched django's get_hashers(), so calling django's get_hasher()
        # or get_hashers_by_algorithm() would only land us back here.
        # As non-ideal workaround, have to use original get_hashers(),
        get_hashers = module.adapter._manager.getorig("django.contrib.auth.hashers:get_hashers").__wrapped__
        for hasher in get_hashers():
            if hasher.algorithm == django_name:
                return hasher

        # hardcode a few for cases where get_hashers() look won't work.
        path = self._builtin_django_hashers.get(django_name)
        if path:
            if "." not in path:
                path = "django.contrib.auth.hashers." + path
            from django.utils.module_loading import import_string
            return import_string(path)()

        raise ValueError("unknown hasher: %r" % django_name)

    #=============================================================================
    # reverse django -> passlib
    #=============================================================================

    def django_to_passlib_name(self, django_name):
        """
        Convert Django hasher / name to Passlib hasher name.
        """
        return self.django_to_passlib(django_name).name

    def django_to_passlib(self, django_name, cached=True):
        """
        Convert Django hasher / name to Passlib hasher / name.
        If present, CryptContext will be checked instead of main registry.

        :param django_name:
            Django hasher class or algorithm name.
            "default" allowed if context provided.

        :raises ValueError:
            if can't resolve hasher.

        :returns:
            passlib hasher or name
        """
        # check for django hasher
        if hasattr(django_name, "algorithm"):

            # check for passlib adapter
            if isinstance(django_name, _PasslibHasherWrapper):
                return django_name.passlib_handler

            # resolve django hasher -> name
            django_name = django_name.algorithm

        # check cache
        if cached:
            cache = self._passlib_hasher_cache
            try:
                return cache[django_name]
            except KeyError:
                pass
            result = cache[django_name] = \
                self.django_to_passlib(django_name, cached=False)
            return result

        # check if it's an obviously-wrapped name
        if django_name.startswith(PASSLIB_WRAPPER_PREFIX):
            passlib_name = django_name[len(PASSLIB_WRAPPER_PREFIX):]
            return self._get_passlib_hasher(passlib_name)

        # resolve default
        if django_name == "default":
            context = self.context
            if context is None:
                raise TypeError("can't determine default scheme w/ context")
            return context.handler()

        # special case: Django uses a separate hasher for "sha1$$digest"
        # hashes (unsalted_sha1) and "sha1$salt$digest" (sha1);
        # but passlib uses "django_salted_sha1" for both of these.
        if django_name == "unsalted_sha1":
            django_name = "sha1"

        # resolve name
        # XXX: bother caching these lists / mapping?
        #      not needed in long-term due to cache above.
        context = self.context
        if context is None:
            # check registry
            # TODO: should make iteration via registry easier
            candidates = (
                registry.get_crypt_handler(passlib_name)
                for passlib_name in registry.list_crypt_handlers()
                if passlib_name.startswith(DJANGO_COMPAT_PREFIX) or
                   passlib_name in _other_django_hashes
            )
        else:
            # check context
            candidates = context.schemes(resolve=True)
        for handler in candidates:
            if getattr(handler, "django_name", None) == django_name:
                return handler

        # give up
        # NOTE: this should only happen for custom django hashers that we don't
        #       know the equivalents for. _HasherHandler (below) is work in
        #       progress that would allow us to at least return a wrapper.
        raise ValueError("can't translate django name to passlib name: %r" %
                         (django_name,))

    #=============================================================================
    # django hasher lookup
    #=============================================================================

    def resolve_django_hasher(self, django_name, cached=True):
        """
        Take in a django algorithm name, return django hasher.
        """
        # check for django hasher
        if hasattr(django_name, "algorithm"):
            return django_name

        # resolve to passlib hasher
        passlib_hasher = self.django_to_passlib(django_name, cached=cached)

        # special case: Django uses a separate hasher for "sha1$$digest"
        # hashes (unsalted_sha1) and "sha1$salt$digest" (sha1);
        # but passlib uses "django_salted_sha1" for both of these.
        # XXX: this isn't ideal way to handle this.  would like to do something
        #      like pass "django_variant=django_name" into passlib_to_django(),
        #      and have it cache separate hasher there.
        #      but that creates a LOT of complication in it's cache structure,
        #      for what is just one special case.
        if django_name == "unsalted_sha1" and passlib_hasher.name == "django_salted_sha1":
            if not cached:
                return self._create_django_hasher(django_name)
            result = self._django_unsalted_sha1
            if result is None:
                result = self._django_unsalted_sha1 = self._create_django_hasher(django_name)
            return result

        # lookup corresponding django hasher
        return self.passlib_to_django(passlib_hasher, cached=cached)

    #=============================================================================
    # eoc
    #=============================================================================

#=============================================================================
# adapter
#=============================================================================
class DjangoContextAdapter(DjangoTranslator):
    """
    Object which tries to adapt a Passlib CryptContext object,
    using a Django-hasher compatible API.

    When installed in django, :mod:`!passlib.ext.django` will create
    an instance of this class, and then monkeypatch the appropriate
    methods into :mod:`!django.contrib.auth` and other appropriate places.
    """
    #=============================================================================
    # instance attrs
    #=============================================================================

    #: CryptContext instance we're wrapping
    context = None

    #: ref to original make_password(),
    #: needed to generate usuable passwords that match django
    _orig_make_password = None

    #: ref to django helper of this name -- not monkeypatched
    is_password_usable = None

    #: PatchManager instance used to track installation
    _manager = None

    #: whether config=disabled flag was set
    enabled = True

    #: patch status
    patched = False

    #=============================================================================
    # init
    #=============================================================================
    def __init__(self, context=None, get_user_category=None, **kwds):

        # init log
        self.log = logging.getLogger(__name__ + ".DjangoContextAdapter")

        # init parent, filling in default context object
        if context is None:
            context = CryptContext()
        super(DjangoContextAdapter, self).__init__(context=context, **kwds)

        # setup user category
        if get_user_category:
            assert callable(get_user_category)
            self.get_user_category = get_user_category

        # install lru cache wrappers
        from functools import lru_cache
        self.get_hashers = lru_cache()(self.get_hashers)

        # get copy of original make_password
        from django.contrib.auth.hashers import make_password
        if make_password.__module__.startswith("passlib."):
            make_password = _PatchManager.peek_unpatched_func(make_password)
        self._orig_make_password = make_password

        # get other django helpers
        from django.contrib.auth.hashers import is_password_usable
        self.is_password_usable = is_password_usable

        # init manager
        mlog = logging.getLogger(__name__ + ".DjangoContextAdapter._manager")
        self._manager = _PatchManager(log=mlog)

    def reset_hashers(self):
        """
        Wrapper to manually reset django's hasher lookup cache
        """
        # resets cache for .get_hashers() & .get_hashers_by_algorithm()
        from django.contrib.auth.hashers import reset_hashers
        reset_hashers(setting="PASSWORD_HASHERS")

        # reset internal caches
        super(DjangoContextAdapter, self).reset_hashers()

    #=============================================================================
    # django hashers helpers -- hasher lookup
    #=============================================================================

    # lru_cache()'ed by init
    def get_hashers(self):
        """
        Passlib replacement for get_hashers() --
        Return list of available django hasher classes
        """
        passlib_to_django = self.passlib_to_django
        return [passlib_to_django(hasher)
                for hasher in self.context.schemes(resolve=True)]

    def get_hasher(self, algorithm="default"):
        """
        Passlib replacement for get_hasher() --
        Return django hasher by name
        """
        return self.resolve_django_hasher(algorithm)

    def identify_hasher(self, encoded):
        """
        Passlib replacement for identify_hasher() --
        Identify django hasher based on hash.
        """
        handler = self.context.identify(encoded, resolve=True, required=True)
        if handler.name == "django_salted_sha1" and encoded.startswith("sha1$$"):
            # Django uses a separate hasher for "sha1$$digest" hashes, but
            # passlib identifies it as belonging to "sha1$salt$digest" handler.
            # We want to resolve to correct django hasher.
            return self.get_hasher("unsalted_sha1")
        return self.passlib_to_django(handler)

    #=============================================================================
    # django.contrib.auth.hashers helpers -- password helpers
    #=============================================================================

    def make_password(self, password, salt=None, hasher="default"):
        """
        Passlib replacement for make_password()
        """
        if password is None:
            return self._orig_make_password(None)
        # NOTE: relying on hasher coming from context, and thus having
        #       context-specific config baked into it.
        passlib_hasher = self.django_to_passlib(hasher)
        if "salt" not in passlib_hasher.setting_kwds:
            # ignore salt param even if preset
            pass
        elif hasher.startswith("unsalted_"):
            # Django uses a separate 'unsalted_sha1' hasher for "sha1$$digest",
            # but passlib just reuses it's "sha1" handler ("sha1$salt$digest"). To make
            # this work, have to explicitly tell the sha1 handler to use an empty salt.
            passlib_hasher = passlib_hasher.using(salt="")
        elif salt:
            # Django make_password() autogenerates a salt if salt is bool False (None / ''),
            # so we only pass the keyword on if there's actually a fixed salt.
            passlib_hasher = passlib_hasher.using(salt=salt)
        return passlib_hasher.hash(password)

    def check_password(self, password, encoded, setter=None, preferred="default"):
        """
        Passlib replacement for check_password()
        """
        # XXX: this currently ignores "preferred" keyword, since its purpose
        #      was for hash migration, and that's handled by the context.
        if password is None or not self.is_password_usable(encoded):
            return False

        # verify password
        context = self.context
        correct = context.verify(password, encoded)
        if not (correct and setter):
            return correct

        # check if we need to rehash
        if preferred == "default":
            if not context.needs_update(encoded, secret=password):
                return correct
        else:
            # Django's check_password() won't call setter() on a
            # 'preferred' alg, even if it's otherwise deprecated. To try and
            # replicate this behavior if preferred is set, we look up the
            # passlib hasher, and call it's original needs_update() method.
            # TODO: Solve redundancy that verify() call
            #       above is already identifying hash.
            hasher = self.django_to_passlib(preferred)
            if (hasher.identify(encoded) and
                    not hasher.needs_update(encoded, secret=password)):
                # alg is 'preferred' and hash itself doesn't need updating,
                # so nothing to do.
                return correct
            # else: either hash isn't preferred, or it needs updating.

        # call setter to rehash
        setter(password)
        return correct

    #=============================================================================
    # django users helpers
    #=============================================================================

    def user_check_password(self, user, password):
        """
        Passlib replacement for User.check_password()
        """
        if password is None:
            return False
        hash = user.password
        if not self.is_password_usable(hash):
            return False
        cat = self.get_user_category(user)
        ok, new_hash = self.context.verify_and_update(password, hash,
                                                      category=cat)
        if ok and new_hash is not None:
            # migrate to new hash if needed.
            user.password = new_hash
            user.save()
        return ok

    def user_set_password(self, user, password):
        """
        Passlib replacement for User.set_password()
        """
        if password is None:
            user.set_unusable_password()
        else:
            cat = self.get_user_category(user)
            user.password = self.context.hash(password, category=cat)

    def get_user_category(self, user):
        """
        Helper for hashing passwords per-user --
        figure out the CryptContext category for specified Django user object.
        .. note::
            This may be overridden via PASSLIB_GET_CATEGORY django setting
        """
        if user.is_superuser:
            return "superuser"
        elif user.is_staff:
            return "staff"
        else:
            return None

    #=============================================================================
    # patch control
    #=============================================================================

    HASHERS_PATH = "django.contrib.auth.hashers"
    MODELS_PATH = "django.contrib.auth.models"
    USER_CLASS_PATH = MODELS_PATH + ":User"
    FORMS_PATH = "django.contrib.auth.forms"

    #: list of locations to patch
    patch_locations = [
        #
        # User object
        # NOTE: could leave defaults alone, but want to have user available
        #       so that we can support get_user_category()
        #
        (USER_CLASS_PATH + ".check_password", "user_check_password", dict(method=True)),
        (USER_CLASS_PATH + ".set_password", "user_set_password", dict(method=True)),

        #
        # Hashers module
        #
        (HASHERS_PATH + ":", "check_password"),
        (HASHERS_PATH + ":", "make_password"),
        (HASHERS_PATH + ":", "get_hashers"),
        (HASHERS_PATH + ":", "get_hasher"),
        (HASHERS_PATH + ":", "identify_hasher"),

        #
        # Patch known imports from hashers module
        #
        (MODELS_PATH + ":", "check_password"),
        (MODELS_PATH + ":", "make_password"),
        (FORMS_PATH + ":", "get_hasher"),
        (FORMS_PATH + ":", "identify_hasher"),

    ]

    def install_patch(self):
        """
        Install monkeypatch to replace django hasher framework.
        """
        # don't reapply
        log = self.log
        if self.patched:
            log.warning("monkeypatching already applied, refusing to reapply")
            return False

        # version check
        if DJANGO_VERSION < MIN_DJANGO_VERSION:
            raise RuntimeError("passlib.ext.django requires django >= %s" %
                               (MIN_DJANGO_VERSION,))

        # log start
        log.debug("preparing to monkeypatch django ...")

        # run through patch locations
        manager = self._manager
        for record in self.patch_locations:
            if len(record) == 2:
                record += ({},)
            target, source, opts = record
            if target.endswith((":", ",")):
                target += source
            value = getattr(self, source)
            if opts.get("method"):
                # have to wrap our method in a function,
                # since we're installing it in a class *as* a method
                # XXX: make this a flag for .patch()?
                value = _wrap_method(value)
            manager.patch(target, value)

        # reset django's caches (e.g. get_hash_by_algorithm)
        self.reset_hashers()

        # done!
        self.patched = True
        log.debug("... finished monkeypatching django")
        return True

    def remove_patch(self):
        """
        Remove monkeypatch from django hasher framework.
        As precaution in case there are lingering refs to context,
        context object will be wiped.

        .. warning::
            This may cause problems if any other Django modules have imported
            their own copies of the patched functions, though the patched
            code has been designed to throw an error as soon as possible in
            this case.
        """
        log = self.log
        manager = self._manager

        if self.patched:
            log.debug("removing django monkeypatching...")
            manager.unpatch_all(unpatch_conflicts=True)
            self.context.load({})
            self.patched = False
            self.reset_hashers()
            log.debug("...finished removing django monkeypatching")
            return True

        if manager.isactive():  # pragma: no cover -- sanity check
            log.warning("reverting partial monkeypatching of django...")
            manager.unpatch_all()
            self.context.load({})
            self.reset_hashers()
            log.debug("...finished removing django monkeypatching")
            return True

        log.debug("django not monkeypatched")
        return False

    #=============================================================================
    # loading config
    #=============================================================================

    def load_model(self):
        """
        Load configuration from django, and install patch.
        """
        self._load_settings()
        if self.enabled:
            try:
                self.install_patch()
            except:
                # try to undo what we can
                self.remove_patch()
                raise
        else:
            if self.patched:  # pragma: no cover -- sanity check
                log.error("didn't expect monkeypatching would be applied!")
            self.remove_patch()
        log.debug("passlib.ext.django loaded")

    def _load_settings(self):
        """
        Update settings from django
        """
        from django.conf import settings

        # TODO: would like to add support for inheriting config from a preset
        #       (or from existing hasher state) and letting PASSLIB_CONFIG
        #       be an update, not a replacement.

        # TODO: wrap and import any custom hashers as passlib handlers,
        #       so they could be used in the passlib config.

        # load config from settings
        _UNSET = object()
        config = getattr(settings, "PASSLIB_CONFIG", _UNSET)
        if config is _UNSET:
            # XXX: should probably deprecate this alias
            config = getattr(settings, "PASSLIB_CONTEXT", _UNSET)
        if config is _UNSET:
            config = "passlib-default"
        if not isinstance(config, (unicode, bytes, dict)):
            raise exc.ExpectedTypeError(config, "str or dict", "PASSLIB_CONFIG")

        # load custom category func (if any)
        get_category = getattr(settings, "PASSLIB_GET_CATEGORY", None)
        if get_category and not callable(get_category):
            raise exc.ExpectedTypeError(get_category, "callable", "PASSLIB_GET_CATEGORY")

        # check if we've been disabled
        if config == "disabled":
            self.enabled = False
            return
        else:
            self.__dict__.pop("enabled", None)

        # resolve any preset aliases
        if isinstance(config, str) and '\n' not in config:
            config = get_preset_config(config)

        # setup category func
        if get_category:
            self.get_user_category = get_category
        else:
            self.__dict__.pop("get_category", None)

        # setup context
        self.context.load(config)
        self.reset_hashers()

    #=============================================================================
    # eof
    #=============================================================================

#=============================================================================
# wrapping passlib handlers as django hashers
#=============================================================================
_GEN_SALT_SIGNAL = "--!!!generate-new-salt!!!--"

class ProxyProperty(object):
    """helper that proxies another attribute"""

    def __init__(self, attr):
        self.attr = attr

    def __get__(self, obj, cls):
        if obj is None:
            cls = obj
        return getattr(obj, self.attr)

    def __set__(self, obj, value):
        setattr(obj, self.attr, value)

    def __delete__(self, obj):
        delattr(obj, self.attr)


class _PasslibHasherWrapper(object):
    """
    adapter which which wraps a :cls:`passlib.ifc.PasswordHash` class,
    and provides an interface compatible with the Django hasher API.

    :param passlib_handler:
        passlib hash handler (e.g. :cls:`passlib.hash.sha256_crypt`.
    """
    #=====================================================================
    # instance attrs
    #=====================================================================

    #: passlib handler that we're adapting.
    passlib_handler = None

    # NOTE: 'rounds' attr will store variable rounds, IF handler supports it.
    #       'iterations' will act as proxy, for compatibility with django pbkdf2 hashers.
    # rounds = None
    # iterations = None

    #=====================================================================
    # init
    #=====================================================================
    def __init__(self, passlib_handler):
        # init handler
        if getattr(passlib_handler, "django_name", None):
            raise ValueError("handlers that reflect an official django "
                             "hasher shouldn't be wrapped: %r" %
                             (passlib_handler.name,))
        if passlib_handler.is_disabled:
            # XXX: could this be implemented?
            raise ValueError("can't wrap disabled-hash handlers: %r" %
                             (passlib_handler.name))
        self.passlib_handler = passlib_handler

        # init rounds support
        if self._has_rounds:
            self.rounds = passlib_handler.default_rounds
            self.iterations = ProxyProperty("rounds")

    #=====================================================================
    # internal methods
    #=====================================================================
    def __repr__(self):
        return "<PasslibHasherWrapper handler=%r>" % self.passlib_handler

    #=====================================================================
    # internal properties
    #=====================================================================

    @memoized_property
    def __name__(self):
        return "Passlib_%s_PasswordHasher" % self.passlib_handler.name.title()

    @memoized_property
    def _has_rounds(self):
        return "rounds" in self.passlib_handler.setting_kwds

    @memoized_property
    def _translate_kwds(self):
        """
        internal helper for safe_summary() --
        used to translate passlib hash options -> django keywords
        """
        out = dict(checksum="hash")
        if self._has_rounds and "pbkdf2" in self.passlib_handler.name:
            out['rounds'] = 'iterations'
        return out

    #=====================================================================
    # hasher properties
    #=====================================================================

    @memoized_property
    def algorithm(self):
        return PASSLIB_WRAPPER_PREFIX + self.passlib_handler.name

    #=====================================================================
    # hasher api
    #=====================================================================
    def salt(self):
        # NOTE: passlib's handler.hash() should generate new salt each time,
        #       so this just returns a special constant which tells
        #       encode() (below) not to pass a salt keyword along.
        return _GEN_SALT_SIGNAL

    def verify(self, password, encoded):
        return self.passlib_handler.verify(password, encoded)

    def encode(self, password, salt=None, rounds=None, iterations=None):
        kwds = {}
        if salt is not None and salt != _GEN_SALT_SIGNAL:
            kwds['salt'] = salt
        if self._has_rounds:
            if rounds is not None:
                kwds['rounds'] = rounds
            elif iterations is not None:
                kwds['rounds'] = iterations
            else:
                kwds['rounds'] = self.rounds
        elif rounds is not None or iterations is not None:
            warn("%s.hash(): 'rounds' and 'iterations' are ignored" % self.__name__)
        handler = self.passlib_handler
        if kwds:
            handler = handler.using(**kwds)
        return handler.hash(password)

    def safe_summary(self, encoded):
        from django.contrib.auth.hashers import mask_hash
        from django.utils.translation import ugettext_noop as _
        handler = self.passlib_handler
        items = [
            # since this is user-facing, we're reporting passlib's name,
            # without the distracting PASSLIB_HASHER_PREFIX prepended.
            (_('algorithm'), handler.name),
        ]
        if hasattr(handler, "parsehash"):
            kwds = handler.parsehash(encoded, sanitize=mask_hash)
            for key, value in iteritems(kwds):
                key = self._translate_kwds.get(key, key)
                items.append((_(key), value))
        return OrderedDict(items)

    def must_update(self, encoded):
        # TODO: would like access CryptContext, would need caller to pass it to get_passlib_hasher().
        #       for now (as of passlib 1.6.6), replicating django policy that this returns True
        #       if 'encoded' hash has different rounds value from self.rounds
        if self._has_rounds:
            # XXX: could cache this subclass somehow (would have to intercept writes to self.rounds)
            # TODO: always call subcls/handler.needs_update() in case there's other things to check
            subcls = self.passlib_handler.using(min_rounds=self.rounds, max_rounds=self.rounds)
            if subcls.needs_update(encoded):
                return True
        return False

    #=====================================================================
    # eoc
    #=====================================================================

#=============================================================================
# adapting django hashers -> passlib handlers
#=============================================================================
# TODO: this code probably halfway works, mainly just needs
#       a routine to read HASHERS and PREFERRED_HASHER.

##from passlib.registry import register_crypt_handler
##from passlib.utils import classproperty, to_native_str, to_unicode
##from passlib.utils.compat import unicode
##
##
##class _HasherHandler(object):
##    "helper for wrapping Hasher instances as passlib handlers"
##    # FIXME: this generic wrapper doesn't handle custom settings
##    # FIXME: genconfig / genhash not supported.
##
##    def __init__(self, hasher):
##        self.django_hasher = hasher
##        if hasattr(hasher, "iterations"):
##            # assume encode() accepts an "iterations" parameter.
##            # fake min/max rounds
##            self.min_rounds = 1
##            self.max_rounds = 0xFFFFffff
##            self.default_rounds = self.django_hasher.iterations
##            self.setting_kwds += ("rounds",)
##
##    # hasher instance - filled in by constructor
##    django_hasher = None
##
##    setting_kwds = ("salt",)
##    context_kwds = ()
##
##    @property
##    def name(self):
##        # XXX: need to make sure this wont' collide w/ builtin django hashes.
##        #      maybe by renaming this to django compatible aliases?
##        return DJANGO_PASSLIB_PREFIX + self.django_name
##
##    @property
##    def django_name(self):
##        # expose this so hasher_to_passlib_name() extracts original name
##        return self.django_hasher.algorithm
##
##    @property
##    def ident(self):
##        # this should always be correct, as django relies on ident prefix.
##        return unicode(self.django_name + "$")
##
##    @property
##    def identify(self, hash):
##        # this should always work, as django relies on ident prefix.
##        return to_unicode(hash, "latin-1", "hash").startswith(self.ident)
##
##    @property
##    def hash(self, secret, salt=None, **kwds):
##        # NOTE: from how make_password() is coded, all hashers
##        #       should have salt param. but only some will have
##        #       'iterations' parameter.
##        opts = {}
##        if 'rounds' in self.setting_kwds and 'rounds' in kwds:
##            opts['iterations'] = kwds.pop("rounds")
##        if kwds:
##            raise TypeError("unexpected keyword arguments: %r" % list(kwds))
##        if isinstance(secret, unicode):
##            secret = secret.encode("utf-8")
##        if salt is None:
##            salt = self.django_hasher.salt()
##        return to_native_str(self.django_hasher(secret, salt, **opts))
##
##    @property
##    def verify(self, secret, hash):
##        hash = to_native_str(hash, "utf-8", "hash")
##        if isinstance(secret, unicode):
##            secret = secret.encode("utf-8")
##        return self.django_hasher.verify(secret, hash)
##
##def register_hasher(hasher):
##    handler = _HasherHandler(hasher)
##    register_crypt_handler(handler)
##    return handler

#=============================================================================
# monkeypatch helpers
#=============================================================================
# private singleton indicating lack-of-value
_UNSET = object()

class _PatchManager(object):
    """helper to manage monkeypatches and run sanity checks"""

    # NOTE: this could easily use a dict interface,
    #       but keeping it distinct to make clear that it's not a dict,
    #       since it has important side-effects.

    #===================================================================
    # init and support
    #===================================================================
    def __init__(self, log=None):
        # map of key -> (original value, patched value)
        # original value may be _UNSET
        self.log = log or logging.getLogger(__name__ + "._PatchManager")
        self._state = {}

    def isactive(self):
        return bool(self._state)

    # bool value tests if any patches are currently applied.
    # NOTE: this behavior is deprecated in favor of .isactive
    __bool__ = __nonzero__ = isactive

    def _import_path(self, path):
        """retrieve obj and final attribute name from resource path"""
        name, attr = path.split(":")
        obj = __import__(name, fromlist=[attr], level=0)
        while '.' in attr:
           head, attr = attr.split(".", 1)
           obj = getattr(obj, head)
        return obj, attr

    @staticmethod
    def _is_same_value(left, right):
        """check if two values are the same (stripping method wrappers, etc)"""
        return get_method_function(left) == get_method_function(right)

    #===================================================================
    # reading
    #===================================================================
    def _get_path(self, key, default=_UNSET):
        obj, attr = self._import_path(key)
        return getattr(obj, attr, default)

    def get(self, path, default=None):
        """return current value for path"""
        return self._get_path(path, default)

    def getorig(self, path, default=None):
        """return original (unpatched) value for path"""
        try:
            value, _= self._state[path]
        except KeyError:
            value = self._get_path(path)
        return default if value is _UNSET else value

    def check_all(self, strict=False):
        """run sanity check on all keys, issue warning if out of sync"""
        same = self._is_same_value
        for path, (orig, expected) in iteritems(self._state):
            if same(self._get_path(path), expected):
                continue
            msg = "another library has patched resource: %r" % path
            if strict:
                raise RuntimeError(msg)
            else:
                warn(msg, PasslibRuntimeWarning)

    #===================================================================
    # patching
    #===================================================================
    def _set_path(self, path, value):
        obj, attr = self._import_path(path)
        if value is _UNSET:
            if hasattr(obj, attr):
                delattr(obj, attr)
        else:
            setattr(obj, attr, value)

    def patch(self, path, value, wrap=False):
        """monkeypatch object+attr at <path> to have <value>, stores original"""
        assert value != _UNSET
        current = self._get_path(path)
        try:
            orig, expected = self._state[path]
        except KeyError:
            self.log.debug("patching resource: %r", path)
            orig = current
        else:
            self.log.debug("modifying resource: %r", path)
            if not self._is_same_value(current, expected):
                warn("overridding resource another library has patched: %r"
                     % path, PasslibRuntimeWarning)
        if wrap:
            assert callable(value)
            wrapped = orig
            wrapped_by = value
            def wrapper(*args, **kwds):
                return wrapped_by(wrapped, *args, **kwds)
            update_wrapper(wrapper, value)
            value = wrapper
        if callable(value):
            # needed by DjangoContextAdapter init
            get_method_function(value)._patched_original_value = orig
        self._set_path(path, value)
        self._state[path] = (orig, value)

    @classmethod
    def peek_unpatched_func(cls, value):
        return value._patched_original_value

    ##def patch_many(self, **kwds):
    ##    "override specified resources with new values"
    ##    for path, value in iteritems(kwds):
    ##        self.patch(path, value)

    def monkeypatch(self, parent, name=None, enable=True, wrap=False):
        """function decorator which patches function of same name in <parent>"""
        def builder(func):
            if enable:
                sep = "." if ":" in parent else ":"
                path = parent + sep + (name or func.__name__)
                self.patch(path, func, wrap=wrap)
            return func
        if callable(name):
            # called in non-decorator mode
            func = name
            name = None
            builder(func)
            return None
        return builder

    #===================================================================
    # unpatching
    #===================================================================
    def unpatch(self, path, unpatch_conflicts=True):
        try:
            orig, expected = self._state[path]
        except KeyError:
            return
        current = self._get_path(path)
        self.log.debug("unpatching resource: %r", path)
        if not self._is_same_value(current, expected):
            if unpatch_conflicts:
                warn("reverting resource another library has patched: %r"
                     % path, PasslibRuntimeWarning)
            else:
                warn("not reverting resource another library has patched: %r"
                     % path, PasslibRuntimeWarning)
                del self._state[path]
                return
        self._set_path(path, orig)
        del self._state[path]

    def unpatch_all(self, **kwds):
        for key in list(self._state):
            self.unpatch(key, **kwds)

    #===================================================================
    # eoc
    #===================================================================

#=============================================================================
# eof
#=============================================================================
