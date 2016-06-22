"""passlib.tests.test_handlers_argon2 - tests for passlib hash algorithms"""
#=============================================================================
# imports
#=============================================================================
# core
import logging
log = logging.getLogger(__name__)
# site
# pkg
from passlib import hash
from passlib.tests.utils import HandlerCase, TEST_MODE, randintgauss
from passlib.tests.test_handlers import UPASS_TABLE, PASS_TABLE_UTF8
# module

#=============================================================================
# a bunch of tests lifted nearlky verbatim from official argon2 UTs...
# https://github.com/P-H-C/phc-winner-argon2/blob/master/src/test.c
#=============================================================================
def hashtest(version, t, logM, p, secret, salt, hex_digest, hash):
    return dict(version=version, rounds=t, logM=logM, memory_cost=1<<logM, parallelism=p,
                secret=secret, salt=salt, hex_digest=hex_digest, hash=hash)

version = 0x10
reference_data = [
    hashtest(version, 2, 16, 1, "password", "somesalt",
             "f6c4db4a54e2a370627aff3db6176b94a2a209a62c8e36152711802f7b30c694",
             "$argon2i$m=65536,t=2,p=1$c29tZXNhbHQ"
             "$9sTbSlTio3Biev89thdrlKKiCaYsjjYVJxGAL3swxpQ"),
    hashtest(version, 2, 20, 1, "password", "somesalt",
             "9690ec55d28d3ed32562f2e73ea62b02b018757643a2ae6e79528459de8106e9",
             "$argon2i$m=1048576,t=2,p=1$c29tZXNhbHQ"
             "$lpDsVdKNPtMlYvLnPqYrArAYdXZDoq5ueVKEWd6BBuk"),
    hashtest(version, 2, 18, 1, "password", "somesalt",
             "3e689aaa3d28a77cf2bc72a51ac53166761751182f1ee292e3f677a7da4c2467",
             "$argon2i$m=262144,t=2,p=1$c29tZXNhbHQ"
             "$Pmiaqj0op3zyvHKlGsUxZnYXURgvHuKS4/Z3p9pMJGc"),
    hashtest(version, 2, 8, 1, "password", "somesalt",
             "fd4dd83d762c49bdeaf57c47bdcd0c2f1babf863fdeb490df63ede9975fccf06",
             "$argon2i$m=256,t=2,p=1$c29tZXNhbHQ"
             "$/U3YPXYsSb3q9XxHvc0MLxur+GP960kN9j7emXX8zwY"),
    hashtest(version, 2, 8, 2, "password", "somesalt",
             "b6c11560a6a9d61eac706b79a2f97d68b4463aa3ad87e00c07e2b01e90c564fb",
             "$argon2i$m=256,t=2,p=2$c29tZXNhbHQ"
             "$tsEVYKap1h6scGt5ovl9aLRGOqOth+AMB+KwHpDFZPs"),
    hashtest(version, 1, 16, 1, "password", "somesalt",
             "81630552b8f3b1f48cdb1992c4c678643d490b2b5eb4ff6c4b3438b5621724b2",
             "$argon2i$m=65536,t=1,p=1$c29tZXNhbHQ"
             "$gWMFUrjzsfSM2xmSxMZ4ZD1JCytetP9sSzQ4tWIXJLI"),
    hashtest(version, 4, 16, 1, "password", "somesalt",
             "f212f01615e6eb5d74734dc3ef40ade2d51d052468d8c69440a3a1f2c1c2847b",
             "$argon2i$m=65536,t=4,p=1$c29tZXNhbHQ"
             "$8hLwFhXm6110c03D70Ct4tUdBSRo2MaUQKOh8sHChHs"),
    hashtest(version, 2, 16, 1, "differentpassword", "somesalt",
             "e9c902074b6754531a3a0be519e5baf404b30ce69b3f01ac3bf21229960109a3",
             "$argon2i$m=65536,t=2,p=1$c29tZXNhbHQ"
             "$6ckCB0tnVFMaOgvlGeW69ASzDOabPwGsO/ISKZYBCaM"),
    hashtest(version, 2, 16, 1, "password", "diffsalt",
             "79a103b90fe8aef8570cb31fc8b22259778916f8336b7bdac3892569d4f1c497",
             "$argon2i$m=65536,t=2,p=1$ZGlmZnNhbHQ"
             "$eaEDuQ/orvhXDLMfyLIiWXeJFvgza3vaw4kladTxxJc"),
]

version = 0x13
reference_data.extend([
    hashtest(version, 2, 16, 1, "password", "somesalt",
             "c1628832147d9720c5bd1cfd61367078729f6dfb6f8fea9ff98158e0d7816ed0",
             "$argon2i$v=19$m=65536,t=2,p=1$c29tZXNhbHQ"
             "$wWKIMhR9lyDFvRz9YTZweHKfbftvj+qf+YFY4NeBbtA"),
    hashtest(version, 2, 20, 1, "password", "somesalt",
             "d1587aca0922c3b5d6a83edab31bee3c4ebaef342ed6127a55d19b2351ad1f41",
             "$argon2i$v=19$m=1048576,t=2,p=1$c29tZXNhbHQ"
             "$0Vh6ygkiw7XWqD7asxvuPE667zQu1hJ6VdGbI1GtH0E"),
    hashtest(version, 2, 18, 1, "password", "somesalt",
             "296dbae80b807cdceaad44ae741b506f14db0959267b183b118f9b24229bc7cb",
             "$argon2i$v=19$m=262144,t=2,p=1$c29tZXNhbHQ"
             "$KW266AuAfNzqrUSudBtQbxTbCVkmexg7EY+bJCKbx8s"),
    hashtest(version, 2, 8, 1, "password", "somesalt",
             "89e9029f4637b295beb027056a7336c414fadd43f6b208645281cb214a56452f",
             "$argon2i$v=19$m=256,t=2,p=1$c29tZXNhbHQ"
             "$iekCn0Y3spW+sCcFanM2xBT63UP2sghkUoHLIUpWRS8"),
    hashtest(version, 2, 8, 2, "password", "somesalt",
             "4ff5ce2769a1d7f4c8a491df09d41a9fbe90e5eb02155a13e4c01e20cd4eab61",
             "$argon2i$v=19$m=256,t=2,p=2$c29tZXNhbHQ"
             "$T/XOJ2mh1/TIpJHfCdQan76Q5esCFVoT5MAeIM1Oq2E"),
    hashtest(version, 1, 16, 1, "password", "somesalt",
             "d168075c4d985e13ebeae560cf8b94c3b5d8a16c51916b6f4ac2da3ac11bbecf",
             "$argon2i$v=19$m=65536,t=1,p=1$c29tZXNhbHQ"
             "$0WgHXE2YXhPr6uVgz4uUw7XYoWxRkWtvSsLaOsEbvs8"),
    hashtest(version, 4, 16, 1, "password", "somesalt",
             "aaa953d58af3706ce3df1aefd4a64a84e31d7f54175231f1285259f88174ce5b",
             "$argon2i$v=19$m=65536,t=4,p=1$c29tZXNhbHQ"
             "$qqlT1YrzcGzj3xrv1KZKhOMdf1QXUjHxKFJZ+IF0zls"),
    hashtest(version, 2, 16, 1, "differentpassword", "somesalt",
             "14ae8da01afea8700c2358dcef7c5358d9021282bd88663a4562f59fb74d22ee",
             "$argon2i$v=19$m=65536,t=2,p=1$c29tZXNhbHQ"
             "$FK6NoBr+qHAMI1jc73xTWNkCEoK9iGY6RWL1n7dNIu4"),
    hashtest(version, 2, 16, 1, "password", "diffsalt",
             "b0357cccfbef91f3860b0dba447b2348cbefecadaf990abfe9cc40726c521271",
             "$argon2i$v=19$m=65536,t=2,p=1$ZGlmZnNhbHQ"
             "$sDV8zPvvkfOGCw26RHsjSMvv7K2vmQq/6cxAcmxSEnE"),
])

#=============================================================================
# argon2
#=============================================================================
class _base_argon2_test(HandlerCase):
    handler = hash.argon2

    known_correct_hashes = [
        #
        # custom
        #

        # sample test
        ("password", '$argon2i$v=19$m=256,t=1,p=1$c29tZXNhbHQ$AJFIsNZTMKTAewB4+ETN1A'),

        # sample w/ all parameters different
        ("password", '$argon2i$v=19$m=380,t=2,p=2$c29tZXNhbHQ$SrssP8n7m/12VWPM8dvNrw'),

        # ensures utf-8 used for unicode
        (UPASS_TABLE, '$argon2i$v=19$m=512,t=2,p=2$1sV0O4PWLtc12Ypv1f7oGw$'
                      'z+yqzlKtrq3SaNfXDfIDnQ'),
        (PASS_TABLE_UTF8, '$argon2i$v=19$m=512,t=2,p=2$1sV0O4PWLtc12Ypv1f7oGw$'
                          'z+yqzlKtrq3SaNfXDfIDnQ'),

        # ensure trailing null bytes handled correctly
        ('password\x00', '$argon2i$v=19$m=512,t=2,p=2$c29tZXNhbHQ$Fb5+nPuLzZvtqKRwqUEtUQ'),

        ]

    known_malformed_hashes = [
        # missing 'm' param
        "$argon2i$v=19$t=2,p=4$c29tZXNhbHQAAAAAAAAAAA$QWLzI4TY9HkL2ZTLc8g6SinwdhZewYrzz9zxCo0bkGY",

        # 't' param > max uint32
        "$argon2i$v=19$m=65536,t=8589934592,p=4$c29tZXNhbHQAAAAAAAAAAA$QWLzI4TY9HkL2ZTLc8g6SinwdhZewYrzz9zxCo0bkGY",

        # unexpected param
        "$argon2i$v=19$m=65536,t=2,p=4,q=5$c29tZXNhbHQAAAAAAAAAAA$QWLzI4TY9HkL2ZTLc8g6SinwdhZewYrzz9zxCo0bkGY",

        # wrong param order
        "$argon2i$v=19$t=2,m=65536,p=4,q=5$c29tZXNhbHQAAAAAAAAAAA$QWLzI4TY9HkL2ZTLc8g6SinwdhZewYrzz9zxCo0bkGY",

        # constraint violation: m < 8 * p
        "$argon2i$v=19$m=127,t=2,p=16$c29tZXNhbHQ$IMit9qkFULCMA/ViizL57cnTLOa5DiVM9eMwpAvPwr4",
    ]

    def do_stub_encrypt(self, handler=None, **settings):
        if self.backend == "argon2_cffi":
            # overriding default since no way to get stub config from argon2._calc_hash()
            handler = (handler or self.handler).using(**settings)
            self = handler(use_defaults=True)
            self.checksum = self._stub_checksum
            assert self.checksum
            return self.to_string()
        else:
            return super(_base_argon2_test, self).do_stub_encrypt(handler, **settings)

    def test_03_legacy_hash_workflow(self):
        # override base method
        raise self.skipTest("legacy 1.6 workflow not supported")

    def test_keyid_parameter(self):
        # NOTE: keyid parameter currently not supported by official argon2 hash parser,
        #       even though it's mentioned in the format spec.
        #       we're trying to be consistent w/ this, so hashes w/ keyid should
        #       always through a NotImplementedError.
        self.assertRaises(NotImplementedError, self.handler.verify, 'password',
                          "$argon2i$v=19$m=65536,t=2,p=4,keyid=ABCD$c29tZXNhbHQ$"
                          "IMit9qkFULCMA/ViizL57cnTLOa5DiVM9eMwpAvPwr4")

    def test_data_parameter(self):
        # NOTE: argon2 c library doesn't support passing in a data parameter to argon2_hash();
        #       but argon2_verify() appears to parse that info... but then discards it (!?).
        #       not sure what proper behavior is, filed issue -- https://github.com/P-H-C/phc-winner-argon2/issues/143
        #       For now, replicating behavior we have for the two backends, to detect when things change.
        handler = self.handler

        # ref hash of 'password' when 'data' is correctly passed into argon2()
        sample1 = '$argon2i$v=19$m=512,t=2,p=2,data=c29tZWRhdGE$c29tZXNhbHQ$KgHyCesFyyjkVkihZ5VNFw'

        # ref hash of 'password' when 'data' is silently discarded (same digest as w/o data)
        sample2 = '$argon2i$v=19$m=512,t=2,p=2,data=c29tZWRhdGE$c29tZXNhbHQ$uEeXt1dxN1iFKGhklseW4w'

        # hash of 'password' w/o the data field
        sample3 = '$argon2i$v=19$m=512,t=2,p=2$c29tZXNhbHQ$uEeXt1dxN1iFKGhklseW4w'

        #
        # test sample 1
        #

        if self.backend == "argon2_cffi":
            # incorrectly returns False -- should either be True, or throw parse error
            self.assertFalse(handler.verify("password", sample1))

            # incorrectly returns sample3, dropping data parameter
            self.assertEqual(handler.genhash("password", sample1), sample3)

        else:
            assert self.backend == "argon2pure"
            # should parse and verify
            self.assertTrue(handler.verify("password", sample1))

            # should preserve sample1
            self.assertEqual(handler.genhash("password", sample1), sample1)

        #
        # test sample 2
        #

        if self.backend == "argon2_cffi":
            # incorrectly returns True -- should either be False, or throw parse error
            self.assertTrue(handler.verify("password", sample2))

            # incorrectly returns sample3, dropping data parameter
            self.assertEqual(handler.genhash("password", sample1), sample3)

        else:
            assert self.backend == "argon2pure"
            # should parse, but fail to verify
            self.assertFalse(self.handler.verify("password", sample2))

            # should return sample1 (corrected digest)
            self.assertEqual(handler.genhash("password", sample2), sample1)

    def test_keyid_and_data_parameters(self):
        # test combination of the two, just in case
        self.assertRaises(NotImplementedError, self.handler.verify, 'stub',
                          "$argon2i$v=19$m=65536,t=2,p=4,keyid=ABCD,data=EFGH$c29tZXNhbHQ$"
                          "IMit9qkFULCMA/ViizL57cnTLOa5DiVM9eMwpAvPwr4")

    def test_needs_update_w_type(self):
        handler = self.handler

        hash = handler.hash("stub")
        self.assertFalse(handler.needs_update(hash))

        hash2 = hash.replace("$argon2i$", "$argon2d$")
        self.assertTrue(handler.needs_update(hash2))

    def test_needs_update_w_version(self):
        handler = self.handler.using(memory_cost=65536, time_cost=2, parallelism=4,
                                     digest_size=32)
        hash = ("$argon2i$m=65536,t=2,p=4$c29tZXNhbHQAAAAAAAAAAA$"
                "QWLzI4TY9HkL2ZTLc8g6SinwdhZewYrzz9zxCo0bkGY")
        if handler.max_version == 0x10:
            self.assertFalse(handler.needs_update(hash))
        else:
            self.assertTrue(handler.needs_update(hash))

    def test_argon_byte_encoding(self):
        """verify we're using right base64 encoding for argon2"""
        handler = self.handler
        if handler.version != 0x13:
            # TODO: make this fatal, and add refs for other version.
            raise self.skipTest("handler uses wrong version for sample hashes")

        # 8 byte salt
        salt = b'somesalt'
        temp = handler.using(memory_cost=256, time_cost=2, parallelism=2, salt=salt,
                             checksum_size=32)
        hash = temp.hash("password")
        self.assertEqual(hash, "$argon2i$v=19$m=256,t=2,p=2"
                               "$c29tZXNhbHQ"
                               "$T/XOJ2mh1/TIpJHfCdQan76Q5esCFVoT5MAeIM1Oq2E")

        # 16 byte salt
        salt = b'somesalt\x00\x00\x00\x00\x00\x00\x00\x00'
        temp = handler.using(memory_cost=256, time_cost=2, parallelism=2, salt=salt,
                             checksum_size=32)
        hash = temp.hash("password")
        self.assertEqual(hash, "$argon2i$v=19$m=256,t=2,p=2"
                               "$c29tZXNhbHQAAAAAAAAAAA"
                               "$rqnbEp1/jFDUEKZZmw+z14amDsFqMDC53dIe57ZHD38")

    def fuzz_setting_memory_cost(self):
        if self.backend == "argon2pure":
            return randintgauss(128, 384, 256, 128)
        else:
            return randintgauss(128, 32767, 16384, 4096)

    # TODO: fuzz parallelism, digest_size

#-----------------------------------------
# test suites for specific backends
#-----------------------------------------

class argon2_argon2_cffi_test(_base_argon2_test.create_backend_case("argon2_cffi")):

    # add some more test vectors that take too long under argon2pure
    known_correct_hashes = _base_argon2_test.known_correct_hashes + [
        #
        # sample hashes from argon2 cffi package's unittests,
        # which in turn were generated by official argon2 cmdline tool.
        #

        # v1.2, type I, w/o a version tag
        ('password', "$argon2i$m=65536,t=2,p=4$c29tZXNhbHQAAAAAAAAAAA$"
                     "QWLzI4TY9HkL2ZTLc8g6SinwdhZewYrzz9zxCo0bkGY"),

        # v1.3, type I
        ('password', "$argon2i$v=19$m=65536,t=2,p=4$c29tZXNhbHQ$"
                     "IMit9qkFULCMA/ViizL57cnTLOa5DiVM9eMwpAvPwr4"),

        # v1.3, type D
        ('password', "$argon2d$v=19$m=65536,t=2,p=4$c29tZXNhbHQ$"
                     "cZn5d+rFh+ZfuRhm2iGUGgcrW5YLeM6q7L3vBsdmFA0"),

        #
        # custom
        #

        # ensure trailing null bytes handled correctly
        ('password\x00', "$argon2i$v=19$m=65536,t=2,p=4$c29tZXNhbHQ$"
                         "Vpzuc0v0SrP88LcVvmg+z5RoOYpMDKH/lt6O+CZabIQ"),

        ]

    # add reference hashes from argon2 clib tests
    known_correct_hashes.extend(
        (info['secret'], info['hash']) for info in reference_data
        if info['logM'] <= (18 if TEST_MODE("full") else 16)
    )

class argon2_argon2pure_test(_base_argon2_test.create_backend_case("argon2pure")):

    handler = hash.argon2.using(memory_cost=32, parallelism=2)

    # add reference hashes from argon2 clib tests
    known_correct_hashes = _base_argon2_test.known_correct_hashes[:]
    known_correct_hashes.extend(
        (info['secret'], info['hash']) for info in reference_data
        if info['logM'] < 16
    )

    def fuzz_setting_rounds(self):
        # decrease default rounds for fuzz testing to speed up volume.
        return randintgauss(1, 3, 2, 1)

#=============================================================================
# eof
#=============================================================================
