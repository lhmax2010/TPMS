gcc -Wall -o trace_parser trace_parser.c trace_parser_mongo.c trace_parser_text.c minilzo.c protocol_v3_0.c protocol_v4_0.c -DMONGO_HAVE_STDINT -lmongoc -DFILTER=0x111
