import logging

from chainpack.cpon import CponReader, CponWriter
from chainpack.chainpack import ChainPackReader, ChainPackWriter

logging.basicConfig(level=logging.INFO, format='%(levelname)s[%(module)s:%(lineno)d] %(message)s')
_logger = logging.getLogger("tests")

class Test:
	def checkEq(self, e1, e2, msg=''):
		#console.log((e1 === e2)? "OK": "ERROR", ":", e1, "vs.", e2)
		if isinstance(e1, str):
			e1 = e1.encode()
		if isinstance(e2, str):
			e2 = e2.encode()
		if e1 == e2:
			return
		if msg:
			raise RuntimeError(msg)
		else:
			raise RuntimeError("test check error: " + e1.decode() + " == " + e2.decode())

	def testConversions(self):
		for lst in [
			[str((2**31 - 1)).encode() + b"u", None],
			[str(2**32 - 1).encode() + b"u", None],
			["" + str(2**31 - 1), None],
			["" + str(-(2**30 - 1)), None],
			["" + str(2**53 - 1), None],
			["" + str(-(2**53 - 1)), None],
			[str(2**32 - 1).encode(), None],
			["true", None],
			["false", None],
			["null", None],
			["1u", None],
			["134", None],
			["7", None],
			["-2", None],
			["0xab", "171"],
			["-0xCD", "-205"],
			["0x1a2b3c4d", "439041101"],
			["223.", None],
			["2.30", None],
			["12.3e-10", "123e-11"],
			["-0.00012", "-12e-5"],
			["-1234567890.", "-1234567890."],
			['"foo"', None],
			["[]", None],
			["[1]", None],
			["[1,]", "[1]"],
			["[1,2,3]", None],
			["[[]]", None],
			['{"foo":"bar"}', None],
			["i{1:2}", None],
			["i{\n\t1: \"bar\",\n\t345u : \"foo\",\n}", "i{1:\"bar\",345:\"foo\"}"],
			["[1u,{\"a\":1},2.30]", None],
			["<1:2>3", None],
			["[1,<7:8>9]", None],
			["<>1", None],
			["<8:3u>i{2:[[\".broker\",<1:2>true]]}", None],
			['<"foo":"bar",1:2>i{1:<7:8>9}', '<1:2,"foo":"bar">i{1:<7:8>9}'],
			["<1:2,\"foo\":<5:6>\"bar\">[1u,{\"a\":1},2.30]", None],
			["i{1:2 // comment to end of line\n}", "i{1:2}"],
			["<1:2>[3,<4:5>6]", None],
			["<4:\"svete\">i{2:<4:\"svete\">[0,1]}", None],
			['d"2019-05-03T11:30:00-0700"', 'd"2019-05-03T11:30:00-07"'],
			#['d""', None],
			['d"2018-02-02T00:00:00Z"', None],
			['d"2027-05-03T11:30:12.345+01"', None],
			['/*comment 1*/{ /*comment 2*/\n'
			 + '\t\"foo\"/*comment \"3\"*/: \"bar\", //comment to end of line\n'
			 + '\t\"baz\" : 1,\n'
			 + '/*\n'
			 + '\tmultiline comment\n'
			 + '\t\"baz\" : 1,\n'
			 + '\t\"baz\" : 1, // single inside multi\n'
			 + '*/\n'
			 + '}', '{"baz":1,"foo":"bar"}'],
		]:
			cpon1 = lst[0]
			cpon2 = lst[1] if lst[1] else cpon1
			print(cpon1)
			rv1 = CponReader.unpack(cpon1)
			cpk1 = ChainPackWriter.pack(rv1)
			rv2 = ChainPackReader.unpack(cpk1)
			cpn2 = CponWriter.pack(rv2)
			# _logger.info("\t{}\t--cpon------>\t{}".format(cpon1, cpn1))
			# self.checkEq(cpn1, cpon2);
			#
			# cpn2 = rv2.to_cpon();
			# _logger.info("\t{}\t--chainpack->\t{}".format(cpn1, cpn2))
			# # print(cpn1, "\t--chainpack->\t", cpn2)
			self.checkEq(cpon2, cpn2)

	def testDateTime(self):
		# same points in time
		v1 = CponReader.unpack('d"2017-05-03T18:30:00Z"')
		v2 = CponReader.unpack('d"2017-05-03T22:30:00+04"')
		v3 = CponReader.unpack('d"2017-05-03T11:30:00-0700"')
		v4 = CponReader.unpack('d"2017-05-03T15:00:00-0330"')
		self.checkEq(v1.value.epochMsec, v2.value.epochMsec)
		self.checkEq(v2.value.epochMsec, v3.value.epochMsec)
		self.checkEq(v3.value.epochMsec, v4.value.epochMsec)
		self.checkEq(v4.value.epochMsec, v1.value.epochMsec)

if __name__ == "__main__":
	t = Test()

	t.testConversions()
	t.testDateTime()

	print("PASSED")
