
inc = include_directories('.')

drakomme_files = files(
	'drakomme.cpp',
	'MmeDocument.cpp',
	'MmeTuringDocument.cpp',
)
drakomme_files += bison.process('MmeParser.ypp')
drakomme_files += flex.process('MmeLexer.lpp')
drakomme_files += bison.process('MmeTuringParser.ypp')
drakomme_files += flex.process('MmeTuringLexer.lpp')

drakodef_files = files(
	'drakodef.cpp',
	'DefDocument.cpp',
	'DefBackendCpp.cpp',
	'DefBackendMme.cpp',
)
drakodef_files += bison.process('DefParser.ypp')
drakodef_files += flex.process('DefLexer.lpp')
