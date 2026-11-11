
inc = include_directories('.')

dekomme_files = files(
	'dekomme.cpp',
	'MmeDocument.cpp',
	'MmeTuringDocument.cpp',
)
dekomme_files += bison.process('MmeParser.ypp')
dekomme_files += flex.process('MmeLexer.lpp')
dekomme_files += bison.process('MmeTuringParser.ypp')
dekomme_files += flex.process('MmeTuringLexer.lpp')

dekodef_files = files(
	'dekodef.cpp',
	'DefDocument.cpp',
	'DefBackendCpp.cpp',
	'DefBackendMme.cpp',
)
dekodef_files += bison.process('DefParser.ypp')
dekodef_files += flex.process('DefLexer.lpp')
